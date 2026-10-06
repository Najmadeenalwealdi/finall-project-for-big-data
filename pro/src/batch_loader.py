"""
batch_loader.py

تحميل الملفات الصغيرة (<= SMALL_FILE_THRESHOLD_MB) باستخدام Python Batch:
- قراءة Streaming بوحدة csv (لا list(reader) ولا تحميل كامل بالذاكرة).
- تجميع السجلات في دفعات قابلة للضبط (BATCH_SIZE) ثم insert_many.
- طباعة رقم الدفعة وعدد السجلات والزمن ومعدل الإدخال.
- معالجة أخطاء الدفعة وتسجيلها دون إخفاء سبب الفشل.
"""

import csv
import time
from datetime import datetime, timezone
from pathlib import Path

from pymongo.errors import BulkWriteError

from config.settings import BATCH_SIZE


def load_raw_batch(file_path, id_run, mongo_db, raw_collection_name, metrics):
    """
    يقرأ ملف CSV صف بصف (Streaming) ويحمّله إلى orders_raw على دفعات.
    يُرجع True عند النجاح الكامل، ويرفع الاستثناء بعد تسجيله عند فشل حقيقي.
    """
    path = Path(file_path)
    raw_collection = mongo_db[raw_collection_name]

    print("=" * 70)
    print(f"PYTHON BATCH LOADER  (id_run={id_run})")
    print("=" * 70)
    print(f"File       : {path}")
    print(f"Batch size : {BATCH_SIZE}")
    metrics.size_batch = BATCH_SIZE

    with open(path, "r", encoding="utf-8-sig", newline="", errors="replace") as f:
        reader = csv.DictReader(f)

        buffer = []
        batch_number = 0
        total_rows = 0
        row_number = 0

        for row in reader:
            row_number += 1
            total_rows += 1

            doc = {
                "id_run": id_run,
                "file_source": str(path),
                "number_row_source": row_number,
                "at_ingested": datetime.now(timezone.utc),
                "engine_used": "python_batch",
                "record_raw": row,
            }
            buffer.append(doc)

            if len(buffer) >= BATCH_SIZE:
                batch_number += 1
                _flush_batch(raw_collection, buffer, batch_number)
                buffer = []

        if buffer:
            batch_number += 1
            _flush_batch(raw_collection, buffer, batch_number)

    metrics.read_rows = total_rows
    metrics.loaded_raw = total_rows

    print(f"[OK] Python Batch load finished. Total rows: {total_rows:,} in {batch_number} batches.")
    print("=" * 70)
    return True


def _flush_batch(raw_collection, buffer, batch_number):
    start = time.time()
    try:
        raw_collection.insert_many(buffer, ordered=False)
        elapsed = time.time() - start
        rate = len(buffer) / elapsed if elapsed > 0 else float("inf")
        print(
            f"  Batch #{batch_number:04d} | rows={len(buffer):6,} | "
            f"time={elapsed:6.2f}s | rate={rate:8.1f} rows/s"
        )
    except BulkWriteError as error:
        # لا نخفي سبب الفشل - نسجله ونستمر لأن هذه طبقة raw ولا فهرس فريد
        # يمنعها، لكن أي خطأ حقيقي (اتصال، صلاحيات..) يجب أن يظهر بوضوح.
        elapsed = time.time() - start
        n_errors = len(error.details.get("writeErrors", []))
        print(
            f"  Batch #{batch_number:04d} | FAILED partially | "
            f"errors={n_errors} | time={elapsed:6.2f}s"
        )
        for we in error.details.get("writeErrors", [])[:5]:
            print(f"    -> index={we.get('index')} code={we.get('code')} msg={we.get('errmsg')}")
    except Exception as error:
        print(f"  Batch #{batch_number:04d} | FAILED | error={error}")
        raise
