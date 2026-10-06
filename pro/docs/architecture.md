# معمارية خط البيانات

## نظرة عامة

```
CSV (dirty)
    |
    v
File Router (file_router.py) --- id_run created in main.py
    | size <= 200MB?
    +--- yes --> Python Batch (batch_loader.py)  ---+
    +--- no  --> PySpark (spark_loader.py)        ---+
                                                       |
                                                       v
                                                 orders_raw
                                            (no filtering, ELT)
                                                       |
                                                       v
                                     Quality & Classification
                                        (quality_rules.py via
                                         elt_pipeline.py)
                                            |          |
                                     valid/corrected  quarantined
                                            |          |
                                            v          v
                                 orders_validated   orders_quarantine
                                  (Upsert on order_id)
                                                       |
                                                       v
                                          reports/results.json
                                             (metrics.py)
```

## قرار المحرك (File Router)

`file_router.select_engine()` يقرأ حجم الملف بالميغابايت ويقارنه بـ
`SMALL_FILE_THRESHOLD_MB` (200 افتراضياً). القرار وسببه يُطبعان دائماً
قبل بدء التحميل.

## طبقة Raw (ELT)

كل سجل يصل إلى `orders_raw` بحقول التتبع التالية بغض النظر عن جودته:

| الحقل | الوصف |
|---|---|
| `id_run` | معرف فريد للتشغيل (uuid4)، يُنشأ في `main.py` |
| `file_source` | مسار/اسم الملف المصدر |
| `number_row_source` | رقم الصف في الملف المصدر |
| `at_ingested` | وقت التحميل (UTC) |
| `engine_used` | `python_batch` أو `pyspark` |
| `record_raw` | كل الحقول الأصلية كما وصلت (بدون أي تحويل) |

لا يوجد Validator ولا Unique Index على هذه المجموعة (متطلب 6.9) حتى لا
يُرفض أي سجل أثناء التحميل الأولي.

## التنظيف والتصنيف

`quality_rules.classify_record()` يطبّق 9 قواعد تصحيح آلي (أكثر من
الحد الأدنى المطلوب وهو 8):

1. الأرقام العربية -> لاتينية
2. رمز/اسم العملة -> توحيد (مثال: YER)
3. فواصل الآلاف -> رقم
4. السعر بالكلمات (قائمة محدودة معروفة) -> رقم
5. رقم الهاتف -> إزالة المسافات وتوحيد الصيغة
6. البريد الإلكتروني -> إصلاح التكرار الواضح فقط
7. التاريخ -> صيغة ISO قياسية (مع كشف التواريخ المستحيلة)
8. المسافات والمرادفات (حالة الطلب) -> Trim + قاموس قياسي
9. إجمالي الطلب -> إعادة الحساب من العناصر + التوصيل عند التعارض

كل تصحيح يُسجَّل في `corrections[]` بالشكل الموثق في القسم 6.7 من
وثيقة التكليف (`field`, `original_value`, `corrected_value`, `rule_code`).

## قرار العزل (Quarantine)

الأخطاء الجوهرية المكتشفة (قسم 6.8 من التكليف): `ID_ORDER_MISSING`,
`ID_CUSTOMER_MISSING`, `DATE_IMPOSSIBLE_INVALID`, `JSON_ITEMS_CORRUPTED`,
`ITEMS_EMPTY`, `PRICE_UNKNOWN`, `VALUE_NEGATIVE_AMBIGUOUS`,
`ID_ORDER_DUPLICATE`, `ERRORS_CONFLICTING_MULTIPLE`.

- خطأ جوهري واحد -> يُستخدم كوده مباشرة.
- خطآن أو أكثر -> `ERRORS_CONFLICTING_MULTIPLE` مع سرد كل الأكواد في
  `codes_error`.

## Idempotency و Upsert

- `orders_validated` لها Unique Index على `order_id` (مفتاح العمل
  الثابت المطلوب في 6.10).
- الكتابة تتم عبر `UpdateOne(..., upsert=True)` ضمن `bulk_write`
  (`elt_pipeline._flush_validated`)، وليس `insert` متبوعاً بفحص.
- كل تشغيل يُحصي `count_inserted` (سجلات جديدة)، `count_updated`
  (سجلات موجودة تغيّرت)، و`count_unchanged` (سجلات موجودة بنفس القيم).
- `orders_raw` تبقى طبقة تتبع تاريخية: يجوز أن تتراكم محاولات تحميل
  متعددة لنفس البيانات عبر id_run مختلفة، بدون أن يؤثر ذلك على تفرد
  `orders_validated`.

## قاعدة الاتساق (6.11)

لكل `id_run`: `loaded_raw == count_valid + count_corrected + count_quarantine`.
يُتحقق منها تلقائياً في `metrics.RunMetrics.check_consistency()` ويُطبع
تحذير إن فشلت.
