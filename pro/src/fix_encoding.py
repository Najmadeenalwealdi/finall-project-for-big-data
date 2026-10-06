from pathlib import Path

input_file = Path("data/orders_huge_mixed_quality.csv")
output_file = Path("data/orders_huge_mixed_quality_fixed.csv")

# محاولة القراءة بترميز Windows-1256 (السبب الشائع لهذا التشوه) وإعادة الحفظ كـ UTF-8
try:
    with open(input_file, 'r', encoding='windows-1256') as src:
        content = src.read()
    with open(output_file, 'w', encoding='utf-8-sig') as dst:
        dst.write(content)
    print("[OK] File encoding fixed and saved as UTF-8-BOM!")
except Exception as e:
    # إذا كان الملف أصلاً UTF-8 ولكن العارض فقط هو المشوه
    with open(input_file, 'r', encoding='utf-8-sig') as src:
        content = src.read()
    with open(output_file, 'w', encoding='utf-8-sig') as dst:
        dst.write(content)
    print("[OK] File is already UTF-8, copied safely!")