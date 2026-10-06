"""
count_validated.py

أداة سريعة لعرض عدد السجلات في كل Collection، وعدد السجلات الفريدة
حسب order_id في orders_validated - يُستخدم لإثبات Idempotency يدوياً
(تشغيل هذا السكربت قبل وبعد إعادة تشغيل نفس الملف يجب أن يعطي نفس
عدد السجلات في orders_validated).
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from pymongo import MongoClient

from config.settings import (
    MONGO_URI, MONGO_DATABASE,
    RAW_COLLECTION, VALIDATED_COLLECTION, QUARANTINE_COLLECTION,
)


def main():
    client = MongoClient(MONGO_URI)
    db = client[MONGO_DATABASE]

    raw_count = db[RAW_COLLECTION].count_documents({})
    validated_count = db[VALIDATED_COLLECTION].count_documents({})
    quarantine_count = db[QUARANTINE_COLLECTION].count_documents({})

    distinct_order_ids = len(db[VALIDATED_COLLECTION].distinct("order_id"))

    print("=" * 60)
    print(f"Database: {MONGO_DATABASE}")
    print("=" * 60)
    print(f"{RAW_COLLECTION:20}: {raw_count:,}")
    print(f"{VALIDATED_COLLECTION:20}: {validated_count:,}  (distinct order_id: {distinct_order_ids:,})")
    print(f"{QUARANTINE_COLLECTION:20}: {quarantine_count:,}")

    if validated_count != distinct_order_ids:
        print(
            "\n[WARNING] validated_count != distinct order_id count -> "
            "there may be duplicate business records (Idempotency violation)."
        )
    else:
        print("\n[OK] No duplicate order_id in orders_validated.")

    client.close()


if __name__ == "__main__":
    main()
