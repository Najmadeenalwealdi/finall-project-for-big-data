# Data Pipeline — خط بيانات هجين لمعالجة بيانات الطلبات (Phase 1 + Phase 2)

مشروع مقرر البيانات الضخمة - العملي، بمرحلتيه:

- **Phase 1 (المشروع النصفي)**: خط بيانات هجين يستقبل ملف CSV غير نظيف
  لبيانات طلبات متجر إلكتروني، يختار محرك المعالجة تلقائياً (Python Batch
  أو PySpark) حسب حجم الملف، يحمّل البيانات خام إلى MongoDB (نمط ELT)، ثم
  ينظفها ويصنفها إلى Valid / Corrected / Quarantine مع ضمان Idempotency
  وUpsert. (الأقسام 1-9 أدناه، تُقيَّم كما هي بلا تطوير إضافي.)
- **Phase 2 (المشروع النهائي)**: استكمال فوق نفس البيانات: استعلامات
  وفهارس، تقارير Aggregation، Materialized Views بتحديث تزايدي، مهام
  مجدولة، وواجهة FastAPI موحّدة لتشغيل كل ما سبق. (الأقسام 10-15 أدناه.)

## 1. المتطلبات (Prerequisites)

- Python 3.10+
- MongoDB Server يعمل محلياً (افتراضياً على `mongodb://localhost:27017`)
- (اختياري، فقط عند تشغيل الملف الكبير) Java 8/11/17 + Apache Spark 3.5.x
  متوافق مع إصدار `pyspark` في requirements.txt

## 2. التثبيت

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## 3. الإعداد قبل أول تشغيل

### 3.1 تحديد مسار الملف الحقيقي

الأعمدة الافتراضية في `config/settings.py` (قسم `COLUMN_MAP`) مبنية على
وصف المشروع فقط. **الخطوة الأولى الإلزامية:**

```bash
python src/inspect_data.py
```

عدّل هذا السكربت ليقرأ ملفك الحقيقي (أو انسخ عينة صغيرة أولاً - انظر 3.2)،
اطّلع على أسماء الأعمدة الفعلية، ثم عدّل `COLUMN_MAP` في `config/settings.py`
(أو مرّرها كمتغيرات بيئة `COL_ORDER_ID`, `COL_CUSTOMER_ID`, ... إلخ) لتطابق
ملفك تماماً.

### 3.2 تحديد مسار الملف الضخم الأصلي

```bash
export ORIGINAL_FILE="/path/to/orders_huge_mixed_quality.csv"     # Linux/Mac
set ORIGINAL_FILE=D:\big data file\orders_huge_mixed_quality.csv  # Windows
```

### 3.3 إنشاء العينة الصغيرة القابلة لإعادة الإنتاج

```bash
python src/create_small_sample.py --input "$ORIGINAL_FILE" --rows 100000
```

ينتج `data/orders_sample_100000.csv` (لا يُنشأ يدوياً بواسطة Excel، عدد
الصفوف قابل للتغيير عبر `--rows`).

## 4. التشغيل

### تشغيل العينة الصغيرة (يجب أن يختار Router محرك `python_batch`)

```bash
python src/main.py --file data/orders_sample_100000.csv
```

### تشغيل الملف الكبير (يجب أن يختار Router محرك `pyspark`)

```bash
python src/main.py --file "$ORIGINAL_FILE"
```

`main.py` هو نقطة التشغيل الرئيسية الوحيدة: يفحص حجم الملف، يختار
المحرك تلقائياً، يحمّل البيانات خام إلى `orders_raw`، ثم ينظفها ويصنفها
ويكتبها بـ Upsert إلى `orders_validated` أو `orders_quarantine`، ثم
يحفظ المقاييس في `reports/results.json`.

## 5. إثبات Idempotency و Upsert (إلزامي)

```bash
# 1) تشغيل أول
python src/main.py --file data/orders_sample_100000.csv
python src/count_validated.py

# 2) إعادة تشغيل نفس الملف بالضبط - يجب ألا يزيد عدد orders_validated
python src/main.py --file data/orders_sample_100000.csv --skip-setup
python src/count_validated.py
```

