import os
import sys

def split_csv_file(input_file, output_dir, chunk_size=1000000):
    """
    تقسيم ملف CSV كبير إلى أجزاء أصغر
    
    Args:
        input_file: مسار الملف الأصلي
        output_dir: مجلد الحفظ للأجزاء
        chunk_size: عدد الصفوف في كل جزء (افتراضي: مليون صف)
    """
    
    # إنشاء المجلد إذا لم يكن موجوداً
    os.makedirs(output_dir, exist_ok=True)
    
    # قراءة الملف
    print(f"📖 Reading {input_file}...")
    
    with open(input_file, 'r', encoding='utf-8') as f:
        # قراءة الهيدر (السطر الأول)
        header = f.readline()
        
        # قراءة البيانات على دفعات
        chunk_num = 1
        row_count = 0
        total_rows = 0
        
        while True:
            output_file = os.path.join(output_dir, f"chunk_{chunk_num:03d}.csv")
            
            with open(output_file, 'w', encoding='utf-8') as out_f:
                out_f.write(header)  # كتابة الهيدر في كل جزء
                
                # قراءة chunk_size صف
                for _ in range(chunk_size):
                    line = f.readline()
                    if not line:  # نهاية الملف
                        break
                    
                    out_f.write(line)
                    row_count += 1
                    total_rows += 1
            
            # ✅ الآن الـ with block انتهى والملف مغلق
            if row_count == 0:  # ما في بيانات جديدة
                os.remove(output_file)  # حذف الملف الفاضي
                break
            
            print(f"✅ Created: {output_file} ({row_count:,} rows)")
            chunk_num += 1
            row_count = 0
    
    print(f"\n🎉 Done! Created {chunk_num - 1} chunks with {total_rows:,} total rows")
    return chunk_num - 1

if __name__ == "__main__":
    input_file = "data/orders_huge_mixed_quality.csv"
    output_dir = "data/chunks"
    
    # تأكد إن الملف موجود
    if not os.path.exists(input_file):
        print(f"❌ Error: File not found: {input_file}")
        sys.exit(1)
    
    # حجم الملف
    file_size_mb = os.path.getsize(input_file) / (1024 * 1024)
    print(f"📦 File size: {file_size_mb:.2f} MB")
    
    # تقسيم الملف
    num_chunks = split_csv_file(input_file, output_dir, chunk_size=500000)  # نصف مليون صف لكل جزء
    
    print(f"\n📋 Next step: Process each chunk in 'data/chunks/' folder")