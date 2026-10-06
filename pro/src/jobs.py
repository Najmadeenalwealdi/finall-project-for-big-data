"""
jobs.py

المتطلب الجديد (4): المهام المجدولة - تعريف الوظائف نفسها + تسجيل كل
تنفيذ (بداية/نهاية/نجاح أو فشل) في collection اسمه job_runs.

جدولة هذه الوظائف (التوقيت الزمني) موجودة في scheduler.py - هذا الملف
يحتوي فقط منطق كل وظيفة + آلية التسجيل والتشغيل اليدوي، لأن كلا من
scheduler.py (APScheduler) و api.py (POST /jobs/{name}/run) يحتاجان
تشغيل الوظيفة نفسها بنفس الطريقة بالضبط (مجدولة أو يدوية - نفس الكود).

وظيفتان مسجّلتان (JOB_REGISTRY):
  - refresh_materialized_views : يستدعي materialized_views.refresh_all()
  - generate_periodic_report   : ينشئ ويحفظ تقريراً دورياً (عدة Aggregations)
    في collection اسمه periodic_reports
"""

import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from aggregations import run_aggregation
from materialized_views import refresh_all

JOB_RUNS_COLLECTION = "job_runs"
PERIODIC_REPORTS_COLLECTION = "periodic_reports"


def job_refresh_materialized_views(db, params=None):
    """الوظيفة المجدولة 1: تحديث العروض المادية تزايدياً."""
    results = refresh_all(db, force_full=False)
    return {"views_refreshed": [r["view"] for r in results], "details": results}


def job_generate_periodic_report(db, params=None):
    """
    الوظيفة المجدولة 2: تقرير دوري يجمع عدة Aggregations في مستند واحد
    ويحفظه في periodic_reports - مثال عملي على "إنشاء تقرير دوري"
    المذكور في المتطلبات كبديل/إضافة لتحديث العروض المادية.
    """
    generated_at = datetime.now(timezone.utc)
    report = {
        "generated_at": generated_at,
        "sales_by_city": run_aggregation(db, "sales_by_city", {"limit": 10}),
        "top_products": run_aggregation(db, "top_products", {"limit": 10}),
        "orders_status_distribution": run_aggregation(db, "orders_status_distribution"),
    }
    db[PERIODIC_REPORTS_COLLECTION].insert_one(dict(report))
    return {
        "report_generated_at": generated_at.isoformat(),
        "sections": ["sales_by_city", "top_products", "orders_status_distribution"],
    }


JOB_REGISTRY = {
    "refresh_materialized_views": {
        "run": job_refresh_materialized_views,
        "description": "تحديث daily_sales_summary و top_products_summary تزايدياً.",
    },
    "generate_periodic_report": {
        "run": job_generate_periodic_report,
        "description": "إنشاء تقرير دوري (عدة Aggregations) وحفظه في periodic_reports.",
    },
}


def list_jobs(db):
    """يُرجع تعريف كل وظيفة + آخر تنفيذ مسجّل لها (إن وجد)."""
    out = []
    for name, spec in JOB_REGISTRY.items():
        last_run = db[JOB_RUNS_COLLECTION].find_one(
            {"job_name": name}, sort=[("started_at", -1)]
        )
        out.append({
            "job_name": name,
            "description": spec["description"],
            "last_run": {
                "started_at": last_run["started_at"].isoformat() if last_run else None,
                "finished_at": last_run["finished_at"].isoformat() if last_run and last_run.get("finished_at") else None,
                "status": last_run["status"] if last_run else None,
            } if last_run else None,
        })
    return out


def run_job(db, job_name, params=None):
    """
    ينفّذ وظيفة واحدة من JOB_REGISTRY ويسجّل وقت البداية والنهاية وحالة
    النجاح/الفشل في job_runs - تُستخدم بنفس الشكل من المجدول (schedule)
    والتشغيل اليدوي (manual) عبر الـAPI، تماماً كما يتطلب القسم 4.
    """
    if job_name not in JOB_REGISTRY:
        raise ValueError(f"Unknown job: {job_name}")

    started_at = datetime.now(timezone.utc)
    status = "success"
    error = None
    result = None

    try:
        result = JOB_REGISTRY[job_name]["run"](db, params)
    except Exception as exc:  # noqa: BLE001 - نسجّل أي خطأ فعلي بدل إسقاط الوظيفة بصمت
        status = "failure"
        error = f"{exc.__class__.__name__}: {exc}"
        print(f"[JOB FAILED] {job_name}: {error}")
        traceback.print_exc()

    finished_at = datetime.now(timezone.utc)
    record = {
        "job_name": job_name,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_seconds": round((finished_at - started_at).total_seconds(), 3),
        "status": status,
        "error": error,
        "result": result,
    }
    db[JOB_RUNS_COLLECTION].insert_one(dict(record))

    record["started_at"] = started_at.isoformat()
    record["finished_at"] = finished_at.isoformat()
    return record


if __name__ == "__main__":
    import argparse
    from pymongo import MongoClient
    from config.settings import MONGO_URI, MONGO_DATABASE

    parser = argparse.ArgumentParser(description="Run a job manually")
    parser.add_argument("--run", required=True, choices=list(JOB_REGISTRY.keys()))
    args = parser.parse_args()

    client = MongoClient(MONGO_URI)
    db = client[MONGO_DATABASE]
    try:
        print(run_job(db, args.run))
    finally:
        client.close()