عدد `orders_validated` (distinct order_id) يجب أن يبقى كما هو بين
التشغيلين، وعدادات `count_inserted` في `reports/results.json` للتشغيل
الثاني يجب أن تكون صفراً تقريباً بينما `count_updated`/`count_unchanged`
هي التي ترتفع.

لإعادة الاختبار من الصفر: `python src/reset_db.py --yes`

## 6. أدوات مساعدة

| السكربت | الغرض |
|---|---|
| `src/inspect_data.py` | عرض أعمدة الملف وأول 5 سجلات |
| `src/debug_sample.py --file <csv> --n 10` | تجربة قواعد التنظيف بدون MongoDB |
| `src/compare_raw_vs_csv.py --file <csv> --id-run <uuid>` | مقارنة عدد صفوف CSV مع عدد سجلات orders_raw لنفس id_run |
| `src/count_validated.py` | عرض عدادات كل Collection والتحقق من عدم التكرار |
| `src/create_size_sample.py --input <csv> --target-mb <n>` | إنشاء عينة بحجم مستهدف بالميغابايت |
| `src/reset_db.py` | تفريغ Collections لإعادة الاختبار |

## 7. بنية المشروع

```
mid_datapipeline/
|-- README.md
|-- requirements.txt
|-- config/
|   `-- settings.py          # كل الإعدادات + COLUMN_MAP + QUARANTINE_CODES
|-- data/                    # ملفات CSV (غير مرفوعة على git)
|-- src/
|   |-- main.py               # نقطة التشغيل الرئيسية
|   |-- file_router.py        # اختيار المحرك حسب الحجم
|   |-- create_small_sample.py
|   |-- create_size_sample.py
|   |-- batch_loader.py       # Python Batch -> orders_raw
|   |-- spark_loader.py       # PySpark -> orders_raw
|   |-- quality_rules.py      # 9 قواعد تنظيف + classify_record()
|   |-- elt_pipeline.py       # التصنيف + Upsert -> validated/quarantine
|   |-- mongo_setup.py        # إنشاء Collections + Unique Index
|   |-- metrics.py            # RunMetrics + results.json
|   |-- reset_db.py / count_validated.py / compare_raw_vs_csv.py / debug_sample.py
|-- tests/
|   |-- test_cleaning_rules.py
|   `-- test_classification.py
|-- reports/
|   |-- results.json          # يُنشأ تلقائياً بعد كل تشغيل
|   `-- screenshots/          # لقطات MongoDB Compass و Spark UI (يدوي)
`-- docs/
    `-- architecture.md
