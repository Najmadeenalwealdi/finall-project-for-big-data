import os
import sys
import json
import subprocess
import time
from pathlib import Path
from datetime import datetime

# ============================================
# إعدادات المعالجة
# ============================================
CHUNKS_DIR = "data/chunks"
PROGRESS_FILE = "reports/progress.json"
RESULTS_FILE = "reports/chunk_results.json"
MAIN_SCRIPT = "src/main.py"
SLEEP_BETWEEN_CHUNKS = 5  # ثواني راحة بين كل جزء (لتبريد الجهاز)

# ============================================
# دوال مساعدة
# ============================================

def load_progress():
    """تحميل آخر تقدم محفوظ"""
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"completed_chunks": [], "failed_chunks": [], "last_chunk": 0}

def save_progress(progress):
    """حفظ التقدم الحالي"""
    os.makedirs("reports", exist_ok=True)
    with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
        json.dump(progress, f, indent=2, ensure_ascii=False)

def get_chunk_files():
    """جلب جميع ملفات الأجزاء مرتبة"""
    chunks_path = Path(CHUNKS_DIR)
    if not chunks_path.exists():
        print(f"❌ مجلد الأجزاء غير موجود: {CHUNKS_DIR}")
        sys.exit(1)
    
    chunk_files = sorted(chunks_path.glob("chunk_*.csv"))
    return chunk_files

def process_single_chunk(chunk_file, chunk_num, total_chunks):
    """معالجة جزء واحد"""
    print(f"\n{'='*70}")
    print(f"🔄 Chunk {chunk_num}/{total_chunks}: {chunk_file.name}")
    print(f"{'='*70}")
    
    start_time = time.time()
    
    try:
        # تشغيل المعالجة
        cmd = [sys.executable, MAIN_SCRIPT, "--file", str(chunk_file)]
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=False,
            text=True
        )
        
        elapsed = time.time() - start_time
        
        print(f"\n✅ Chunk {chunk_num} completed in {elapsed:.1f}s")
        return {"status": "success", "elapsed": elapsed}
        
    except subprocess.CalledProcessError as e:
        elapsed = time.time() - start_time
        print(f"\n❌ Chunk {chunk_num} failed after {elapsed:.1f}s")
        print(f"Error: {e}")
        return {"status": "failed", "elapsed": elapsed, "error": str(e)}

def print_final_summary(results):
    """طباعة الملخص النهائي"""
    print(f"\n{'='*70}")
    print(f"📊 FINAL SUMMARY")
    print(f"{'='*70}")
    
    successful = [r for r in results if r["status"] == "success"]
    failed = [r for r in results if r["status"] == "failed"]
    
    print(f"Total chunks    : {len(results)}")
    print(f"Successful      : {len(successful)} ✅")
    print(f"Failed          : {len(failed)} ❌")
    
    if successful:
        total_time = sum(r["elapsed"] for r in successful)
        print(f"Total time      : {total_time:.1f}s ({total_time/60:.1f} min)")
        print(f"Avg per chunk   : {total_time/len(successful):.1f}s")
    
    print(f"{'='*70}")

# ============================================
# البرنامج الرئيسي
# ============================================

def main():
    print("🚀 Starting chunk processing...")
    print(f"📁 Chunks directory: {CHUNKS_DIR}")
    print(f"⏸️  Sleep between chunks: {SLEEP_BETWEEN_CHUNKS}s")
    
    # جلب ملفات الأجزاء
    chunk_files = get_chunk_files()
    total_chunks = len(chunk_files)
    
    if total_chunks == 0:
        print("❌ No chunk files found!")
        sys.exit(1)
    
    print(f"📋 Found {total_chunks} chunks to process")
    
    # تحميل التقدم السابق
    progress = load_progress()
    completed = set(progress["completed_chunks"])
    
    print(f"📈 Already completed: {len(completed)} chunks")
    
    # سؤال المستخدم: هل يريد البدء من جديد أم الاستئناف؟
    if len(completed) > 0:
        choice = input(f"\nResume from chunk {len(completed)+1}? (y=resume, n=restart): ")
        if choice.lower() == 'n':
            completed = set()
            progress = {"completed_chunks": [], "failed_chunks": [], "last_chunk": 0}
            print(" Restarting from beginning...")
    
    # معالجة الأجزاء
    results = []
    
    for i, chunk_file in enumerate(chunk_files, 1):
        # تخطي الأجزاء المكتملة
        if i in completed:
            print(f"⏭️  Skipping chunk {i} (already completed)")
            continue
        
        # معالجة الجزء
        result = process_single_chunk(chunk_file, i, total_chunks)
        results.append({
            "chunk_num": i,
            "file": chunk_file.name,
            **result
        })
        
        # تحديث التقدم
        if result["status"] == "success":
            progress["completed_chunks"].append(i)
        else:
            progress["failed_chunks"].append(i)
        
        progress["last_chunk"] = i
        save_progress(progress)
        
        # راحة بين الأجزاء (لتبريد الجهاز)
        if i < total_chunks and result["status"] == "success":
            print(f"😴 Resting {SLEEP_BETWEEN_CHUNKS}s...")
            time.sleep(SLEEP_BETWEEN_CHUNKS)
    
    # حفظ النتائج النهائية
    os.makedirs("reports", exist_ok=True)
    final_results = {
        "start_time": datetime.now().isoformat(),
        "total_chunks": total_chunks,
        "results": results,
        "summary": {
            "successful": len([r for r in results if r["status"] == "success"]),
            "failed": len([r for r in results if r["status"] == "failed"])
        }
    }
    
    with open(RESULTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(final_results, f, indent=2, ensure_ascii=False)
    
    # طباعة الملخص
    print_final_summary(results)
    print(f"\n📄 Detailed results saved to: {RESULTS_FILE}")

if __name__ == "__main__":
    main()