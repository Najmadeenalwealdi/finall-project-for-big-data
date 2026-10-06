"""
aggregations.py

المتطلب الجديد (2): 5 تقارير Aggregation على الأقل، كل واحد باسم
واضح وطريقة تشغيل مستقلة ويعيد نتيجة فعلية من بيانات orders_validated.

  1. sales_by_city            - إجمالي المبيعات وعدد الطلبات حسب المدينة
  2. top_products              - أفضل المنتجات حسب الإيراد (من items)
  3. top_customers              - أفضل العملاء حسب إجمالي الشراء
  4. sales_by_period            - المبيعات حسب الفترة الزمنية (شهرياً)
  5. orders_status_distribution - توزيع الطلبات حسب الحالة (status)

items لكل طلب مصفوفة من عناصر بأسماء حقول غير موحّدة بالضرورة
(انظر ITEM_*_KEYS في settings.py)؛ لذلك نبني تعبير $ifNull متسلسل في
Mongo نفسه (عبر _first_present_expr) يجرب كل اسم مرشح بالترتيب،
بدل الافتراض أن اسم الحقل ثابت.

تشغيل مباشر:
    python src/aggregations.py --list
    python src/aggregations.py --run sales_by_city
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from config.settings import (
    MONGO_URI, MONGO_DATABASE, VALIDATED_COLLECTION,
    ITEM_QUANTITY_KEYS, ITEM_UNIT_PRICE_KEYS, ITEM_PRODUCT_KEYS,
)


# فقط السجلات التي لها قيمة تجارية فعلية (valid/corrected) تدخل التقارير -
# orders_quarantine مستبعدة دوماً من هذه التقارير التحليلية.
BUSINESS_MATCH = {"quality_status": {"$in": ["valid", "corrected"]}}


def _first_present_expr(var_name, candidate_keys, default=None):
    """
    يبني تعبير Mongo $ifNull متسلسلاً يجرب كل مفتاح من candidate_keys
    بالترتيب على متغير $$var_name (عنصر items عبر $map)، ويرجع default
    إذا لم يوجد أي منها - مطابق لمنطق _first_present في quality_rules.py
    لكن كتعبير Mongo بدل بايثون.
    """
    expr = default
    for key in reversed(candidate_keys):
        expr = {"$ifNull": [f"$$item.{key}", expr]}
    return expr


def _normalized_items_stage():
    """
    $addFields يحوّل items (أسماء حقول متفاوتة) إلى items_norm موحدة:
    [{product, qty, unit_price, line_total}], قابلة لإعادة الاستخدام في
    أي تقرير بدون تكرار منطق $ifNull.
    """
    qty_expr = _first_present_expr("item", ITEM_QUANTITY_KEYS, default=1)
    price_expr = _first_present_expr("item", ITEM_UNIT_PRICE_KEYS, default=0)
    product_expr = _first_present_expr("item", ITEM_PRODUCT_KEYS, default="UNKNOWN")

    return {
        "$addFields": {
            "items_norm": {
                "$map": {
                    "input": {"$ifNull": ["$items", []]},
                    "as": "item",
                    "in": {
                        "product": product_expr,
                        "qty": {"$toDouble": {"$ifNull": [qty_expr, 1]}},
                        "unit_price": {"$toDouble": {"$ifNull": [price_expr, 0]}},
                    },
                }
            }
        }
    }


def _build_sales_by_city(params):
    return [
        {"$match": BUSINESS_MATCH},
        {"$group": {
            "_id": "$city",
            "total_sales": {"$sum": "$total_amount"},
            "orders_count": {"$sum": 1},
            "avg_order_value": {"$avg": "$total_amount"},
        }},
        {"$project": {
            "_id": 0, "city": {"$ifNull": ["$_id", "غير محدد"]},
            "total_sales": {"$round": ["$total_sales", 2]},
            "orders_count": 1,
            "avg_order_value": {"$round": ["$avg_order_value", 2]},
        }},
        {"$sort": {"total_sales": -1}},
        {"$limit": int(params.get("limit", 20))},
    ]


def _build_top_products(params):
    return [
        {"$match": BUSINESS_MATCH},
        _normalized_items_stage(),
        {"$unwind": "$items_norm"},
        {"$group": {
            "_id": "$items_norm.product",
            "revenue": {"$sum": {"$multiply": ["$items_norm.qty", "$items_norm.unit_price"]}},
            "units_sold": {"$sum": "$items_norm.qty"},
            "orders_count": {"$sum": 1},
        }},
        {"$project": {
            "_id": 0, "product": "$_id",
            "revenue": {"$round": ["$revenue", 2]},
            "units_sold": 1, "orders_count": 1,
        }},
        {"$sort": {"revenue": -1}},
        {"$limit": int(params.get("limit", 10))},
    ]


def _build_top_customers(params):
    return [
        {"$match": BUSINESS_MATCH},
        {"$group": {
            "_id": "$customer_id",
            "customer_name": {"$first": "$customer_name"},
            "total_spent": {"$sum": "$total_amount"},
            "orders_count": {"$sum": 1},
        }},
        {"$project": {
            "_id": 0, "customer_id": "$_id", "customer_name": 1,
            "total_spent": {"$round": ["$total_spent", 2]},
            "orders_count": 1,
        }},
        {"$sort": {"total_spent": -1}},
        {"$limit": int(params.get("limit", 10))},
    ]


def _build_sales_by_period(params):
    # order_date مخزّن كنص ISO "YYYY-MM-DD" - substrBytes(0,7) يعطي "YYYY-MM"
    granularity = params.get("granularity", "month")
    period_len = 7 if granularity == "month" else 10  # "month" أو "day"
    return [
        {"$match": BUSINESS_MATCH},
        {"$addFields": {"period": {"$substrBytes": ["$order_date", 0, period_len]}}},
        {"$group": {
            "_id": "$period",
            "total_sales": {"$sum": "$total_amount"},
            "orders_count": {"$sum": 1},
        }},
        {"$project": {
            "_id": 0, "period": "$_id",
            "total_sales": {"$round": ["$total_sales", 2]},
            "orders_count": 1,
        }},
        {"$sort": {"period": 1}},
    ]


def _build_orders_status_distribution(params):
    return [
        {"$match": BUSINESS_MATCH},
        {"$group": {"_id": "$status", "orders_count": {"$sum": 1}}},
        {"$group": {
            "_id": None,
            "statuses": {"$push": {"status": "$_id", "orders_count": "$orders_count"}},
            "total": {"$sum": "$orders_count"},
        }},
        {"$unwind": "$statuses"},
        {"$project": {
            "_id": 0,
            "status": "$statuses.status",
            "orders_count": "$statuses.orders_count",
            "percentage": {
                "$round": [{"$multiply": [{"$divide": ["$statuses.orders_count", "$total"]}, 100]}, 2]
            },
        }},
        {"$sort": {"orders_count": -1}},
    ]


AGGREGATIONS = {
    "sales_by_city": {
        "collection": VALIDATED_COLLECTION,
        "build": _build_sales_by_city,
        "description": "إجمالي المبيعات وعدد الطلبات ومتوسط قيمة الطلب حسب المدينة.",
        "example_params": {"limit": 20},
    },
    "top_products": {
        "collection": VALIDATED_COLLECTION,
        "build": _build_top_products,
        "description": "أفضل المنتجات حسب الإيراد الإجمالي (من عناصر items).",
        "example_params": {"limit": 10},
    },
    "top_customers": {
        "collection": VALIDATED_COLLECTION,
        "build": _build_top_customers,
        "description": "أفضل العملاء حسب إجمالي ما أنفقوه عبر كل طلباتهم.",
        "example_params": {"limit": 10},
    },
    "sales_by_period": {
        "collection": VALIDATED_COLLECTION,
        "build": _build_sales_by_period,
        "description": "المبيعات وعدد الطلبات مجمّعة حسب الفترة الزمنية (شهر/يوم).",
        "example_params": {"granularity": "month"},
    },
    "orders_status_distribution": {
        "collection": VALIDATED_COLLECTION,
        "build": _build_orders_status_distribution,
        "description": "توزيع عدد ونسبة الطلبات حسب حالة الطلب (status).",
        "example_params": {},
    },
}


def list_aggregations():
    return {
        name: {"description": spec["description"], "example_params": spec["example_params"]}
        for name, spec in AGGREGATIONS.items()
    }


def run_aggregation(db, name, params=None):
    params = params or {}
    spec = AGGREGATIONS[name]
    pipeline = spec["build"](params)
    return list(db[spec["collection"]].aggregate(pipeline))


def _cli():
    parser = argparse.ArgumentParser(description="Run / list aggregation reports")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--run", help="aggregation name to run")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    if args.list:
        print(json.dumps(list_aggregations(), ensure_ascii=False, indent=2))
        return

    from pymongo import MongoClient
    client = MongoClient(MONGO_URI)
    db = client[MONGO_DATABASE]
    try:
        if args.run:
            params = {"limit": args.limit} if args.limit else {}
            result = run_aggregation(db, args.run, params)
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        else:
            parser.print_help()
    finally:
        client.close()


if __name__ == "__main__":
    _cli()
