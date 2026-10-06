import csv
from pathlib import Path

INPUT_FILE = Path("data/orders_sample_100000.csv")

def inspect_data(file_path):
    if not file_path.exists():
        raise FileNotFoundError(
            f"File not found: {file_path}"
        )

    print("=" * 70)
    print("DATASET INSPECTION")
    print("=" * 70)

    with open(
        file_path,
        "r",
        encoding="utf-8-sig",
        newline="",
        errors="replace"
    ) as file:

        reader = csv.reader(file)

        # قراءة أسماء الأعمدة
        header = next(reader)

        print("\nColumns:")
        print("-" * 70)

        for index, column in enumerate(header, start=1):
            print(f"{index:2}. {column}")

        print("\nNumber of columns:", len(header))

        # قراءة أول 5 سجلات فقط
        print("\nFirst 5 records:")
        print("-" * 70)

        for row_number, row in enumerate(reader, start=1):

            print(f"\nRecord #{row_number}")

            for column, value in zip(header, row):
                print(f"  {column}: {value}")

            if row_number >= 5:
                break

if __name__ == "__main__":
    inspect_data(INPUT_FILE)