"""
spark_loader.py

تحميل الملفات الكبيرة (> SMALL_FILE_THRESHOLD_MB) باستخدام PySpark:
- SparkSession + DataFrame API (لا Pandas).
- Schema ثابتة بدل inferSchema.
- كل الحقول تُقرأ كـ String في Raw للحفاظ على القيم غير النظيفة.
- الكتابة إلى MongoDB بالتوازي عبر MongoDB Spark Connector.
- عدم استخدام repartition دون تبرير موثّق.
"""

from datetime import datetime, timezone

from config.settings import (
    MONGO_URI,
    MONGO_DATABASE,
    SPARK_APP_NAME,
    SPARK_MASTER,
    SPARK_MONGO_CONNECTOR_PACKAGE,
    SPARK_INPUT_PARTITIONS,
)


def build_spark_session():
    from pyspark.sql import SparkSession

    mongo_write_uri = f"{MONGO_URI}/{MONGO_DATABASE}"

    builder = (
        SparkSession.builder
        .appName(SPARK_APP_NAME)
        .master(SPARK_MASTER)
        .config("spark.jars.packages", SPARK_MONGO_CONNECTOR_PACKAGE)
        .config("spark.mongodb.write.connection.uri", mongo_write_uri)
    )

    spark = builder.getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    return spark


def load_raw_spark(file_path, id_run, raw_collection_name, metrics):
    """
    يقرأ الملف الكبير عبر PySpark ويكتبه إلى orders_raw بالتوازي.
    كل الحقول تُقرأ كـ StringType حسب المواصفة 6.4 للحفاظ على القيم الخام.
    """
    from pyspark.sql import functions as F
    from pyspark.sql.types import StructType, StructField, StringType

    print("=" * 70)
    print(f"PYSPARK LOADER  (id_run={id_run})")
    print("=" * 70)

    spark = build_spark_session()

    try:
        # اكتشاف الأعمدة من السطر الأول فقط (بدون inferSchema على كامل الملف)
        header_line = spark.read.text(str(file_path)).limit(1).collect()[0][0]
        import csv as _csv
        columns = next(_csv.reader([header_line]))

        schema = StructType([StructField(c, StringType(), True) for c in columns])

        # ملاحظة مهمة: لا نستخدم .option("multiLine", True) هنا. خيار
        # multiLine يفرض على Spark قراءة الملف بالكامل عبر Executor واحد
        # (partition واحدة) لأنه يحتاج تتبّع حقول نصية متعددة الأسطر على
        # مستوى الملف كله، مما يُسقط التوازي المطلوب فعلياً في هذا القسم
        # من المشروع (Input partitions كانت تظهر = 1 دائماً). بدلاً من ذلك
        # نستخدم quote/escape فقط، وهو يكفي لمعالجة الفواصل والاقتباسات
        # داخل حقول CSV (مثل items JSON المُقتبس) مع الحفاظ على التوازي
        # الطبيعي القائم على تجزيء الملف إلى splits متعددة.
        df = (
            spark.read
            .option("header", True)
            .option("quote", '"')
            .option("escape", '"')
            .schema(schema)
            .csv(str(file_path))
        )

        input_partitions = df.rdd.getNumPartitions()
        print(f"Input partitions (default, no repartition): {input_partitions}")

        # لا نستخدم repartition بدون مبرر. إذا احتجت لضبط التوازي، فعّل
        # SPARK_INPUT_PARTITIONS في settings.py ووثّق السبب (مثلاً: عدد
        # الملفات المصدر قليل جداً مقارنة بعدد الأنوية المتاحة).
        if SPARK_INPUT_PARTITIONS and SPARK_INPUT_PARTITIONS > 0:
            print(
                f"Repartitioning to {SPARK_INPUT_PARTITIONS} "
                f"(justified: SPARK_INPUT_PARTITIONS set explicitly in settings.py)"
            )
            df = df.repartition(SPARK_INPUT_PARTITIONS)

        # إضافة أعمدة تتبع Raw المطلوبة في القسم 6.5
        df = (
            df.withColumn("id_run", F.lit(id_run))
              .withColumn("file_source", F.lit(str(file_path)))
              .withColumn("number_row_source", F.monotonically_increasing_id())
              .withColumn("at_ingested", F.current_timestamp())
              .withColumn("engine_used", F.lit("pyspark"))
        )

        # تجميع الحقول الأصلية في struct واحد (record_raw) للحفاظ على
        # القيمة الأصلية دون تحويل يفقد المعلومة
        record_raw_cols = [F.col(c).alias(c) for c in columns]
        df = df.withColumn("record_raw", F.struct(*record_raw_cols))

        final_df = df.select(
            "id_run", "file_source", "number_row_source",
            "at_ingested", "engine_used", "record_raw",
        )

        read_rows = df.count()
        print(f"Rows read from CSV: {read_rows:,}")

        start = datetime.now(timezone.utc)

        (
            final_df.write
            .format("mongodb")
            .mode("append")
            .option("database", MONGO_DATABASE)
            .option("collection", raw_collection_name)
            .save()
        )

        elapsed = (datetime.now(timezone.utc) - start).total_seconds()
        rate = read_rows / elapsed if elapsed > 0 else float("inf")

        print(f"[OK] Spark write finished in {elapsed:.2f}s ({rate:.1f} rows/s)")
        print("=" * 70)

        metrics.read_rows = read_rows
        metrics.loaded_raw = read_rows
        metrics.partitions = input_partitions

        return True

    finally:
        spark.stop()
