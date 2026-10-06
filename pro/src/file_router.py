from pathlib import Path

from config.settings import SMALL_FILE_THRESHOLD_MB

def get_file_size_mb(file_path):
    """
    Return file size in megabytes.
    """

    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(
            f"File not found: {path}"
        )

    size_bytes = path.stat().st_size

    size_mb = size_bytes / (1024 * 1024)

    return size_mb

def select_engine(file_path):
    """
    Select the processing engine according to file size.

    <= 200 MB  -> Python Batch
    > 200 MB   -> PySpark
    """

    path = Path(file_path)

    size_mb = get_file_size_mb(path)

    if size_mb <= SMALL_FILE_THRESHOLD_MB:

        engine = "python_batch"

        reason = (
            f"File size ({size_mb:.2f} MB) "
            f"is below or equal to "
            f"the {SMALL_FILE_THRESHOLD_MB} MB threshold."
        )

    else:

        engine = "pyspark"

        reason = (
            f"File size ({size_mb:.2f} MB) "
            f"is greater than "
            f"the {SMALL_FILE_THRESHOLD_MB} MB threshold."
        )

    return {
        "file_path": str(path),
        "file_size_mb": round(size_mb, 2),
        "engine": engine,
        "reason": reason
    }

def print_routing_decision(file_path):
    """
    Display the routing decision.
    """

    result = select_engine(file_path)

    print("=" * 70)
    print("FILE ROUTER")
    print("=" * 70)

    print(f"File Size       : {result['file_size_mb']} MB")
    print(f"Selected Engine : {result['engine']}")
    print(f"Reason          : {result['reason']}")

    print("=" * 70)

if __name__ == "__main__":

    from config.settings import SAMPLE_FILE, ORIGINAL_FILE

    print("\nSMALL SAMPLE")
    print("-" * 70)

    print_routing_decision(SAMPLE_FILE)

    print("\nORIGINAL LARGE FILE")
    print("-" * 70)

    print_routing_decision(ORIGINAL_FILE)