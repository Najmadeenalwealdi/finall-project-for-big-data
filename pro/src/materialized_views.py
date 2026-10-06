"""
materialized_views.py

المتطلب الجديد (3): Materialized Views - عروض مادية (2 على الأقل):
  - daily_sales_summary : إجمالي المبيعات وعدد الطلبات لكل يوم
  - top_products_summary : إيراد/كمية كل منتج عبر كل الطلبات

آلية التحديث التزايدي (incremental refresh):
  كل عرض له "علامة مائية" (watermark) محفوظة في collection مستقل اسمه
  mv_control (view_name -> last_watermark datetime). عند كل تحديث:
    1) نجد السجلات في orders_validated التي last_updated_at > watermark
       السابقة فقط (التحديث الصحيح لـ last_updated_at بحيث لا يتغيّر إلا
       للسجلات المُدرجة/المُحدّثة فعلياً تم إصلاحه في elt_pipeline.py -
       السجلات unchanged لا تُكتب إطلاقاً فلا تُحرّك last_updated_at).
    2) نحدد *فقط* الأيام (لـ daily_sales_summary) أو *فقط* المنتجات
       (لـ top_products_summary) التي تأثرت بهذه السجلات المتغيرة.
    3) نعيد حساب إجمالي هذه الأيام/المنتجات المتأثرة فقط من
       orders_validated (Upsert لكل مستند في العرض) - بدون إعادة حساب
       أو إعادة بناء الأيام/المنتجات التي لم تتأثر، وبدون المرور على كل
       مجموعة البيانات من جديد.
  أول تشغيل (لا توجد watermark محفوظة) هو الاستثناء الطبيعي الوحيد: يُبنى
  العرض كاملاً لأنه لا يوجد شيء سابق يُستكمل منه.

تشغيل مباشر:
    python src/materialized_views.py --refresh daily_sales_summary
    python src/materialized_views.py --refresh top_products_summary
    python src/materialized_views.py --refresh-all
    python src/materialized_views.py --refresh-all --force-full   # إعادة بناء كاملة صريحة
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from pymongo import UpdateOne

from config.settings import MONGO_URI, MONGO_DATABASE, VALIDATED_COLLECTION
from aggregations import BUSINESS_MATCH, _normalized_items_stage

MV_CONTROL_COLLECTION = "mv_control"
DAILY_SALES_VIEW = "daily_sales_summary"
TOP_PRODUCTS_VIEW = "top_products_summary"


def _get_watermark(db, view_name):
    doc = db[MV_CONTROL_COLLECTION].find_one({"view_name": view_name})
    return doc.get("last_watermark") if doc else None


def _set_watermark(db, view_name, watermark, extra=None):
    update = {"last_watermark": watermark, "last_refreshed_at": datetime.now(timezone.utc)}
    if extra:
        update.update(extra)
    db[MV_CONTROL_COLLECTION].update_one(
        {"view_name": view_name}, {"$set": update}, upsert=True,
    )


def refresh_daily_sales_summary(db, force_full=False):
    """يحدّث daily_sales_summary تزايدياً - فقط الأيام المتأثرة بتغييرات جديدة."""
    refresh_started_at = datetime.now(timezone.utc)
    watermark = None if force_full else _get_watermark(db, DAILY_SALES_VIEW)
    is_full_rebuild = watermark is None

    changed_match = dict(BUSINESS_MATCH)
    if not is_full_rebuild:
        changed_match["last_updated_at"] = {"$gt": watermark, "$lte": refresh_started_at}

    if is_full_rebuild:
        affected_days = None  # None = كل الأيام (بناء أول/كامل)
    else:
        changed_days_cursor = db[VALIDATED_COLLECTION].aggregate([
            {"$match": changed_match},
            {"$group": {"_id": "$order_date"}},
        ])
        affected_days = [d["_id"] for d in changed_days_cursor if d["_id"]]
        if not affected_days:
            _set_watermark(db, DAILY_SALES_VIEW, refresh_started_at, {"last_affected": 0})
            return {"view": DAILY_SALES_VIEW, "mode": "incremental", "affected_days": 0,
                    "note": "لا توجد تغييرات جديدة منذ آخر تحديث"}

    day_match = dict(BUSINESS_MATCH)
    if affected_days is not None:
        day_match["order_date"] = {"$in": affected_days}

    pipeline = [
        {"$match": day_match},
        {"$group": {
            "_id": "$order_date",
            "total_sales": {"$sum": "$total_amount"},
            "orders_count": {"$sum": 1},
            "avg_order_value": {"$avg": "$total_amount"},
        }},
    ]
    results = list(db[VALIDATED_COLLECTION].aggregate(pipeline))

    ops = [
        UpdateOne(
            {"_id": row["_id"]},
            {"$set": {
                "day": row["_id"],
                "total_sales": round(row["total_sales"], 2),
                "orders_count": row["orders_count"],
                "avg_order_value": round(row["avg_order_value"], 2),
                "updated_at": refresh_started_at,
            }},
            upsert=True,
        )
        for row in results if row["_id"]
    ]
    if ops:
        db[DAILY_SALES_VIEW].bulk_write(ops, ordered=False)

    _set_watermark(db, DAILY_SALES_VIEW, refresh_started_at, {"last_affected": len(ops)})
    return {
        "view": DAILY_SALES_VIEW,
        "mode": "full" if is_full_rebuild else "incremental",
        "affected_days": len(ops),
    }


def refresh_top_products_summary(db, force_full=False):
    """يحدّث top_products_summary تزايدياً - فقط المنتجات التي ظهرت في طلبات متغيرة."""
    refresh_started_at = datetime.now(timezone.utc)
    watermark = None if force_full else _get_watermark(db, TOP_PRODUCTS_VIEW)
    is_full_rebuild = watermark is None

    changed_match = dict(BUSINESS_MATCH)
    if not is_full_rebuild:
        changed_match["last_updated_at"] = {"$gt": watermark, "$lte": refresh_started_at}

    if is_full_rebuild:
        affected_products = None  # None = كل المنتجات
    else:
        changed_products_cursor = db[VALIDATED_COLLECTION].aggregate([
            {"$match": changed_match},
            _normalized_items_stage(),
            {"$unwind": "$items_norm"},
            {"$group": {"_id": "$items_norm.product"}},
        ])
        affected_products = [p["_id"] for p in changed_products_cursor if p["_id"]]
        if not affected_products:
            _set_watermark(db, TOP_PRODUCTS_VIEW, refresh_started_at, {"last_affected": 0})
            return {"view": TOP_PRODUCTS_VIEW, "mode": "incremental", "affected_products": 0,
                    "note": "لا توجد تغييرات جديدة منذ آخر تحديث"}

    pipeline = [{"$match": BUSINESS_MATCH}, _normalized_items_stage(), {"$unwind": "$items_norm"}]
    if affected_products is not None:
        pipeline.append({"$match": {"items_norm.product": {"$in": affected_products}}})
    pipeline += [
        {"$group": {
            "_id": "$items_norm.product",
            "revenue": {"$sum": {"$multiply": ["$items_norm.qty", "$items_norm.unit_price"]}},
            "units_sold": {"$sum": "$items_norm.qty"},
            "orders_count": {"$sum": 1},
        }},
    ]
    results = list(db[VALIDATED_COLLECTION].aggregate(pipeline))

    ops = [
        UpdateOne(
            {"_id": row["_id"]},
            {"$set": {
                "product": row["_id"],
                "revenue": round(row["revenue"], 2),
                "units_sold": row["units_sold"],
                "orders_count": row["orders_count"],
                "updated_at": refresh_started_at,
            }},
            upsert=True,
        )
        for row in results if row["_id"]
    ]
    if ops:
        db[TOP_PRODUCTS_VIEW].bulk_write(ops, ordered=False)

    _set_watermark(db, TOP_PRODUCTS_VIEW, refresh_started_at, {"last_affected": len(ops)})
    return {
        "view": TOP_PRODUCTS_VIEW,
        "mode": "full" if is_full_rebuild else "incremental",
        "affected_products": len(ops),
    }


def refresh_all(db, force_full=False):
    return [
        refresh_daily_sales_summary(db, force_full=force_full),
        refresh_top_products_summary(db, force_full=force_full),
    ]


def _cli():
    parser = argparse.ArgumentParser(description="Refresh materialized views")
    parser.add_argument("--refresh", choices=[DAILY_SALES_VIEW, TOP_PRODUCTS_VIEW])
    parser.add_argument("--refresh-all", action="store_true")
    parser.add_argument("--force-full", action="store_true")
    args = parser.parse_args()

    from pymongo import MongoClient
    client = MongoClient(MONGO_URI)
    db = client[MONGO_DATABASE]
    try:
        if args.refresh_all:
            for result in refresh_all(db, force_full=args.force_full):
                print(result)
        elif args.refresh == DAILY_SALES_VIEW:
            print(refresh_daily_sales_summary(db, force_full=args.force_full))
        elif args.refresh == TOP_PRODUCTS_VIEW:
            print(refresh_top_products_summary(db, force_full=args.force_full))
        else:
            parser.print_help()
    finally:
        client.close()


if __name__ == "__main__":
    _cli()
