"""
create_size_sample.py

مكمّل لـ create_small_sample.py: بدل تحديد عدد صفوف، ينشئ عينة بحجم
تقريبي بالميغابايت - مفيد لاختبار File Router عند الحدود (threshold)
بدقة (مثال: عينة 210MB للتأكد من أن Router يختار PySpark فعلاً).

الاستخدام:
    python src/create_size_sample.py --input orders_huge_mixed_quality.csv --target-mb 210
"""

import argparse
import csv
from pathlib import Path


def create_size_sample(input_file, output_file, target_mb):
    input_path = Path(input_file)
    output_path = Path(output_file)
    target_bytes = target_mb * 1024 * 1024

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Creating size-targeted sample")
    print(f"Input     : {input_path}")
    print(f"Output    : {output_path}")
    print(f"Target    : {target_mb} MB")
    print("=" * 60)

    written_bytes = 0
    count = 0

    with open(input_path, "r", encoding="utf-8-sig", newline="", errors="replace") as source:
        reader = csv.reader(source)
        with open(output_path, "w", encoding="utf-8", newline="") as target:
            writer = csv.writer(target)

            header = next(reader)
            header_line = ",".join(header) + "\n"
            writer.writerow(header)
            written_bytes += len(header_line.encode("utf-8"))

            for row in reader:
                writer.writerow(row)
                line_len = len(",".join(row).encode("utf-8")) + 1
                written_bytes += line_len
                count += 1

                if written_bytes >= target_bytes:
                    break

                if count % 50000 == 0:
                    print(f"  ...{count:,} rows, {written_bytes / (1024*1024):.1f} MB so far")

    print(f"[OK] Wrote {count:,} rows, ~{written_bytes / (1024*1024):.2f} MB -> {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create a CSV sample targeting a specific size in MB")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", default="data/orders_sample_size.csv")
    parser.add_argument("--target-mb", type=float, required=True)
    args = parser.parse_args()

    create_size_sample(args.input, args.output, args.target_mb)
