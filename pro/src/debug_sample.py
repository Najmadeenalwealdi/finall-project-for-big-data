"""
debug_sample.py

أداة تصحيح سريعة: تطبع نتيجة classify_record() على أول N سجل من
ملف CSV، بدون أي اتصال بـ MongoDB - مفيدة لتجربة قواعد التنظيف
وتعديل COLUMN_MAP بسرعة قبل تشغيل الخط الكامل.

الاستخدام:
    python src/debug_sample.py --file data/orders_sample_100000.csv --n 10
"""

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
sys.path.append(str(Path(__file__).resolve().parent))

from config.settings import COLUMN_MAP
from quality_rules import classify_record


def main():
    parser = argparse.ArgumentParser(description="Debug classify_record() on a few CSV rows")
    parser.add_argument("--file", required=True)
    parser.add_argument("--n", type=int, default=10)
    parser.add_argument(
        "--status", choices=["valid", "corrected", "quarantined"], default=None,
        help="Show only records matching this quality_status (scans more rows to find matches)",
    )
    parser.add_argument(
        "--max-scan", type=int, default=200000,
        help="Safety cap on how many rows to scan when filtering by --status",
    )
    args = parser.parse_args()

    seen = {}
    shown = 0
    scanned = 0
    with open(args.file, "r", encoding="utf-8-sig", newline="", errors="replace") as f:
        reader = csv.DictReader(f)
        print(f"Detected columns: {reader.fieldnames}\n")

        for row in reader:
            scanned += 1
            result = classify_record(row, COLUMN_MAP, seen_order_ids=seen)

            if args.status and result["quality_status"] != args.status:
                if scanned >= args.max_scan:
                    print(f"[stopped] scanned {scanned:,} rows without enough matches for --status {args.status}")
                    break
                continue

            shown += 1
            print(f"--- Record (row #{scanned}, match #{shown}) ---")
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
            print()

            if shown >= args.n:
                break


if __name__ == "__main__":
    main()
