"""
compare_raw_vs_csv.py

أداة تحقق: تقارن عدد صفوف ملف CSV المصدر (بدون الترويسة) مع عدد
السجلات التي وصلت فعلياً إلى orders_raw لنفس id_run، للتأكد من أن
كل السجلات وصلت إلى Raw قبل أي فلترة (مبدأ ELT في القسم 6.5).

الاستخدام:
    python src/compare_raw_vs_csv.py --file data/orders_sample_100000.csv --id-run <uuid>
"""

import argparse
import csv
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from pymongo import MongoClient

from config.settings import MONGO_URI, MONGO_DATABASE, RAW_COLLECTION


def count_csv_rows(file_path):
    with open(file_path, "r", encoding="utf-8-sig", newline="", errors="replace") as f:
        reader = csv.reader(f)
        next(reader, None)  # header
        return sum(1 for _ in reader)


def main():
    parser = argparse.ArgumentParser(description="Compare source CSV row count vs orders_raw count")
    parser.add_argument("--file", required=True, help="Path to source CSV file")
    parser.add_argument("--id-run", required=True, help="id_run to check in orders_raw")
    args = parser.parse_args()

    csv_rows = count_csv_rows(args.file)

    client = MongoClient(MONGO_URI)
    db = client[MONGO_DATABASE]
    raw_count = db[RAW_COLLECTION].count_documents({"id_run": args.id_run})
    client.close()

    print("=" * 60)
    print(f"CSV rows (excluding header) : {csv_rows:,}")
    print(f"orders_raw docs for id_run  : {raw_count:,}")
    print("=" * 60)

    if csv_rows == raw_count:
        print("[OK] Every source row reached orders_raw.")
    else:
        print(f"[MISMATCH] Difference: {csv_rows - raw_count:,} rows")


if __name__ == "__main__":
    main()
