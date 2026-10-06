import os

# 1. ضع المسارات الحقيقية التي تأكدت منها في الخطوة 2
os.environ['JAVA_HOME'] = r"C:\Program Files\Java\jdk-17"  # عدلها إذا كان مسار جافا مختلف
os.environ['SPARK_HOME'] = r"C:\spark\spark-3.5.1-bin-hadoop3" # عدلها إذا كان اسم مجلد سبارك مختلف

# 2. إضافة مسارات bin إلى PATH ليجدها بايثون
java_bin = os.path.join(os.environ['JAVA_HOME'], 'bin')
spark_bin = os.path.join(os.environ['SPARK_HOME'], 'bin')
os.environ['PATH'] = f"{java_bin};{spark_bin};{os.environ['PATH']}"

# 3. تهيئة Spark باستخدام findspark
import findspark
findspark.init()

from pyspark.sql import SparkSession

print("Initializing Spark...")
spark = SparkSession.builder.appName("test").master("local[*]").getOrCreate()

print("✅ Spark is working successfully!")
print(f"Spark version: {spark.version}")

spark.stop()