"""
elt_pipeline.py

المرحلتان 4 و5 و6 من المعمارية:
Quality & Transform -> Classification -> Final Load (Upsert)

يقرأ كل سجلات id_run الحالي من orders_raw (بعد أن حُمّلت خام بالكامل)،
يطبّق قواعد التنظيف والتصنيف من quality_rules.classify_record()، ثم:
  - يكتب السجلات Valid/Corrected إلى orders_validated عبر Upsert
    (idempotent, keyed on order_id).
  - يكتب السجلات غير القابلة للتصحيح إلى orders_quarantine.

ملاحظة مهمة حول count_inserted/count_updated/count_unchanged:
لا نعتمد على upserted_count/modified_count الجاهزة من MongoDB، لأن
modified_count يتأثر بأي حقل تغيّر في المستند - بما فيها حقول التتبع
(last_run_id, last_updated_at) التي تتغيّر في كل تشغيل بالضرورة حتى لو
محتوى السجل التجاري (order_id, items, total_amount...) لم يتغيّر إطلاقاً.
لذلك نقارن نحن الحقول التجارية يدوياً مقابل القيمة الموجودة فعلاً في
orders_validated قبل الكتابة، ونحسب insert/update/unchanged من هذه
المقارنة مباشرة - هذا ما يجعل unchanged يعمل فعلياً عند إعادة تشغيل
نفس الملف دون أي تعديل على البيانات.
"""

from datetime import datetime, timezone

from pymongo import UpdateOne

from config.settings import COLUMN_MAP
from quality_rules import classify_record


# الحقول "التجارية" فقط - أي حقل هنا يدخل في مقارنة
# insert/update/unchanged. حقول التتبع (last_run_id, last_updated_at,
# first_seen_run_id, created_at) مستثناة عمداً من هذه القائمة.
BUSINESS_FIELDS = [
    "order_id", "customer_id", "customer_name", "customer_email", "customer_phone",
    "order_date", "items", "currency", "delivery_fee", "delivery_type",
    "payment_method", "payment_status",
    "total_amount", "status", "city", "district",
    "quality_status", "corrections",
]


def run_quality_and_load(id_run, mongo_db, raw_collection_name,
                          validated_collection_name, quarantine_collection_name,
                          metrics, cursor_batch_size=5000):
    """
    يعالج كل سجلات id_run الحالي من orders_raw دفعة دفعة، ويصنفها،
    ثم يكتبها بـ Upsert إلى orders_validated أو يدرجها في orders_quarantine.
    """
    raw_collection = mongo_db[raw_collection_name]
    validated_collection = mongo_db[validated_collection_name]
    quarantine_collection = mongo_db[quarantine_collection_name]

    print("=" * 70)
    print(f"QUALITY & CLASSIFICATION  (id_run={id_run})")
    print("=" * 70)

    seen_order_ids = {}

    # دفعة السجلات الجاهزة للكتابة لـ orders_validated: order_id -> dict تجاري
    validated_batch = {}
    quarantine_docs = []

    count_valid = 0
    count_corrected = 0
    count_quarantine = 0
    processed = 0

    cursor = raw_collection.find({"id_run": id_run}, no_cursor_timeout=True).batch_size(cursor_batch_size)

    try:
        for raw_doc in cursor:
            processed += 1
            record_raw = raw_doc.get("record_raw", {}) or {}

            result = classify_record(record_raw, COLUMN_MAP, seen_order_ids=seen_order_ids)

            status = result["quality_status"]

            if status == "quarantined":
                count_quarantine += 1
                metrics.add_quarantine_code(result["quarantine_code"])
                quarantine_docs.append({
                    "id_run": id_run,
                    "order_id_raw": record_raw.get(COLUMN_MAP.get("order_id"), None),
                    "codes_error": result["codes_error"],
                    "details_error": result["quarantine_reason"],
                    "quarantine_code": result["quarantine_code"],
                    "record_raw": record_raw,
                    "corrections_attempted": result["corrections"],
                    "quarantined_at": datetime.now(timezone.utc),
                })
            else:
                if status == "valid":
                    count_valid += 1
                else:
                    count_corrected += 1
                    for correction in result["corrections"]:
                        metrics.add_correction_rule(correction["rule_code"])

                cleaned = result["cleaned"]
                order_id = cleaned["order_id"]

                business_doc = {
                    **cleaned,
                    "quality_status": status,
                    "corrections": result["corrections"],
                }
                validated_batch[order_id] = business_doc

            if len(validated_batch) >= cursor_batch_size:
                _flush_validated(validated_collection, validated_batch, metrics, id_run)
                validated_batch = {}

            if len(quarantine_docs) >= cursor_batch_size:
                quarantine_collection.insert_many(quarantine_docs, ordered=False)
                quarantine_docs = []

            if processed % 20000 == 0:
                print(f"  Processed {processed:,} raw records...")

        if validated_batch:
            _flush_validated(validated_collection, validated_batch, metrics, id_run)
        if quarantine_docs:
            quarantine_collection.insert_many(quarantine_docs, ordered=False)

    finally:
        cursor.close()

    metrics.count_valid = count_valid
    metrics.count_corrected = count_corrected
    metrics.count_quarantine = count_quarantine

    print(f"Valid       : {count_valid:,}")
    print(f"Corrected   : {count_corrected:,}")
    print(f"Quarantined : {count_quarantine:,}")
    print("=" * 70)


