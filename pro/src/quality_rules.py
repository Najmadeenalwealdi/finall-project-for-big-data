"""
quality_rules.py

قواعد التنظيف الآلي (8 قواعد على الأقل) + منطق التصنيف
(Valid / Corrected / Quarantine) + Audit Trail لكل تصحيح.

كل دالة rule_* تُرجع (value, corrected: bool) — القيمة بعد المحاولة،
وهل تم تصحيحها فعلياً أم أنها وصلت سليمة أصلاً.

الدالة الرئيسية classify_record() هي نقطة الدخول التي يستخدمها
batch_loader.py و spark_loader.py (عبر elt_pipeline.py) لتصنيف كل سجل خام.
"""

import json
import re
from datetime import datetime

from config.settings import QUARANTINE_CODES, ITEM_QUANTITY_KEYS, ITEM_UNIT_PRICE_KEYS


# ============================================================
# أدوات مساعدة عامة
# ============================================================

ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

WORD_NUMBERS = {
    "الف": 1000, "ألف": 1000,
    "الفان": 2000, "ألفان": 2000, "ألفين": 2000, "الفين": 2000,
    "ثلاثة آلاف": 3000, "ثلاثة الاف": 3000,
    "اربعة آلاف": 4000, "أربعة آلاف": 4000, "اربعة الاف": 4000,
    "خمسة آلاف": 5000, "خمسة الاف": 5000,
    "ستة آلاف": 6000, "ستة الاف": 6000,
    "سبعة آلاف": 7000, "سبعة الاف": 7000,
    "ثمانية آلاف": 8000, "ثمانية الاف": 8000,
    "تسعة آلاف": 9000, "تسعة الاف": 9000,
    "عشرة آلاف": 10000, "عشرة الاف": 10000,
    "مئة": 100, "مية": 100,
    "الفين وخمسمئة": 2500,
}

CURRENCY_SYNONYMS = {
    "لاير": "YER", "ريال": "YER", "ريال يمني": "YER", "لاير يمني": "YER",
    "yer": "YER", "yr": "YER",
    "دولار": "USD", "usd": "USD", "$": "USD",
    "سعودي": "SAR", "ريال سعودي": "SAR", "sar": "SAR",
}

# ملاحظة: لا نترجم الحالة من عربي لإنجليزي - القيم الكنسية الفعلية في بيانات
# المشروع عربية (مؤكد، مدفوع، ملغي، قيد الشحن، قيد الانتظار، تم التسليم،
# مرتجع...) وهذا ما تستخدمه أمثلة المواصفة نفسها. هذا القاموس يبقى فارغاً
# ويُستخدم فقط إذا اكتُشفت مستقبلاً اختلافات إملائية حقيقية يجب توحيدها
# (نفس القيمة الكنسية، كتابة مختلفة) - وليس للترجمة بين لغتين.
STATUS_SYNONYMS = {}


def _clean_text(value):
    if value is None:
        return ""
    return str(value).strip()


# ============================================================
# القاعدة 1: الأرقام العربية -> لاتينية
# ============================================================

def rule_arabic_numerals(value):
    text = _clean_text(value)
    if not text:
        return text, False
    converted = text.translate(ARABIC_DIGITS)
    return converted, converted != text


# ============================================================
# القاعدة 2: رمز/اسم العملة -> توحيد إلى رمز ISO (مثلاً YER)
# ============================================================

def rule_currency(value):
    text = _clean_text(value)
    if not text:
        return None, False
    key = text.lower().strip()
    if key in CURRENCY_SYNONYMS:
        normalized = CURRENCY_SYNONYMS[key]
        return normalized, normalized != text
    upper = text.upper()
    if upper in {"YER", "USD", "SAR", "EUR"}:
        return upper, upper != text
    return text, False


# ============================================================
# القاعدة 3: فواصل الآلاف -> رقم صحيح
# ============================================================

def rule_thousands_separator(value):
    text = _clean_text(value)
    if not text:
        return value, False
    if "," in text:
        stripped = text.replace(",", "")
        try:
            float(stripped)
            return stripped, True
        except ValueError:
            return value, False
    return value, False


# ============================================================
# القاعدة 4: السعر بالكلمات -> رقم (قيم معروفة محددة فقط)
# ============================================================

def rule_price_in_words(value):
    text = _clean_text(value)
    if not text:
        return value, False
    key = text.strip()
    if key in WORD_NUMBERS:
        return str(WORD_NUMBERS[key]), True
    return value, False


# ============================================================
# دمج قواعد 1+2+3+4 في محلل سعر واحد يُرجع float أو None
# ============================================================

