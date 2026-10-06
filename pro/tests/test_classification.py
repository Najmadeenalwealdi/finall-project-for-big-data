"""
اختبارات وحدة لمنطق التصنيف classify_record() في quality_rules.py
تغطي مسارات: Valid / Corrected / Quarantine (بأسباب مختلفة) وتضارب التكرار.
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
sys.path.append(str(Path(__file__).resolve().parent.parent / "src"))

from quality_rules import classify_record

# خريطة أعمدة محايدة (identity map) خاصة بالاختبارات فقط: الاختبارات تفحص
# منطق التصنيف نفسه بغض النظر عن أسماء أعمدة أي ملف CSV حقيقي، لذلك لا
# نستورد COLUMN_MAP الفعلي من config/settings.py (ذاك مخصص لعمود CSV
# الحقيقي لدى المستخدم مثل "items_json" بدل "items").
COLUMN_MAP = {
    "order_id": "order_id",
    "order_date": "order_date",
    "status": "status",
    "customer_id": "customer_id",
    "customer_name": "customer_name",
    "customer_phone": "customer_phone",
    "customer_email": "customer_email",
    "city": "city",
    "district": "district",
    "delivery_type": "delivery_type",
    "delivery_fee": "delivery_fee",
    "payment_method": "payment_method",
    "payment_status": "payment_status",
    "payment_amount": "payment_amount",
    "currency": "currency",
    "total_amount": "total_amount",
    "items": "items",
}


def make_row(**overrides):
    row = {
        "order_id": "ORD001",
        "customer_id": "CUST001",
        "customer_email": "user@mail.com",
        "customer_phone": "+967771234567",
        "order_date": "2025-01-31",
        "items": json.dumps([{"quantity": 2, "unit_price": 100}]),
        "currency": "YER",
        "delivery_fee": "10",
        "total_amount": "210",
        "status": "confirmed",
    }
    row.update(overrides)
    return row


class TestClassifyRecord(unittest.TestCase):
    def test_clean_record_is_valid(self):
        result = classify_record(make_row(), COLUMN_MAP, seen_order_ids={})
        self.assertEqual(result["quality_status"], "valid")
        self.assertEqual(result["corrections"], [])
        self.assertIsNone(result["quarantine_code"])

    def test_fixable_record_is_corrected(self):
        row = make_row(total_amount="٢١٠", order_date="2025/01/31")
        result = classify_record(row, COLUMN_MAP, seen_order_ids={})
        self.assertEqual(result["quality_status"], "corrected")
        self.assertGreater(len(result["corrections"]), 0)

    def test_missing_order_id_is_quarantined(self):
        row = make_row(order_id="")
        result = classify_record(row, COLUMN_MAP, seen_order_ids={})
        self.assertEqual(result["quality_status"], "quarantined")
        self.assertEqual(result["quarantine_code"], "ID_ORDER_MISSING")

    def test_missing_customer_id_is_quarantined(self):
        row = make_row(customer_id="")
        result = classify_record(row, COLUMN_MAP, seen_order_ids={})
        self.assertEqual(result["quarantine_code"], "ID_CUSTOMER_MISSING")

    def test_corrupted_json_is_quarantined(self):
        row = make_row(items="{not valid json")
        result = classify_record(row, COLUMN_MAP, seen_order_ids={})
        self.assertEqual(result["quarantine_code"], "JSON_ITEMS_CORRUPTED")

    def test_empty_items_is_quarantined(self):
        row = make_row(items="[]")
        result = classify_record(row, COLUMN_MAP, seen_order_ids={})
        self.assertEqual(result["quarantine_code"], "ITEMS_EMPTY")

    def test_impossible_date_is_quarantined(self):
        row = make_row(order_date="2025-13-45")
        result = classify_record(row, COLUMN_MAP, seen_order_ids={})
        self.assertEqual(result["quarantine_code"], "DATE_IMPOSSIBLE_INVALID")

    def test_multiple_errors_use_conflicting_code(self):
        row = make_row(customer_id="", order_date="2025-99-99")
        result = classify_record(row, COLUMN_MAP, seen_order_ids={})
        self.assertEqual(result["quarantine_code"], "ERRORS_CONFLICTING_MULTIPLE")
        self.assertIn("ID_CUSTOMER_MISSING", result["codes_error"])
        self.assertIn("DATE_IMPOSSIBLE_INVALID", result["codes_error"])

    def test_conflicting_duplicate_order_id_detected(self):
        seen = {}
        row1 = make_row(order_id="DUP1", customer_id="A")
        row2 = make_row(order_id="DUP1", customer_id="B")
        r1 = classify_record(row1, COLUMN_MAP, seen_order_ids=seen)
        r2 = classify_record(row2, COLUMN_MAP, seen_order_ids=seen)
        self.assertEqual(r1["quality_status"], "valid")
        self.assertEqual(r2["quarantine_code"], "ID_ORDER_DUPLICATE")

    def test_consistent_duplicate_order_id_not_flagged(self):
        seen = {}
        row1 = make_row(order_id="DUP2")
        row2 = make_row(order_id="DUP2")
        r1 = classify_record(row1, COLUMN_MAP, seen_order_ids=seen)
        r2 = classify_record(row2, COLUMN_MAP, seen_order_ids=seen)
        self.assertEqual(r1["quality_status"], "valid")
        self.assertEqual(r2["quality_status"], "valid")


if __name__ == "__main__":
    unittest.main()
