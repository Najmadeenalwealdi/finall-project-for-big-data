"""
اختبارات وحدة لقواعد التنظيف الأساسية في quality_rules.py
تشغيل:  python -m pytest tests/ -v   (أو: python -m unittest discover tests)
"""

import sys
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
sys.path.append(str(Path(__file__).resolve().parent.parent / "src"))

from quality_rules import (
    rule_arabic_numerals,
    rule_currency,
    rule_thousands_separator,
    rule_price_in_words,
    parse_price,
    rule_phone,
    rule_email,
    rule_date,
    is_impossible_date,
    rule_status,
    parse_items_json,
    rule_recompute_total,
)


class TestArabicNumerals(unittest.TestCase):
    def test_converts_arabic_digits(self):
        value, corrected = rule_arabic_numerals("٥٠٠٠")
        self.assertEqual(value, "5000")
        self.assertTrue(corrected)

    def test_no_change_for_latin_digits(self):
        value, corrected = rule_arabic_numerals("5000")
        self.assertEqual(value, "5000")
        self.assertFalse(corrected)


class TestCurrency(unittest.TestCase):
    def test_normalizes_yemeni_rial_text(self):
        value, corrected = rule_currency("لاير يمني")
        self.assertEqual(value, "YER")
        self.assertTrue(corrected)

    def test_already_normalized(self):
        value, corrected = rule_currency("YER")
        self.assertEqual(value, "YER")
        self.assertFalse(corrected)


class TestThousandsSeparator(unittest.TestCase):
    def test_removes_commas(self):
        value, corrected = rule_thousands_separator("125,000.00")
        self.assertEqual(value, "125000.00")
        self.assertTrue(corrected)


class TestPriceInWords(unittest.TestCase):
    def test_known_word(self):
        value, corrected = rule_price_in_words("خمسة آلاف")
        self.assertEqual(value, "5000")
        self.assertTrue(corrected)

    def test_unknown_word_untouched(self):
        value, corrected = rule_price_in_words("سعر غير معروف")
        self.assertFalse(corrected)


class TestParsePrice(unittest.TestCase):
    def test_full_pipeline_arabic_currency_text(self):
        price, corrected, rules = parse_price("٥٠٠٠ لاير")
        self.assertEqual(price, 5000.0)
        self.assertTrue(corrected)

    def test_plain_number_not_corrected(self):
        price, corrected, rules = parse_price("210")
        self.assertEqual(price, 210.0)
        self.assertFalse(corrected)

    def test_unparseable_returns_none(self):
        price, corrected, rules = parse_price("غير معروف تماما")
        self.assertIsNone(price)


class TestPhone(unittest.TestCase):
    def test_removes_spaces_and_normalizes_plus(self):
        value, corrected = rule_phone("967+ 77 123 4567")
        self.assertEqual(value, "+9677712 34567".replace(" ", ""))
        self.assertTrue(corrected)


class TestEmail(unittest.TestCase):
    def test_fixes_repeated_symbols(self):
        value, corrected, valid = rule_email("user@@mail..com")
        self.assertEqual(value, "user@mail.com")
        self.assertTrue(corrected)
        self.assertTrue(valid)

    def test_already_valid_untouched(self):
        value, corrected, valid = rule_email("user@mail.com")
        self.assertFalse(corrected)
        self.assertTrue(valid)


class TestDate(unittest.TestCase):
    def test_slash_format(self):
        value, corrected = rule_date("2025/01/31")
        self.assertEqual(value, "2025-01-31")
        self.assertTrue(corrected)

    def test_already_iso_not_corrected(self):
        value, corrected = rule_date("2025-01-31")
        self.assertEqual(value, "2025-01-31")
        self.assertFalse(corrected)

    def test_impossible_date_flagged_by_is_impossible_date(self):
        # rule_date نفسها لا تتحقق من منطقية التاريخ (ذلك عمل
        # is_impossible_date المستخدمة في classify_record) - فقط تطبّع
        # الصيغة. "2025-13-45" يطابق شكل ISO فيُعاد كما هو، ثم تكتشف
        # is_impossible_date أنه تاريخ مستحيل (شهر/يوم غير صالحين).
        value, corrected = rule_date("2025-13-45")
        self.assertTrue(is_impossible_date(value))

    def test_is_impossible_date_flags_none(self):
        self.assertTrue(is_impossible_date(None))


class TestStatus(unittest.TestCase):
    def test_extra_whitespace_is_corrected(self):
        value, corrected = rule_status(" مؤكد ")
        self.assertEqual(value, "مؤكد")
        self.assertTrue(corrected)

    def test_already_canonical_not_corrected(self):
        # القيم الكنسية الفعلية في بيانات المشروع عربية - لا تُترجم للإنجليزية
        value, corrected = rule_status("مؤكد")
        self.assertEqual(value, "مؤكد")
        self.assertFalse(corrected)

    def test_unknown_status_passed_through_unflagged(self):
        value, corrected = rule_status("حالة غير معروفة تمامًا")
        self.assertEqual(value, "حالة غير معروفة تمامًا")
        self.assertFalse(corrected)


class TestItemsJson(unittest.TestCase):
    def test_valid_json_list(self):
        items, error = parse_items_json('[{"quantity": 1, "unit_price": 10}]')
        self.assertIsNone(error)
        self.assertEqual(len(items), 1)

    def test_corrupted_json(self):
        items, error = parse_items_json("{broken")
        self.assertEqual(error, "JSON_ITEMS_CORRUPTED")

    def test_empty_list(self):
        items, error = parse_items_json("[]")
        self.assertEqual(error, "ITEMS_EMPTY")


class TestRecomputeTotal(unittest.TestCase):
    def test_recomputes_when_mismatched(self):
        items = [{"quantity": 2, "unit_price": 100}]
        total, corrected = rule_recompute_total(items, "10", 999)
        self.assertEqual(total, 210.0)
        self.assertTrue(corrected)

    def test_matches_no_correction(self):
        items = [{"quantity": 2, "unit_price": 100}]
        total, corrected = rule_recompute_total(items, "10", 210)
        self.assertFalse(corrected)


if __name__ == "__main__":
    unittest.main()