def parse_price(raw_value):
    if raw_value is None or _clean_text(raw_value) == "":
        return None, False, []

    original = _clean_text(raw_value)
    corrected_any = False
    applied = []

    value, changed = rule_arabic_numerals(original)
    if changed:
        corrected_any = True
        applied.append("ARABIC_NUMERALS")

    value2, changed2 = rule_price_in_words(value)
    if changed2:
        value = value2
        corrected_any = True
        applied.append("PRICE_IN_WORDS")

    value_no_currency = re.sub(
        r"(لاير|ريال|دولار|usd|yer|sar|\$)", "", value, flags=re.IGNORECASE
    ).strip()
    if value_no_currency != value:
        corrected_any = True
        applied.append("CURRENCY_TEXT_STRIPPED")
        value = value_no_currency

    value3, changed3 = rule_thousands_separator(value)
    if changed3:
        value = value3
        corrected_any = True
        applied.append("THOUSANDS_SEPARATOR")

    value = value.strip()
    try:
        price = float(value)
    except ValueError:
        return None, corrected_any, applied

    return price, corrected_any, applied


# ============================================================
# القاعدة 5: رقم الهاتف -> إزالة المسافات وتوحيد الصيغة
# ============================================================

def rule_phone(value):
    text = _clean_text(value)
    if not text:
        return value, False
    original = text
    text = text.translate(ARABIC_DIGITS)
    cleaned = re.sub(r"[^\d+]", "", text)
    if cleaned.count("+") > 1 or (cleaned.count("+") == 1 and not cleaned.startswith("+")):
        cleaned = "+" + cleaned.replace("+", "")
    changed = cleaned != original
    return cleaned, changed


# ============================================================
# القاعدة 6: البريد الإلكتروني -> إصلاح التكرار الواضح فقط
# ============================================================

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def rule_email(value):
    text = _clean_text(value)
    if not text:
        return value, False, False

    original = text
    fixed = text.replace(" ", "")
    fixed = re.sub(r"@{2,}", "@", fixed)
    fixed = re.sub(r"\.{2,}", ".", fixed)

    corrected = fixed != original
    is_valid = bool(EMAIL_PATTERN.match(fixed))
    return fixed, corrected, is_valid


# ============================================================
# القاعدة 7: التاريخ -> صيغة قياسية ISO (YYYY-MM-DD)
# ============================================================

DATE_FORMATS = [
    "%Y-%m-%d", "%Y/%m/%d",
    "%d-%m-%Y", "%d/%m/%Y",
    "%m-%d-%Y", "%m/%d/%Y",
    "%Y.%m.%d", "%d.%m.%Y",
]

# تاريخ/تاريخ+وقت بصيغة ISO صحيحة أصلاً (مثل "2025-02-24T21:29:00").
# وجود هذه الصيغة في البيانات الأصلية هو الوضع الطبيعي المتوقع لكل طلب
# (كل الطلبات لها طابع زمني) - لذا لا يُعتبر "تصحيحاً" مجرد اقتصاص الوقت
# لتخزين التاريخ فقط، إلا إذا كانت القيمة الأصلية تحتوي أرقاماً عربية
# (دليل فعلي على أن القيمة الخام كانت تحتاج تطبيعاً).
ISO_DATE_TIME_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2})?(\.\d+)?)?$"
)


def rule_date(value):
    text = _clean_text(value)
    if not text:
        return None, False

    original = text
    had_arabic_digits = any(ch in "٠١٢٣٤٥٦٧٨٩" for ch in text)
    normalized_text = text.translate(ARABIC_DIGITS).strip()

    if ISO_DATE_TIME_PATTERN.match(normalized_text):
        iso = normalized_text[:10]
        corrected = had_arabic_digits
        return iso, corrected

    for fmt in DATE_FORMATS:
        try:
            parsed = datetime.strptime(normalized_text, fmt)
            iso = parsed.strftime("%Y-%m-%d")
            return iso, True
        except ValueError:
            continue

    try:
        parsed = datetime.fromisoformat(normalized_text.replace("Z", ""))
        iso = parsed.strftime("%Y-%m-%d")
        return iso, True
    except ValueError:
        pass

    return None, False


def is_impossible_date(iso_date_str):
    if iso_date_str is None:
        return True
    try:
        parsed = datetime.strptime(iso_date_str, "%Y-%m-%d")
    except ValueError:
        return True
    if parsed.year < 2000 or parsed.year > 2100:
        return True
    return False


# ============================================================
# القاعدة 8: المسافات والمرادفات -> Trim + توحيد إلى قاموس قياسي
# ============================================================

