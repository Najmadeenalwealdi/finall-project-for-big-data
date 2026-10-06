"""
queries.py

المتطلب الجديد (1): 5 استعلامات عملية على الأقل + تنفيذ
explain("executionStats") لـ3 استعلامات قبل وبعد إنشاء الفهارس.

كل استعلام معرّف مرة واحدة في QUERY_DEFINITIONS (الفلتر + الترتيب)
ويُستخدم من ثلاث جهات بدون تكرار منطق: run_query() (تنفيذ فعلي)،
explain_query() (قياس أداء)، و api.py (واجهة FastAPI).

تشغيل مباشر:
    python src/queries.py --list
    python src/queries.py --run orders_by_status --status "مؤكد" --limit 5
    python src/queries.py --explain-demo        # Q1/Q2/Q3 قبل وبعد الفهارس
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from config.settings import MONGO_URI, MONGO_DATABASE, VALIDATED_COLLECTION
from indexes import create_indexes, drop_indexes, INDEX_SPECS


# ============================================================
# تعريف الاستعلامات (اسم -> دالة تبني (filter, sort) من المعاملات)
# ============================================================

def _orders_by_status(params):
    status = params.get("status", "مؤكد")
    return {"status": status}, [("order_date", -1)]


def _orders_by_customer(params):
    customer_id = params.get("customer_id", "")
    return {"customer_id": customer_id}, [("order_date", -1)]


def _high_value_orders_by_city(params):
    city = params.get("city", "")
    min_amount = float(params.get("min_amount", 1000))
    return {"city": city, "total_amount": {"$gte": min_amount}}, [("total_amount", -1)]


def _orders_by_payment(params):
    payment_method = params.get("payment_method", "")
    payment_status = params.get("payment_status", "")
    filt = {}
    if payment_method:
        filt["payment_method"] = payment_method
    if payment_status:
        filt["payment_status"] = payment_status
    return filt, [("order_date", -1)]


def _orders_needing_review(params):
    return {"quality_status": "corrected"}, [("last_updated_at", -1)]


QUERY_DEFINITIONS = {
    "orders_by_status": {
        "collection": VALIDATED_COLLECTION,
        "build": _orders_by_status,
        "description": "كل الطلبات بحالة معينة (status)، الأحدث أولاً.",
        "example_params": {"status": "مؤكد", "limit": 10},
        "served_by_index": "idx_status_order_date",
    },
    "orders_by_customer": {
        "collection": VALIDATED_COLLECTION,
        "build": _orders_by_customer,
        "description": "سجل كل طلبات عميل واحد (customer_id)، الأحدث أولاً.",
        "example_params": {"customer_id": "CUST001", "limit": 10},
        "served_by_index": "idx_customer_order_date",
    },
    "high_value_orders_by_city": {
        "collection": VALIDATED_COLLECTION,
        "build": _high_value_orders_by_city,
        "description": "الطلبات عالية القيمة (total_amount >= min_amount) في مدينة معينة.",
        "example_params": {"city": "صنعاء", "min_amount": 1000, "limit": 10},
        "served_by_index": "idx_city_total_amount",
    },
    "orders_by_payment": {
        "collection": VALIDATED_COLLECTION,
        "build": _orders_by_payment,
        "description": "الطلبات حسب طريقة الدفع و/أو حالة الدفع.",
        "example_params": {"payment_method": "كاش", "payment_status": "مدفوع", "limit": 10},
        "served_by_index": None,  # عمداً بدون فهرس مخصص - انظر indexes.py
    },
    "orders_needing_review": {
        "collection": VALIDATED_COLLECTION,
        "build": _orders_needing_review,
        "description": "الطلبات التي تم تصحيحها تلقائياً (quality_status=corrected) لمراجعة بشرية.",
        "example_params": {"limit": 10},
        "served_by_index": "idx_quality_status",
    },
}

# الاستعلامات الثلاثة المستخدمة في عرض before/after explain (القسم 1، البند 3)
EXPLAIN_DEMO_QUERIES = ["orders_by_status", "orders_by_customer", "high_value_orders_by_city"]


def list_queries():
    return {
        name: {
            "description": spec["description"],
            "example_params": spec["example_params"],
            "served_by_index": spec["served_by_index"],
        }
        for name, spec in QUERY_DEFINITIONS.items()
    }


def run_query(db, name, params=None, limit=10):
    params = params or {}
    spec = QUERY_DEFINITIONS[name]
    filt, sort = spec["build"](params)
    cursor = db[spec["collection"]].find(filt, {"_id": 0}).sort(sort).limit(limit)
    return list(cursor)


def explain_query(db, name, params=None, limit=10):
    """ينفّذ explain('executionStats') على استعلام واحد ويُرجع ملخصاً مقروءاً."""
    params = params or {}
    spec = QUERY_DEFINITIONS[name]
    filt, sort = spec["build"](params)

    command = {
        "find": spec["collection"],
        "filter": filt,
        "sort": dict(sort),
        "limit": limit,
    }
    raw = db.command("explain", command, verbosity="executionStats")

    exec_stats = raw.get("executionStats", {})
    winning_plan = raw.get("queryPlanner", {}).get("winningPlan", {})

    def _stage_chain(plan):
        stages = []
        node = plan
        while isinstance(node, dict):
            stages.append(node.get("stage"))
            node = node.get("inputStage")
        return stages

    return {
        "query": name,
        "filter": filt,
        "sort": dict(sort),
        "stage_chain": _stage_chain(winning_plan),
        "used_index": winning_plan.get("inputStage", {}).get("indexName")
        or winning_plan.get("indexName"),
        "totalDocsExamined": exec_stats.get("totalDocsExamined"),
        "totalKeysExamined": exec_stats.get("totalKeysExamined"),
        "nReturned": exec_stats.get("nReturned"),
        "executionTimeMillis": exec_stats.get("executionTimeMillis"),
    }


def run_explain_demo(db):
    """
    يشغّل explain('executionStats') لـ3 استعلامات (EXPLAIN_DEMO_QUERIES)
    قبل إنشاء الفهارس ثم بعدها، ويطبع مقارنة واضحة - يحقق متطلب
    'explain لعدد 3 استعلامات قبل وبعد إنشاء الفهارس' بالضبط.
    """
    print("=" * 70)
    print("EXPLAIN DEMO: before vs after indexes (3 queries)")
    print("=" * 70)

    # تأكد أن الفهارس الثلاثة قيد الاختبار غير موجودة أولاً
    drop_indexes(db)

    before = {}
    for name in EXPLAIN_DEMO_QUERIES:
        params = QUERY_DEFINITIONS[name]["example_params"]
        before[name] = explain_query(db, name, params)

    create_indexes(db)

    after = {}
    for name in EXPLAIN_DEMO_QUERIES:
        params = QUERY_DEFINITIONS[name]["example_params"]
        after[name] = explain_query(db, name, params)

    for name in EXPLAIN_DEMO_QUERIES:
        b, a = before[name], after[name]
        print(f"\n--- {name} ---")
        print(f"  BEFORE indexes : stages={b['stage_chain']} "
              f"docsExamined={b['totalDocsExamined']} keysExamined={b['totalKeysExamined']} "
              f"time={b['executionTimeMillis']}ms")
        print(f"  AFTER  indexes : stages={a['stage_chain']} "
              f"index={a['used_index']} docsExamined={a['totalDocsExamined']} "
              f"keysExamined={a['totalKeysExamined']} time={a['executionTimeMillis']}ms")
        if b["totalDocsExamined"] and a["totalDocsExamined"] is not None:
            print(
                f"  => Docs examined reduced from {b['totalDocsExamined']} to "
                f"{a['totalDocsExamined']} after indexing."
            )

    print("=" * 70)
    return {"before": before, "after": after}


def _cli():
    parser = argparse.ArgumentParser(description="Run / list / explain project queries")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--run", help="query name to run")
    parser.add_argument("--explain", help="query name to explain")
    parser.add_argument("--explain-demo", action="store_true")
    parser.add_argument("--status")
    parser.add_argument("--customer_id")
    parser.add_argument("--city")
    parser.add_argument("--min_amount")
    parser.add_argument("--payment_method")
    parser.add_argument("--payment_status")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    if args.list:
        print(json.dumps(list_queries(), ensure_ascii=False, indent=2))
        return

    from pymongo import MongoClient
    client = MongoClient(MONGO_URI)
    db = client[MONGO_DATABASE]
    try:
        params = {
            k: v for k, v in {
                "status": args.status, "customer_id": args.customer_id,
                "city": args.city, "min_amount": args.min_amount,
                "payment_method": args.payment_method, "payment_status": args.payment_status,
            }.items() if v is not None
        }

        if args.explain_demo:
            run_explain_demo(db)
        elif args.explain:
            print(json.dumps(explain_query(db, args.explain, params, args.limit), ensure_ascii=False, indent=2, default=str))
        elif args.run:
            results = run_query(db, args.run, params, args.limit)
            print(json.dumps(results, ensure_ascii=False, indent=2, default=str))
        else:
            parser.print_help()
    finally:
        client.close()


if __name__ == "__main__":
    _cli()
