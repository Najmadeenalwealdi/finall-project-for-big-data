"""
mongo_setup.py

إعداد قاعدة بيانات MongoDB: إنشاء الـ Collections المطلوبة، وضبط
Unique Index على id_order في orders_validated فقط (بدون Validator أو
Unique Index على orders_raw حتى لا يمنعا التحميل الخام كما تنص المواصفة 6.9).
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import ConnectionFailure

from config.settings import (
    MONGO_URI,
    MONGO_DATABASE,
    RAW_COLLECTION,
    VALIDATED_COLLECTION,
    QUARANTINE_COLLECTION,
)


def get_client():
    return MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)


def setup_mongodb():
    print("=" * 60)
    print("MONGODB SETUP")
    print("=" * 60)

    try:
        client = get_client()
        client.admin.command("ping")
        print("[OK] MongoDB connection successful")

        db = client[MONGO_DATABASE]
        existing_collections = db.list_collection_names()

        # ------------------------------------------------------------
        # orders_raw: بدون Validator وبدون Unique Index (طبقة تتبع تاريخية)
        # ------------------------------------------------------------
        if RAW_COLLECTION not in existing_collections:
            db.create_collection(RAW_COLLECTION)
            print(f"[OK] Created collection: {RAW_COLLECTION}")
        else:
            print(f"[OK] Collection already exists: {RAW_COLLECTION}")

        # فهرس غير فريد يسرّع البحث والتتبع حسب id_run (لا يمنع التكرار)
        db[RAW_COLLECTION].create_index([("id_run", ASCENDING)])
        db[RAW_COLLECTION].create_index([("record_raw.order_id_raw", ASCENDING)])

        # ------------------------------------------------------------
        # orders_validated: Unique Index على order_id (مفتاح العمل الثابت)
        # ------------------------------------------------------------
        if VALIDATED_COLLECTION not in existing_collections:
            db.create_collection(VALIDATED_COLLECTION)
            print(f"[OK] Created collection: {VALIDATED_COLLECTION}")
        else:
            print(f"[OK] Collection already exists: {VALIDATED_COLLECTION}")

        db[VALIDATED_COLLECTION].create_index(
            [("order_id", ASCENDING)], unique=True, name="uniq_order_id"
        )
        print("[OK] Unique index on order_id ensured for orders_validated")

        # ------------------------------------------------------------
        # orders_quarantine: بدون قيود فريدة (يمكن أن يتكرر نفس الطلب لأسباب مختلفة)
        # ------------------------------------------------------------
        if QUARANTINE_COLLECTION not in existing_collections:
            db.create_collection(QUARANTINE_COLLECTION)
            print(f"[OK] Created collection: {QUARANTINE_COLLECTION}")
        else:
            print(f"[OK] Collection already exists: {QUARANTINE_COLLECTION}")

        db[QUARANTINE_COLLECTION].create_index([("id_run", ASCENDING)])
        db[QUARANTINE_COLLECTION].create_index([("codes_error", ASCENDING)])

        # ------------------------------------------------------------
        # إضافات المشروع النهائي: job_runs (سجل تنفيذ المهام المجدولة)
        # و mv_control (علامات التحديث التزايدي للعروض المادية)
        # ------------------------------------------------------------
        db["job_runs"].create_index([("job_name", ASCENDING), ("started_at", DESCENDING)])
        db["mv_control"].create_index([("view_name", ASCENDING)], unique=True)

        print()
        print(f"Database: {MONGO_DATABASE}")
        print("MongoDB setup completed successfully.")
        print("=" * 60)

        client.close()
        return True

    except ConnectionFailure as error:
        print("[FAIL] Could not connect to MongoDB.")
        print("Make sure MongoDB Server is installed and running.")
        print(f"Error: {error}")
        return False


if __name__ == "__main__":
    setup_mongodb()