def rule_status(value):
    original = "" if value is None else str(value)
    text = _clean_text(value)
    if not text:
        return value, False
    trimmed = text.strip()
    key = trimmed.lower()
    if key in STATUS_SYNONYMS:
        normalized = STATUS_SYNONYMS[key]
    elif trimmed in STATUS_SYNONYMS:
        normalized = STATUS_SYNONYMS[trimmed]
    else:
        normalized = trimmed
    return normalized, normalized != original


# ============================================================
# القاعدة 9: إجمالي الطلب -> إعادة الحساب من العناصر + التوصيل
# ============================================================

def parse_items_json(raw_value):
    text = _clean_text(raw_value)
    if not text:
        return None, "JSON_ITEMS_CORRUPTED"
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None, "JSON_ITEMS_CORRUPTED"

    if not isinstance(parsed, list):
        return None, "JSON_ITEMS_CORRUPTED"

    if len(parsed) == 0:
        return [], "ITEMS_EMPTY"

    return parsed, None


_MISSING = object()


def _first_present(item_dict, candidate_keys):
    """يجرب كل مفتاح من candidate_keys بالترتيب. يرجع _MISSING إذا لا يوجد أي منها."""
    for key in candidate_keys:
        if key in item_dict and item_dict[key] not in (None, ""):
            return item_dict[key]
    return _MISSING


def rule_recompute_total(items, delivery_fee, stated_total):
    try:
        computed = 0.0
        for item in items:
            if not isinstance(item, dict):
                return stated_total, False

            unit_price_raw = _first_present(item, ITEM_UNIT_PRICE_KEYS)
            if unit_price_raw is _MISSING:
                # اسم مفتاح السعر داخل items غير معروف/غير متطابق مع
                # ITEM_UNIT_PRICE_KEYS في settings.py - لا نخمن القيمة،
                # نتجاهل إعادة الحساب لهذا السجل بدل تصحيحه خطأً.
                return stated_total, False

            qty_raw = _first_present(item, ITEM_QUANTITY_KEYS)
            qty = 1.0 if qty_raw is _MISSING else float(qty_raw)
            unit_price = float(unit_price_raw)

            if qty < 0 or unit_price < 0:
                return stated_total, False
            computed += qty * unit_price
        fee = float(delivery_fee) if delivery_fee not in (None, "") else 0.0
        if fee < 0:
            return stated_total, False
        computed += fee
        computed = round(computed, 2)
    except (TypeError, ValueError, AttributeError):
        return stated_total, False

    if stated_total is None:
        return computed, True

    try:
        stated = round(float(stated_total), 2)
    except (TypeError, ValueError):
        return computed, True

    if abs(stated - computed) > 0.01:
        return computed, True

    return stated, False


# ============================================================
# التصنيف الرئيسي
# ============================================================

