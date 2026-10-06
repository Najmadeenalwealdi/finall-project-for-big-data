"""
scheduler.py

المتطلب الجديد (4): جدولة زمنية فعلية لوظائف jobs.py عبر APScheduler.

  - refresh_materialized_views : كل 15 دقيقة
  - generate_periodic_report   : كل 6 ساعات

يُستخدم من جهتين:
  1) مستقلاً: `python src/scheduler.py` يشغّل المجدول في العملية
     الحالية ويبقيها حية (مفيد للعرض/الاختبار اليدوي المباشر).
  2) من api.py: start_scheduler(db) تُستدعى عند بدء تشغيل FastAPI
     لتعمل الجدولة في الخلفية طوال عمر خدمة الـAPI، مع إبقاء القدرة
     على تشغيل أي وظيفة يدوياً في أي وقت عبر jobs.run_job() مباشرة
     (هذا ما يستخدمه POST /jobs/{name}/run بدون الانتظار للجدول).
"""

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from apscheduler.schedulers.background import BackgroundScheduler

from jobs import run_job

REFRESH_MV_INTERVAL_MINUTES = 15
PERIODIC_REPORT_INTERVAL_HOURS = 6

_scheduler_instance = None


def build_scheduler(db):
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        lambda: run_job(db, "refresh_materialized_views"),
        trigger="interval",
        minutes=REFRESH_MV_INTERVAL_MINUTES,
        id="refresh_materialized_views",
        replace_existing=True,
        next_run_time=datetime.now(timezone.utc),
    )
    scheduler.add_job(
        lambda: run_job(db, "generate_periodic_report"),
        trigger="interval",
        hours=PERIODIC_REPORT_INTERVAL_HOURS,
        id="generate_periodic_report",
        replace_existing=True,
    )
    return scheduler


def start_scheduler(db):
    """يبدأ المجدول مرة واحدة فقط (singleton) - تُستدعى من api.py عند الإقلاع."""
    global _scheduler_instance
    if _scheduler_instance is not None and _scheduler_instance.running:
        return _scheduler_instance
    _scheduler_instance = build_scheduler(db)
    _scheduler_instance.start()
    print(
        f"[OK] Scheduler started: refresh_materialized_views every "
        f"{REFRESH_MV_INTERVAL_MINUTES}min, generate_periodic_report every "
        f"{PERIODIC_REPORT_INTERVAL_HOURS}h"
    )
    return _scheduler_instance


def stop_scheduler():
    global _scheduler_instance
    if _scheduler_instance is not None:
        _scheduler_instance.shutdown(wait=False)
        _scheduler_instance = None


if __name__ == "__main__":
    from pymongo import MongoClient
    from config.settings import MONGO_URI, MONGO_DATABASE

    client = MongoClient(MONGO_URI)
    db = client[MONGO_DATABASE]
    sched = start_scheduler(db)
    print("Scheduler running. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(2)
    except (KeyboardInterrupt, SystemExit):
        stop_scheduler()
        client.close()
        print("\nScheduler stopped.")
