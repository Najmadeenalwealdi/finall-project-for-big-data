"""
api.py

المتطلب الجديد (5): واجهة API موحدة للتشغيل والاختبار (FastAPI).

هذه الواجهة ليست مشروع Backend مستقلاً - هي فقط غلاف تشغيل موحّد حول
الوظائف الموجودة أصلاً في المشروع (main.run_pipeline, indexes.py,
queries.py, aggregations.py, materialized_views.py, jobs.py). لا يوجد
أي منطق تحميل/تنظيف/تصنيف جديد هنا.

POST /ingest يستخدم main.run_pipeline() بالضبط - نفس بوابة الإدخال
والـPipeline المستخدمة من سطر الأوامر (src/main.py)، بدون مسار إدخال
جديد كما تنص المواصفة.

تشغيل:
    uvicorn src.api:app --reload --port 8000
    افتح http://localhost:8000/docs لواجهة Swagger.
"""

import sys
from contextlib import asynccontextmanager
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
sys.path.append(str(Path(__file__).resolve().parent))

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from pymongo import MongoClient

from config.settings import (
    MONGO_URI, MONGO_DATABASE, SAMPLE_FILE,
)
import indexes as indexes_module
import queries as queries_module
import aggregations as aggregations_module
import materialized_views as mv_module
import jobs as jobs_module
from scheduler import start_scheduler, stop_scheduler
from main import run_pipeline


# ============================================================
# دورة حياة التطبيق: اتصال Mongo واحد يعاد استخدامه + تشغيل المجدول
# ============================================================

class _State:
    client: MongoClient = None
    db = None


state = _State()


@asynccontextmanager
async def lifespan(app: FastAPI):
    state.client = MongoClient(MONGO_URI)
    state.db = state.client[MONGO_DATABASE]
    start_scheduler(state.db)
    yield
    stop_scheduler()
    state.client.close()


app = FastAPI(
    title="Big Data Orders Pipeline API",
    description="واجهة تشغيل واختبار موحّدة لمشروع البيانات الضخمة (Phase 2).",
    version="1.0.0",
    lifespan=lifespan,
)


# ============================================================
# نماذج الطلبات (Request bodies)
# ============================================================

class IngestRequest(BaseModel):
    file_path: str = str(SAMPLE_FILE)
    skip_setup: bool = False


class RefreshMvRequest(BaseModel):
    view: str | None = None  # None = كل العروض
    force_full: bool = False


# ============================================================
# المسارات
# ============================================================

@app.get("/health")
def health():
    try:
        state.client.admin.command("ping")
        mongo_ok = True
    except Exception:
        mongo_ok = False
    return {"status": "ok" if mongo_ok else "degraded", "database": MONGO_DATABASE, "mongo_connected": mongo_ok}


@app.post("/ingest")
def ingest(req: IngestRequest):
    """يشغّل خط الأنابيب الكامل (نفس main.py) على ملف CSV محدد."""
    try:
        result = run_pipeline(req.file_path, skip_setup=req.skip_setup, db=state.db)
        return result
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error))
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(error))


@app.post("/indexes")
def create_indexes():
    created = indexes_module.create_indexes(state.db)
    return {"created_indexes": created}


@app.get("/queries")
def list_queries():
    return queries_module.list_queries()


@app.get("/queries/{name}")
def run_query(name: str, limit: int = 10,
              status: str | None = None, customer_id: str | None = None,
              city: str | None = None, min_amount: float | None = None,
              payment_method: str | None = None, payment_status: str | None = None):
    if name not in queries_module.QUERY_DEFINITIONS:
        raise HTTPException(status_code=404, detail=f"Unknown query: {name}")
    params = {
        k: v for k, v in {
            "status": status, "customer_id": customer_id, "city": city,
            "min_amount": min_amount, "payment_method": payment_method,
            "payment_status": payment_status,
        }.items() if v is not None
    }
    results = queries_module.run_query(state.db, name, params, limit)
    return {"query": name, "params": params, "count": len(results), "results": results}


@app.get("/aggregations")
def list_aggregations():
    return aggregations_module.list_aggregations()


@app.get("/aggregations/{name}")
def run_aggregation(name: str, limit: int | None = None, granularity: str | None = None):
    if name not in aggregations_module.AGGREGATIONS:
        raise HTTPException(status_code=404, detail=f"Unknown aggregation: {name}")
    params = {k: v for k, v in {"limit": limit, "granularity": granularity}.items() if v is not None}
    results = aggregations_module.run_aggregation(state.db, name, params)
    return {"aggregation": name, "params": params, "count": len(results), "results": results}


@app.post("/refresh-mv")
def refresh_mv(req: RefreshMvRequest = RefreshMvRequest()):
    if req.view == mv_module.DAILY_SALES_VIEW:
        return mv_module.refresh_daily_sales_summary(state.db, force_full=req.force_full)
    if req.view == mv_module.TOP_PRODUCTS_VIEW:
        return mv_module.refresh_top_products_summary(state.db, force_full=req.force_full)
    if req.view is None:
        return mv_module.refresh_all(state.db, force_full=req.force_full)
    raise HTTPException(status_code=404, detail=f"Unknown view: {req.view}")


@app.get("/jobs")
def list_jobs():
    return jobs_module.list_jobs(state.db)


@app.post("/jobs/{name}/run")
def run_job(name: str):
    if name not in jobs_module.JOB_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Unknown job: {name}")
    return jobs_module.run_job(state.db, name)
