import os
from pathlib import Path


# ============================================================
# PROJECT PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
REPORTS_DIR = PROJECT_ROOT / "reports"
RESULTS_FILE = REPORTS_DIR / "results.json"


# ============================================================
# DATA FILES
# ============================================================

SAMPLE_FILE = Path(
    os.environ.get("SAMPLE_FILE", str(DATA_DIR / "orders_sample_100000.csv"))
)

# المسار الحقيقي للملف الضخم يُقرأ من متغير بيئة ORIGINAL_FILE
# مثال (Windows):  set ORIGINAL_FILE=D:\big data file\orders_huge_mixed_quality\orders_huge_mixed_quality.csv
# مثال (Linux/Mac): export ORIGINAL_FILE=/path/to/orders_huge_mixed_quality.csv
ORIGINAL_FILE = Path(
    os.environ.get(
        "ORIGINAL_FILE",
        str(DATA_DIR / "orders_huge_mixed_quality.csv"),
    )
)


# ============================================================
# FILE ROUTER
# ============================================================

SMALL_FILE_THRESHOLD_MB = int(os.environ.get("SMALL_FILE_THRESHOLD_MB", 200))
# التبرير: 200 ميغابايت اختيرت لأنها أكبر من حجم عينة الاختبار (100000 سجل تقريباً
# بضع عشرات من الميغابايتات) بهامش أمان مريح، وفي نفس الوقت أصغر بكثير من حجم
# الملف الضخم الفعلي (عدة مئات من الميغابايت / جيجابايت)، بحيث يضمن أن العينة
# دائماً تذهب لمسار Python Batch وأن الملف الكامل دائماً يذهب لمسار PySpark،
# وهو ما يطابق سيناريو العرض العملي المطلوب في القسم 10.


# ============================================================
# BATCH SETTINGS
# ============================================================

BATCH_SIZE = int(os.environ.get("BATCH_SIZE", 10000))


# ============================================================
# SAMPLE SETTINGS
# ============================================================

SAMPLE_ROWS = int(os.environ.get("SAMPLE_ROWS", 100000))


# ============================================================
# MONGODB
# ============================================================

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
MONGO_DATABASE = os.environ.get("MONGO_DATABASE", "bigdata_midterm")

RAW_COLLECTION = "orders_raw"
VALIDATED_COLLECTION = "orders_validated"
QUARANTINE_COLLECTION = "orders_quarantine"


# ============================================================
# SPARK SETTINGS
# ============================================================

SPARK_APP_NAME = os.environ.get("SPARK_APP_NAME", "midterm-orders-pipeline")
SPARK_MASTER = os.environ.get("SPARK_MASTER", "local[*]")
# اسم حزمة MongoDB Spark Connector (يجب أن يطابق إصدار Spark المثبت لديك)
SPARK_MONGO_CONNECTOR_PACKAGE = os.environ.get(
    "SPARK_MONGO_CONNECTOR_PACKAGE",
    "org.mongodb.spark:mongo-spark-connector_2.12:10.3.0",
)
SPARK_INPUT_PARTITIONS = int(os.environ.get("SPARK_INPUT_PARTITIONS", 0))  # 0 = افتراضي Spark


# ============================================================
# COLUMN MAPPING (RAW CSV -> LOGICAL FIELD NAMES)
# ============================================================
# مهم جداً: هذه القيم افتراضية بناءً على وصف المشروع فقط.
# شغّل src/inspect_data.py على ملفك الحقيقي أولاً وعدّل القيم بالجهة اليمنى
# (اسم العمود الفعلي في ملف الـ CSV لديك) لتطابق ملفك تماماً.


# ============================================================
# COLUMN MAPPING (RAW CSV -> LOGICAL FIELD NAMES)
# ============================================================
# الجهة اليسرى: الاسم المنطقي الذي يبحث عنه quality_rules.py (لا تغيره)
# الجهة اليمنى: الاسم الفعلي الدقيق كما هو مكتوب في السطر الأول من ملف CSV لديك

COLUMN_MAP = {
    "order_id": "order_id",          # العمود 1
    "order_date": "order_date",      # العمود 2
    "status": "status",              # العمود 3 (مهم جداً لـ quality_rules)
    "customer_id": "customer_id",    # العمود 4
    "customer_name": "customer_name",# العمود 5
    "customer_phone": "customer_phone", # العمود 6
    "customer_email": "customer_email", # العمود 7
    "city": "city",                  # العمود 8
    "district": "district",          # العمود 9
    "delivery_type": "delivery_type",# العمود 10
    "delivery_fee": "delivery_cost", # العمود 11 (مهم: الجودة تبحث عن delivery_fee)
    "payment_method": "payment_method", # العمود 12
    "payment_status": "payment_status", # العمود 13
    "payment_amount": "payment_amount", # العمود 14
    "currency": "currency",          # العمود 15
    "total_amount": "total_amount",  # العمود 16
    "items": "items_json",           # العمود 17 (مهم جداً: الجودة تبحث عن "items")



# ________________________________
    # "customer_id": os.environ.get("COL_CUSTOMER_ID", "customer_id"),
    # "customer_email": os.environ.get("COL_CUSTOMER_EMAIL", "customer_email"),
    # "customer_phone": os.environ.get("COL_CUSTOMER_PHONE", "customer_phone"),
    # "order_date": os.environ.get("COL_ORDER_DATE", "order_date"),
    # "items": os.environ.get("COL_ITEMS", "items"),              # JSON string
    # "currency": os.environ.get("COL_CURRENCY", "currency"),
    # "delivery_fee": os.environ.get("COL_DELIVERY_FEE", "delivery_fee"),
    # "total_amount": os.environ.get("COL_TOTAL_AMOUNT", "total_amount"),
    # "status": os.environ.get("COL_STATUS", "status"),
}


# ============================================================
# QUARANTINE ERROR CODES
# ============================================================

ITEM_QUANTITY_KEYS = ["quantity", "qty", "count", "amount_units"]
ITEM_UNIT_PRICE_KEYS = ["unit_price", "price", "item_price", "price_per_unit"]
# أسماء مرشحة لاسم/معرّف المنتج داخل كل عنصر items - تُستخدم في تقرير
# "أفضل المنتجات" (aggregations.py). عدّلها إن كانت بياناتك تستخدم اسماً
# مختلفاً فعلياً (مثل inspect_data.py للتحقق من بنية items الحقيقية).
ITEM_PRODUCT_KEYS = ["product_id", "product_name", "product", "sku", "item_name", "name"]


QUARANTINE_CODES = {
    "ID_ORDER_MISSING": "معرف الطلب مفقود ولا يمكن استنتاجه.",
    "ID_CUSTOMER_MISSING": "معرف العميل مفقود.",
    "DATE_IMPOSSIBLE_INVALID": "تاريخ غير منطقي أو مستحيل.",
    "JSON_ITEMS_CORRUPTED": "JSON ناقص أو غير قابل للتحليل.",
    "ITEMS_EMPTY": "لا توجد عناصر للطلب.",
    "PRICE_UNKNOWN": "السعر الأصلي غير موجود أو غير قابل للاستنتاج.",
    "VALUE_NEGATIVE_AMBIGUOUS": "كمية أو مبلغ سالب لا يمكن تحديد معناه.",
    "ID_ORDER_DUPLICATE": "تكرار يحتاج سياسة دمج أو مراجعة.",
    "ERRORS_CONFLICTING_MULTIPLE": "عدة أخطاء جوهرية تمنع التصحيح الآمن.",
}