def classify_record(raw_record, column_map, seen_order_ids=None):
    """
    يأخذ raw_record (dict من أسماء أعمدة CSV الأصلية إلى القيم النصية الخام)
    ويُرجع dict فيه:
      quality_status: "valid" | "corrected" | "quarantined"
      cleaned: dict بالحقول بعد التنظيف (للحالتين valid/corrected)
      corrections: list من audit trail entries
      quarantine_code: str أو None
      quarantine_reason: str أو None

    seen_order_ids: dict اختياري {order_id: fingerprint} لاكتشاف
    التكرار المتضارب داخل نفس الملف (ID_ORDER_DUPLICATE).
    """
    corrections = []
    errors = []

    def get(field):
        return raw_record.get(column_map.get(field, field))

    order_id_raw = _clean_text(get("order_id"))
    if not order_id_raw:
        errors.append("ID_ORDER_MISSING")
        order_id = None
    else:
        order_id = order_id_raw

    customer_id_raw = _clean_text(get("customer_id"))
    if not customer_id_raw:
        errors.append("ID_CUSTOMER_MISSING")
    customer_id = customer_id_raw or None

    date_raw = get("order_date")
    iso_date, date_corrected = rule_date(date_raw)
    if iso_date is None or is_impossible_date(iso_date):
        errors.append("DATE_IMPOSSIBLE_INVALID")
    elif date_corrected:
        corrections.append({
            "field": "order_date",
            "original_value": _clean_text(date_raw),
            "corrected_value": iso_date,
            "rule_code": "DATE_NORMALIZED",
        })

    items_raw = get("items")
    items, items_error = parse_items_json(items_raw)
    if items_error:
        errors.append(items_error)

    total_raw = get("total_amount")
    total_price, total_corrected_flag, total_rules = parse_price(total_raw)

    if total_price is None and (items is None or len(items) == 0):
        errors.append("PRICE_UNKNOWN")
    elif total_price is not None and total_price < 0:
        errors.append("VALUE_NEGATIVE_AMBIGUOUS")

    if total_corrected_flag and total_price is not None:
        corrections.append({
            "field": "total_amount",
            "original_value": _clean_text(total_raw),
            "corrected_value": total_price,
            "rule_code": "+".join(total_rules) if total_rules else "PRICE_NORMALIZED",
        })

    currency_raw = get("currency")
    currency, currency_corrected = rule_currency(currency_raw)
    if currency_corrected:
        corrections.append({
            "field": "currency",
            "original_value": _clean_text(currency_raw),
            "corrected_value": currency,
            "rule_code": "CURRENCY_NORMALIZED",
        })

    phone_raw = get("customer_phone")
    phone, phone_corrected = rule_phone(phone_raw)
    if phone_corrected:
        corrections.append({
            "field": "customer_phone",
            "original_value": _clean_text(phone_raw),
            "corrected_value": phone,
            "rule_code": "PHONE_NORMALIZED",
        })

    email_raw = get("customer_email")
    email, email_corrected, email_valid = rule_email(email_raw)
    if email_corrected:
        corrections.append({
            "field": "customer_email",
            "original_value": _clean_text(email_raw),
            "corrected_value": email,
            "rule_code": "EMAIL_REPEATED_SYMBOLS",
        })

    status_raw = get("status")
    status, status_corrected = rule_status(status_raw)
    if status_corrected:
        corrections.append({
            "field": "status",
            "original_value": _clean_text(status_raw),
            "corrected_value": status,
            "rule_code": "STATUS_NORMALIZED",
        })

    delivery_raw = get("delivery_fee")
    if items and total_price is not None:
        recomputed_total, total_recomputed_flag = rule_recompute_total(
            items, delivery_raw, total_price
        )
        if total_recomputed_flag:
            corrections.append({
                "field": "total_amount",
                "original_value": total_price,
                "corrected_value": recomputed_total,
                "rule_code": "TOTAL_RECOMPUTED_FROM_ITEMS",
            })
            total_price = recomputed_total

    if order_id and seen_order_ids is not None:
        fingerprint = f"{customer_id}|{total_price}"
        previous = seen_order_ids.get(order_id)
        if previous is not None and previous != fingerprint:
            errors.append("ID_ORDER_DUPLICATE")
        seen_order_ids[order_id] = fingerprint

    if len(errors) >= 2:
        primary_code = "ERRORS_CONFLICTING_MULTIPLE"
        reason = (
            "أخطاء جوهرية متعددة: " + ", ".join(errors) + ". " +
            QUARANTINE_CODES["ERRORS_CONFLICTING_MULTIPLE"]
        )
        return {
            "quality_status": "quarantined",
            "cleaned": None,
            "corrections": corrections,
            "quarantine_code": primary_code,
            "quarantine_reason": reason,
            "codes_error": errors,
        }

    if len(errors) == 1:
        code = errors[0]
        return {
            "quality_status": "quarantined",
            "cleaned": None,
            "corrections": corrections,
            "quarantine_code": code,
            "quarantine_reason": QUARANTINE_CODES.get(code, code),
            "codes_error": errors,
        }

    # حقول وصفية إضافية (pass-through، بلا قواعد تحقق/تصحيح جوهرية) -
    # مطلوبة لتقارير الـAggregations في المشروع النهائي (المبيعات حسب
    # المدينة، إلخ) ولا تدخل في قرار Valid/Corrected/Quarantine.
    cleaned = {
        "order_id": order_id,
        "customer_id": customer_id,
        "customer_name": _clean_text(get("customer_name")) or None,
        "customer_email": email if email_valid else _clean_text(email_raw),
        "customer_phone": phone,
        "order_date": iso_date,
        "items": items,
        "currency": currency,
        "delivery_fee": delivery_raw,
        "delivery_type": _clean_text(get("delivery_type")) or None,
        "payment_method": _clean_text(get("payment_method")) or None,
        "payment_status": _clean_text(get("payment_status")) or None,
        "total_amount": total_price,
        "status": status,
        "city": _clean_text(get("city")) or None,
        "district": _clean_text(get("district")) or None,
    }

    quality_status = "corrected" if corrections else "valid"

    return {
        "quality_status": quality_status,
        "cleaned": cleaned,
        "corrections": corrections,
        "quarantine_code": None,
        "quarantine_reason": None,
        "codes_error": [],
    }
