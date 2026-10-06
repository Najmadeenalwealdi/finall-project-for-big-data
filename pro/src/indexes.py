"""
indexes.py

المتطلب الجديد (1): الاستعلامات والفهارس.

ينشئ 4 فهارس على orders_validated تخدم استعلامات queries.py مباشرة
(3 منها Compound Index، أكثر من الحد الأدنى المطلوب وهو واحد فقط):

  - idx_status_order_date   : (status, order_date)      -> Q1
  - idx_customer_order_date : (customer_id, order_date)  -> Q2
  - idx_city_total_amount   : (city, total_amount)       -> Q3
  - idx_quality_status      : (quality_status)           -> Q5

Q4 (orders_by_payment) تُترك عمداً بدون فهرس مخصص لها - التبرير: حقلا
payment_method/payment_status قليلا التمييز (cardinality منخفضة جداً،
عدد قليل من القيم الممكنة لكل منهما) على مجموعة بيانات بهذا الحجم، فإن
Index Scan عليهما لن يكون أفضل بشكل ملموس من Collection Scan مقارنة
بتكلفة صيانة فهرس إضافي مع كل كتابة - هذا جزء من "لماذا اختيرت هذه
الفهارس بالتحديد" المطلوب توضيحه.

لا نلمس orders_raw (طبقة خام تاريخية بلا استعلامات تحليلية) ولا نكرر
الفهرس الفريد uniq_order_id الموجود مسبقاً في mongo_setup.py.
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from pymongo import ASCENDING, DESCENDING

from config.settings import VALIDATED_COLLECTION


# كل فهرس: (keys, name, justification بالعربي يُطبع عند التنفيذ)
INDEX_SPECS = [
    {
        "keys": [("status", ASCENDING), ("order_date", DESCENDING)],
        "name": "idx_status_order_date",
        "compound": True,
        "serves_query": "orders_by_status",
        "justification": (
            "Compound index يخدم استعلاماً شائعاً جداً: تصفية حسب الحالة status "
            "(مثال: كل الطلبات المؤكدة) مع ترتيب تنازلي حسب order_date. ترتيب "
            "الحقلين مهم: status أولاً (equality) ثم order_date (range/sort) "
            "يطابق قاعدة ESR (Equality-Sort-Range) في MongoDB."
        ),
    },
    {
        "keys": [("customer_id", ASCENDING), ("order_date", DESCENDING)],
        "name": "idx_customer_order_date",
        "compound": True,
        "serves_query": "orders_by_customer",
        "justification": (
            "Compound index يخدم أكثر استعلام تكراراً في أي نظام طلبات: سجل "
            "طلبات عميل واحد (customer_id) مرتبة زمنياً. equality على "
            "customer_id أولاً يقلل فضاء البحث إلى طلبات هذا العميل فقط قبل "
            "الترتيب."
        ),
    },
    {
        "keys": [("city", ASCENDING), ("total_amount", DESCENDING)],
        "name": "idx_city_total_amount",
        "compound": True,
        "serves_query": "high_value_orders_by_city",
        "justification": (
            "Compound index يخدم تقارير تحليلية مرتبطة بالمدينة (المبيعات "
            "حسب المدينة / الطلبات عالية القيمة في مدينة معينة). city عالي "
            "التمييز نسبياً كحقل equality أول، و total_amount يخدم كلا "
            "الترتيب والنطاق (>=) في نفس الاستعلام."
        ),
    },
    {
        "keys": [("quality_status", ASCENDING)],
        "name": "idx_quality_status",
        "compound": False,
        "serves_query": "orders_needing_review",
        "justification": (
            "فهرس مفرد على quality_status (valid/corrected) يخدم استعلام "
            "مراجعة السجلات 'corrected' فقط - عدد القيم الممكنة قليل لكنه "
            "يُستخدم في كل تشغيل للمراجعة اليدوية والتقارير، وحجم المطابقات "
            "(corrected عادة جزء بسيط من الإجمالي) يجعل Index Scan مفيداً."
        ),
    },
]


def create_indexes(db):
    """ينشئ كل الفهارس في INDEX_SPECS على orders_validated (idempotent)."""
    collection = db[VALIDATED_COLLECTION]
    created = []
    print("=" * 70)
    print("CREATING INDEXES")
    print("=" * 70)
    for spec in INDEX_SPECS:
        collection.create_index(spec["keys"], name=spec["name"])
        kind = "compound" if spec["compound"] else "single-field"
        print(f"[OK] {spec['name']} ({kind}) -> serves query '{spec['serves_query']}'")
        print(f"     {spec['justification']}")
        created.append(spec["name"])
    print("=" * 70)
    return created


def drop_indexes(db):
    """يحذف الفهارس في INDEX_SPECS فقط (لإعادة قياس الأداء 'قبل الإنشاء')."""
    collection = db[VALIDATED_COLLECTION]
    existing = {ix["name"] for ix in collection.list_indexes()}
    for spec in INDEX_SPECS:
        if spec["name"] in existing:
            collection.drop_index(spec["name"])
            print(f"[OK] dropped {spec['name']}")


def list_indexes(db):
    collection = db[VALIDATED_COLLECTION]
    return list(collection.list_indexes())


if __name__ == "__main__":
    from pymongo import MongoClient
    from config.settings import MONGO_URI, MONGO_DATABASE

    client = MongoClient(MONGO_URI)
    db = client[MONGO_DATABASE]
    create_indexes(db)
    client.close()