def _flush_validated(validated_collection, validated_batch, metrics, id_run):
    """
    يكتب دفعة من السجلات التجارية إلى orders_validated عبر Upsert،
    ويحسب count_inserted/count_updated/count_unchanged بمقارنة الحقول
    التجارية الجديدة مقابل ما هو موجود فعلاً في القاعدة قبل الكتابة -
    وليس من نتيجة bulk_write الجاهزة (انظر الشرح أعلى الملف).
    """
    if not validated_batch:
        return

    order_ids = list(validated_batch.keys())

    # قراءة دفعية واحدة لكل الحقول التجارية الحالية لهذه المعرفات فقط
    projection = {field: 1 for field in BUSINESS_FIELDS}
    projection["_id"] = 0
    existing_cursor = validated_collection.find(
        {"order_id": {"$in": order_ids}},
        projection,
    )
    existing_docs = {doc["order_id"]: doc for doc in existing_cursor}

    ops = []
    now = datetime.now(timezone.utc)

    for order_id, new_business in validated_batch.items():
        old_business = existing_docs.get(order_id)

        if old_business is not None and old_business == new_business:
            # Unchanged: متعمد عدم كتابة أي شيء لهذا السجل - لا UpdateOne
            # إطلاقاً. هذا يحافظ على last_updated_at كـ"علامة مائية"
            # (watermark) موثوقة لتحديد ما تغيّر فعلاً فقط، وهو ما تعتمد
            # عليه materialized_views.py للتحديث التزايدي بدل إعادة بناء
            # العرض كاملاً من الصفر في كل مرة (انظر القسم 3 من المشروع
            # النهائي). لو حدّثنا last_updated_at حتى للسجلات غير
            # المتغيرة، لكانت كل الإعادة-تشغيل تُعامَل كـ"تغيّر" خطأً.
            metrics.count_unchanged += 1
            continue

        update_doc = {
            "$set": {
                **new_business,
                "last_run_id": id_run,
                "last_updated_at": now,
            },
            "$setOnInsert": {
                "first_seen_run_id": id_run,
                "created_at": now,
            },
        }
        ops.append(UpdateOne({"order_id": order_id}, update_doc, upsert=True))

        if old_business is None:
            metrics.count_inserted += 1
        else:
            metrics.count_updated += 1

    if ops:
        validated_collection.bulk_write(ops, ordered=False)
