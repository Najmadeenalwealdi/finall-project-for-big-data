import sys
from pathlib import Path

# 1. هذا السطر هو الحل: يخبر بايثون بمكان مجلد المشروع الرئيسي (mid_datapipeline)
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

# 2. الآن يمكن الاستيراد بنجاح
from pymongo import MongoClient
from config.settings import MONGO_URI, MONGO_DATABASE, VALIDATED_COLLECTION, QUARANTINE_COLLECTION

# ⚠️ استبدل هذا الـ ID بالـ ID الذي فشل في التشغيل الأخير
# (يمكنك نسخه من رسالة الخطأ السابقة)
FAILED_RUN_ID = "cb7053c1-cf8b-4382-ace6-b3d44f29018f" 

def clean_failed_run():
    print(f"Connecting to MongoDB at {MONGO_URI}...")
    client = MongoClient(MONGO_URI)
    db = client[MONGO_DATABASE]

    print(f"Cleaning partial data for run_id: {FAILED_RUN_ID}...")
    
    # حذف البيانات الجزئية من orders_validated
    result1 = db[VALIDATED_COLLECTION].delete_many({"last_run_id": FAILED_RUN_ID})
    print(f"  - Deleted {result1.deleted_count} documents from {VALIDATED_COLLECTION}")
    
    # حذف البيانات الجزئية من orders_quarantine
    result2 = db[QUARANTINE_COLLECTION].delete_many({"id_run": FAILED_RUN_ID})
    print(f"  - Deleted {result2.deleted_count} documents from {QUARANTINE_COLLECTION}")
    
    print("[OK] Cleanup complete. Ready for re-run.")
    client.close()

if __name__ == "__main__":
    clean_failed_run()