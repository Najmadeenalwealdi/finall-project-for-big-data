"""
reset_db.py

يفرغ Collections المشروع لإعادة اختبار المشروع من الصفر.
مفيد قبل أول تشغيل لإثبات Idempotency بشكل نظيف، أو أثناء التطوير.
لا يُستخدم كجزء من خط البيانات نفسه - أداة صيانة فقط.

يستخدم drop() بدل delete_many({}): حذف مجموعة كاملة (drop) شبه فوري
بغض النظر عن حجمها، بينما delete_many({}) على ملايين المستندات يحذفها
واحداً واحداً وقد يأخذ وقتاً طويلاً جداً. بعد drop() يُعاد إنشاء
الفهارس (Unique Index على order_id...) عبر mongo_setup تلقائياً.

الاستخدام:
    python src/reset_db.py            # يسأل تأكيد
    python src/reset_db.py --yes      # بدون تأكيد
    python src/reset_db.py --yes --only orders_raw   # تصفير مجموعة واحدة فقط
"""

import argparse
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
sys.path.append(str(Path(__file__).resolve().parent))

from pymongo import MongoClient

from config.settings import (
    MONGO_URI, MONGO_DATABASE,
    RAW_COLLECTION, VALIDATED_COLLECTION, QUARANTINE_COLLECTION,
)
from mongo_setup import setup_mongodb


def reset_collections(target_names):
    client = MongoClient(MONGO_URI)
    db = client[MONGO_DATABASE]

    for name in target_names:
        if name in db.list_collection_names():
            db.drop_collection(name)
            print(f"[OK] Dropped collection: {name}")
        else:
            print(f"[SKIP] Collection did not exist: {name}")

    client.close()

    # إعادة إنشاء المجموعات والفهارس (Unique Index على order_id، إلخ)
    print()
    setup_mongodb()


if __name__ == "__main__":
    all_collections = (RAW_COLLECTION, VALIDATED_COLLECTION, QUARANTINE_COLLECTION)

    parser = argparse.ArgumentParser(description="Reset (drop + recreate) pipeline collections")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt")
    parser.add_argument(
        "--only", choices=all_collections, default=None,
        help="Drop only this one collection instead of all three",
    )
    args = parser.parse_args()

    targets = (args.only,) if args.only else all_collections

    if not args.yes:
        answer = input(
            f"This will DROP (fast, irreversible) the following collections: "
            f"{', '.join(targets)} (database: {MONGO_DATABASE}). Continue? [y/N] "
        )
        if answer.strip().lower() != "y":
            print("Aborted.")
            sys.exit(0)

    reset_collections(targets)