```

## 8. تشغيل الاختبارات

```bash
python -m unittest discover tests -v
```

## 9. القرارات والافتراضات الموثقة

- **الحد الفاصل للمحرك**: 200MB (`SMALL_FILE_THRESHOLD_MB`) — أكبر من حجم
  العينة (100,000 سجل) بهامش أمان، وأصغر بكثير من الملف الضخم الفعلي.
- **البريد الإلكتروني**: يُصلح فقط التكرار الواضح (`@@`, `..`, مسافات).
  إذا بقي غير صالح بعد الإصلاح، لا يُعزل الطلب كاملاً بسببه وحده (الإيميل
  ليس مفتاح عمل)، بل يُحفظ كما وصل مع الإبقاء على بقية الحقول الصالحة.
- **التكرار (`ID_ORDER_DUPLICATE`)**: يُكتشف فقط عندما يحمل نفس `order_id`
  بيانات جوهرية متضاربة (عميل مختلف/مبلغ مختلف) داخل نفس الملف. تكرار
  متطابق البيانات لا يُعزل، ويُترك لـ Upsert التعامل معه بشكل طبيعي.
  عبر تشغيلات متعددة، هذا هو دور Upsert أصلاً (تحديث لا تكرار).
- **repartition في Spark**: لا يُستخدم افتراضياً؛ يُفعّل فقط عبر
  `SPARK_INPUT_PARTITIONS` في الإعدادات مع تبرير في هذا الملف.
- **`multiLine` في PySpark**: تم إزالته عمداً (كان يفرض قراءة الملف
  بـpartition واحدة فقط ويُسقط التوازي). بدّلناه بـ`quote`/`escape`، وهو
  كافٍ لحقل `items` المُقتبس في CSV. راجع `src/spark_loader.py`.
- **Upsert و"unchanged" الحقيقي**: `elt_pipeline.py` لا يكتب شيئاً إطلاقاً
  للسجلات غير المتغيرة فعلياً (بدل الاعتماد على `modified_count` الذي
  يتأثر بحقول التتبع). هذا ضروري لعمل `last_updated_at` كعلامة مائية
  (watermark) موثوقة يعتمد عليها التحديث التزايدي لـMaterialized Views
  في القسم 12 أدناه - وهو سبب إضافي (غير idempotency وحدها) لعدم لمس
  السجلات غير المتغيرة.

---

# Phase 2 — المشروع النهائي (الإضافات الجديدة، 7 درجات)

> يفترض هذا الجزء أن Phase 1 أعلاه يعمل بالفعل (MongoDB فيه بيانات في
> `orders_validated` من تشغيل `src/main.py` سابقاً). كل ما هنا يُبنى فوق
> `orders_validated` الموجود - لا تغيير على بوابة الإدخال (`src/main.py`
> / `run_pipeline`) سوى استدعائها من `POST /ingest` في القسم 14.

## 10. التثبيت الإضافي

تمت إضافة `fastapi`, `uvicorn`, `apscheduler`, `pydantic` إلى
`requirements.txt` الموجود مسبقاً - نفس أمر التثبيت في القسم 2 يكفي:

```bash
pip install -r requirements.txt
```

انسخ `.env.example` إلى `.env` وعدّله إذا احتجت (اختياري، كل المتغيرات
لها قيم افتراضية معقولة في `config/settings.py`).

## 11. الاستعلامات والفهارس + Explain

```bash
# عرض الاستعلامات المتاحة الخمسة
python src/queries.py --list

# تشغيل استعلام واحد فعلياً
python src/queries.py --run orders_by_status --status "مؤكد" --limit 5
python src/queries.py --run orders_by_customer --customer_id CUST00123
python src/queries.py --run high_value_orders_by_city --city "صنعاء" --min_amount 500
python src/queries.py --run orders_by_payment --payment_method كاش
python src/queries.py --run orders_needing_review

# إنشاء الفهارس الأربعة (3 منها Compound) منفردة
python src/indexes.py

# عرض explain('executionStats') قبل وبعد الفهارس لـ3 استعلامات معاً
python src/queries.py --explain-demo
```

`--explain-demo` يحذف الفهارس الأربعة إن وُجدت، يشغّل `explain` على 3
استعلامات (`orders_by_status`, `orders_by_customer`,
`high_value_orders_by_city`)، ثم يُنشئ الفهارس ويعيد `explain` لنفس
الاستعلامات، ويطبع مقارنة واضحة (`totalDocsExamined`, `totalKeysExamined`,
`executionTimeMillis`, نوع المرحلة COLLSCAN مقابل IXSCAN). التبرير
الكامل لكل فهرس (لماذا اختير وأثره) موجود كتعليقات داخل `src/indexes.py`
ويُطبع أيضاً عند تشغيله.

## 12. تقارير Aggregation (5 تقارير)

```bash
python src/aggregations.py --list
python src/aggregations.py --run sales_by_city
python src/aggregations.py --run top_products
python src/aggregations.py --run top_customers
python src/aggregations.py --run sales_by_period
python src/aggregations.py --run orders_status_distribution
```

كل تقرير مستقل بالتشغيل، ويستثني دوماً `orders_quarantine` (يعتمد فقط
على `orders_validated` بحالة `valid`/`corrected`). التفاصيل في
`src/aggregations.py`.

## 13. Materialized Views (تحديث تزايدي)

```bash
# بناء أول/كامل (لا توجد watermark سابقة بعد)
python src/materialized_views.py --refresh-all

# إعادة تشغيل --refresh-all بعد أي ingest جديد: يحدّث فقط الأيام/المنتجات
# التي تأثرت فعلياً بالسجلات الجديدة/المحدثة، لا كل البيانات من جديد
python src/materialized_views.py --refresh-all

