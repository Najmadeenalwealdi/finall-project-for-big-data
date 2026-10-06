"""
main.py

نقطة التشغيل الرئيسية الوحيدة للمشروع (المطلوبة في القسم 6.2 و9).

الاستخدام:
    python src/main.py --file data/orders_sample_100000.csv
    python src/main.py --file "$ORIGINAL_FILE"
    python src/main.py                      # يستخدم SAMPLE_FILE من settings.py افتراضياً

يمر بكل مراحل المعمارية (القسم 4):
  1) File Discovery   -> إنشاء id_run
  2) Engine Selection  -> file_router
  3) Load Raw          -> batch_loader أو spark_loader
  4-6) Quality/Classification/Final Load -> elt_pipeline
  7) (Idempotency تُختبر بإعادة تشغيل نفس الأمر مرة ثانية)
  8) Metrics           -> reports/results.json
"""

import argparse
import sys
import uuid
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
sys.path.append(str(Path(__file__).resolve().parent))

from pymongo import MongoClient

from config.settings import (
    MONGO_URI, MONGO_DATABASE,
    RAW_COLLECTION, VALIDATED_COLLECTION, QUARANTINE_COLLECTION,
    SAMPLE_FILE,
)
from file_router import select_engine, print_routing_decision
from mongo_setup import setup_mongodb
from metrics import RunMetrics, save_run_metrics


def parse_args():
    parser = argparse.ArgumentParser(description="Hybrid orders data pipeline")
    parser.add_argument(
        "--file",
        default=str(SAMPLE_FILE),
        help="Path to the input CSV file (default: SAMPLE_FILE from settings.py)",
    )
    parser.add_argument(
        "--skip-setup",
        action="store_true",
        help="Skip MongoDB collections/index setup (use if already set up)",
    )
    return parser.parse_args()


def run_pipeline(file_path, skip_setup=False, db=None):
    """
    ينفّذ خط الأنابيب الكامل (المراحل 1-8) على ملف واحد، ويُرجع
    run_metrics.to_dict(). هذه هي "بوابة الإدخال" الوحيدة للمشروع -
    يستخدمها main() عبر CLI وأيضاً POST /ingest في api.py (المشروع
    النهائي، القسم 5) بدون أي مسار إدخال مستقل جديد، كما تنص المواصفة.

    db: اتصال MongoDB جاهز (اختياري) - يُستخدم عندما يستدعيها api.py
    التي تملك اتصالاً مفتوحاً مسبقاً بدل فتح اتصال جديد لكل طلب ingest.
    """
    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    # -------- المرحلة 1: File Discovery + id_run --------
    id_run = str(uuid.uuid4())
    print(f"\nid_run = {id_run}\n")

    if not skip_setup:
        ok = setup_mongodb()
        if not ok:
            raise RuntimeError("MongoDB setup failed.")

    # -------- المرحلة 2: اختيار المحرك --------
    routing = select_engine(file_path)
    print_routing_decision(file_path)

    metrics = RunMetrics(
        id_run=id_run,
        file_name=str(file_path),
        file_size_mb=routing["file_size_mb"],
        used_engine=routing["engine"],
    )

    owns_client = db is None
    client = None
    if owns_client:
        client = MongoClient(MONGO_URI)
        db = client[MONGO_DATABASE]

    try:
        # -------- المرحلة 3: Load Raw --------
        if routing["engine"] == "python_batch":
            from batch_loader import load_raw_batch
            load_raw_batch(file_path, id_run, db, RAW_COLLECTION, metrics)
        else:
            from spark_loader import load_raw_spark
            load_raw_spark(file_path, id_run, RAW_COLLECTION, metrics)

        # -------- المراحل 4-6: Quality, Classification, Final Load (Upsert) --------
        from elt_pipeline import run_quality_and_load
        run_quality_and_load(
            id_run, db,
            RAW_COLLECTION, VALIDATED_COLLECTION, QUARANTINE_COLLECTION,
            metrics,
        )

        # -------- المرحلة 8: Metrics --------
        metrics.finish()
        metrics.print_summary()
        save_run_metrics(metrics)

        ok, expected = metrics.check_consistency()
        if not ok:
            print(
                f"[WARNING] Consistency check FAILED for id_run={id_run}: "
                f"loaded_raw={metrics.loaded_raw} != "
                f"valid+corrected+quarantine={expected}"
            )

        return metrics.to_dict()

    finally:
        if owns_client:
            client.close()


def main():
    args = parse_args()
    try:
        run_pipeline(args.file, skip_setup=args.skip_setup)
    except (FileNotFoundError, RuntimeError) as error:
        print(f"[ERROR] {error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
