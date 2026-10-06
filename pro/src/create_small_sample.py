import csv
import argparse
from pathlib import Path

def create_sample(input_file, output_file, rows):
    input_path = Path(input_file)
    output_path = Path(output_file)

    if not input_path.exists():
        raise FileNotFoundError(
            f"Input file not found: {input_path}"
        )

    print("=" * 60)
    print("Creating reproducible sample")
    print("=" * 60)
    print(f"Input : {input_path}")
    print(f"Output: {output_path}")
    print(f"Rows  : {rows}")
    print()

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(
        input_path,
        "r",
        encoding="utf-8-sig",
        newline="",
        errors="replace"
    ) as source:

        reader = csv.reader(source)

        with open(
            output_path,
            "w",
            encoding="utf-8",
            newline=""
        ) as target:

            writer = csv.writer(target)

            # قراءة Header
            header = next(reader)
            writer.writerow(header)

            count = 0

            for row in reader:

                writer.writerow(row)
                count += 1

                if count >= rows:
                    break

                if count % 10000 == 0:
                    print(f"Processed: {count:,} rows")

    print()
    print("=" * 60)
    print("Sample creation completed")
    print("=" * 60)
    print(f"Rows created: {count:,}")
    print(f"Output file : {output_path}")

if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Create a small reproducible CSV sample"
    )

    parser.add_argument(
        "--input",
        required=True,
        help="Path to the original large CSV file"
    )

    parser.add_argument(
        "--output",
        default="data/orders_sample_100000.csv",
        help="Output sample file"
    )

    parser.add_argument(
        "--rows",
        type=int,
        default=100000,
        help="Number of data rows to extract"
    )

    args = parser.parse_args()

    create_sample(
        args.input,
        args.output,
        args.rows
    )