# فرض إعادة بناء كاملة صريحة عند الحاجة
python src/materialized_views.py --refresh-all --force-full
```

العرضان `daily_sales_summary` و `top_products_summary` ومجموعة التحكم
`mv_control` (تخزّن watermark كل عرض) مُنشأة تلقائياً كـcollections في
MongoDB عند أول كتابة. آلية التحديث التزايدي موثقة بالتفصيل في تعليقات
`src/materialized_views.py`.

## 14. المهام المجدولة

```bash
# تشغيل يدوي فوري لأي وظيفة (دون انتظار الجدول) - لنفس الكود الذي
# يستخدمه المجدول والـAPI، يسجّل النتيجة في job_runs
python src/jobs.py --run refresh_materialized_views
python src/jobs.py --run generate_periodic_report

# تشغيل المجدول نفسه بشكل مستقل ومستمر (يبقي العملية حية بجدول زمني حقيقي)
python src/scheduler.py
```

- `refresh_materialized_views`: كل 15 دقيقة.
- `generate_periodic_report`: كل 6 ساعات (يحفظ تقريراً في `periodic_reports`).

كل تنفيذ (مجدول أو يدوي) يُسجَّل في `job_runs` بوقت البداية، وقت
النهاية، الحالة (`success`/`failure`)، ورسالة الخطأ عند الفشل.
عند تشغيل الـAPI (القسم 15) يبدأ المجدول تلقائياً مع إقلاع الخدمة.

## 15. واجهة API الموحّدة (FastAPI)

```bash
uvicorn src.api:app --reload --port 8000
```

ثم افتح `http://localhost:8000/docs` لواجهة Swagger التفاعلية. المسارات:

| المسار | الوظيفة |
|---|---|
| `GET /health` | حالة الخدمة واتصال MongoDB |
| `POST /ingest` | يشغّل خط الأنابيب الكامل (نفس `src/main.py`) على ملف `{"file_path": "..."}`|
| `POST /indexes` | ينشئ الفهارس الأربعة |
| `GET /queries` | قائمة الاستعلامات المتاحة |
| `GET /queries/{name}` | تشغيل استعلام (معاملات كـ query string، مثل `?status=مؤكد&limit=5`) |
| `GET /aggregations` | قائمة تقارير Aggregation |
| `GET /aggregations/{name}` | تشغيل تقرير (مثل `?limit=10`) |
| `POST /refresh-mv` | تحديث عرض مادي واحد (`{"view": "daily_sales_summary"}`) أو كلاهما (`{}`) |
| `GET /jobs` | قائمة المهام المجدولة + آخر تنفيذ لكل منها |
| `POST /jobs/{name}/run` | تشغيل مهمة يدوياً فوراً |

`POST /ingest` يستخدم `main.run_pipeline()` بالضبط - نفس بوابة الإدخال
المستخدمة من سطر الأوامر في Phase 1، بدون أي مسار إدخال مستقل جديد.

## 16. بنية المشروع (مُحدّثة)

```
pro/
|-- README.md
|-- requirements.txt
|-- .env.example
|-- config/
|   `-- settings.py          # كل الإعدادات + COLUMN_MAP + QUARANTINE_CODES + ITEM_*_KEYS
|-- data/
|-- src/
|   |-- main.py               # نقطة التشغيل (run_pipeline) - Phase 1
|   |-- file_router.py / batch_loader.py / spark_loader.py
|   |-- quality_rules.py      # قواعد التنظيف + classify_record()
|   |-- elt_pipeline.py       # التصنيف + Upsert -> validated/quarantine
|   |-- mongo_setup.py        # Collections + كل الفهارس الأساسية
|   |-- metrics.py
|   |-- indexes.py            # Phase 2: الفهارس الأربعة لـ orders_validated
|   |-- queries.py            # Phase 2: 5 استعلامات + explain-demo
|   |-- aggregations.py       # Phase 2: 5 تقارير Aggregation
|   |-- materialized_views.py # Phase 2: daily_sales_summary + top_products_summary
|   |-- jobs.py               # Phase 2: تعريف وتسجيل المهام المجدولة
|   |-- scheduler.py          # Phase 2: APScheduler
|   `-- api.py                # Phase 2: FastAPI الموحّدة
|-- tests/
|-- reports/
`-- docs/
    `-- architecture.md
```
