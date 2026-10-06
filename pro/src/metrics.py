"""
metrics.py

تجميع مقاييس كل تشغيل (id_run) وحفظها في reports/results.json
كما هو مطلوب في القسم 6.12 والمرحلة 8 من المعمارية.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from config.settings import RESULTS_FILE, REPORTS_DIR


class RunMetrics:
    def __init__(self, id_run, file_name, file_size_mb, used_engine):
        self.id_run = id_run
        self.file_name = file_name
        self.file_size_mb = file_size_mb
        self.used_engine = used_engine

        self.started_at = datetime.now(timezone.utc)
        self.finished_at = None

        self.read_rows = 0
        self.loaded_raw = 0
        self.count_valid = 0
        self.count_corrected = 0
        self.count_quarantine = 0

        self.counts_case_error = {}
        self.counts_correction_rule = {}

        self.count_inserted = 0
        self.count_updated = 0
        self.count_unchanged = 0

        self.partitions = None
        self.size_batch = None

    def add_quarantine_code(self, code):
        self.counts_case_error[code] = self.counts_case_error.get(code, 0) + 1

    def add_correction_rule(self, rule_code):
        """
        يسجل كم مرة أُطلقت كل قاعدة تصحيح - أداة تشخيصية أساسية:
        إذا وجدت قاعدة واحدة تطلق على أغلب السجلات (مثلاً > 80%)، هذا
        مؤشر قوي أن الحقل لا يطابق أسماء/صيغة بياناتك الفعلية ويحتاج
        تعديل في quality_rules.py أو COLUMN_MAP بدل أنه تصحيح حقيقي.
        """
        self.counts_correction_rule[rule_code] = self.counts_correction_rule.get(rule_code, 0) + 1

    def finish(self):
        self.finished_at = datetime.now(timezone.utc)

    @property
    def seconds_elapsed(self):
        end = self.finished_at or datetime.now(timezone.utc)
        return round((end - self.started_at).total_seconds(), 3)

    @property
    def throughput(self):
        elapsed = self.seconds_elapsed
        if elapsed <= 0:
            return 0
        return round(self.read_rows / elapsed, 2)

    def check_consistency(self):
        """
        شرط القبول من القسم 6.11:
        run_raw_count = run_valid_count + run_corrected_count + run_quarantine_count
        """
        expected = self.count_valid + self.count_corrected + self.count_quarantine
        return self.loaded_raw == expected, expected

    @property
    def upsert_applied(self):
        """
        true فقط إذا كل سجل Valid/Corrected حصل على نتيجة Upsert واحدة
        بالضبط (inserted أو updated أو unchanged) - فحص اتساق للـ Upsert
        نفسه، وليس فحص Idempotency عبر التشغيلات.
        """
        expected = self.count_valid + self.count_corrected
        actual = self.count_inserted + self.count_updated + self.count_unchanged
        return expected == actual

    @property
    def idempotent_run(self):
        """
        true إذا هذا التشغيل لم يُنشئ أي سجل عمل جديد في orders_validated
        (count_inserted == 0) - أي أن كل السجلات الصالحة/المصححة كانت
        موجودة مسبقاً وتم تحديثها أو تركها دون تغيير فقط.

        هذا يكون False بشكل طبيعي ومتوقع في أول تشغيل (لأنه يُدرج
        سجلات جديدة لأول مرة)، ويجب أن يصبح True عند إعادة تشغيل نفس
        الملف مرة ثانية - وهذا بالضبط اختبار Idempotency المطلوب في 6.10.
        """
        return self.count_inserted == 0

    def to_dict(self):
        ok, expected = self.check_consistency()
        return {
            "id_run": self.id_run,
            "file_name": self.file_name,
            "file_size_mb": self.file_size_mb,
            "used_engine": self.used_engine,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "read_rows": self.read_rows,
            "loaded_raw": self.loaded_raw,
            "count_valid": self.count_valid,
            "count_corrected": self.count_corrected,
            "count_quarantine": self.count_quarantine,
            "consistency_check_passed": ok,
            "consistency_expected_total": expected,
            "seconds_elapsed": self.seconds_elapsed,
            "throughput_rows_per_sec": self.throughput,
            "partitions_or_batch_size": self.partitions if self.partitions is not None else self.size_batch,
            "counts_case_error": self.counts_case_error,
            "counts_correction_rule": self.counts_correction_rule,
            "count_inserted": self.count_inserted,
            "count_updated": self.count_updated,
            "count_unchanged": self.count_unchanged,
            "upsert_applied": self.upsert_applied,
            "idempotent_run": self.idempotent_run,
        }

    def print_summary(self):
        print("=" * 70)
        print(f"RUN SUMMARY  (id_run={self.id_run})")
        print("=" * 70)
        print(f"Engine            : {self.used_engine}")
        print(f"File              : {self.file_name} ({self.file_size_mb} MB)")
        print(f"Read rows         : {self.read_rows:,}")
        print(f"Loaded to raw     : {self.loaded_raw:,}")
        print(f"Valid             : {self.count_valid:,}")
        print(f"Corrected         : {self.count_corrected:,}")
        print(f"Quarantined       : {self.count_quarantine:,}")
        ok, expected = self.check_consistency()
        print(f"Consistency check : {'PASSED' if ok else 'FAILED'} (raw={self.loaded_raw}, expected={expected})")
        print(f"Elapsed           : {self.seconds_elapsed}s")
        print(f"Throughput        : {self.throughput} rows/sec")
        print(f"Inserted/Updated/Unchanged (upsert): "
              f"{self.count_inserted}/{self.count_updated}/{self.count_unchanged}")
        print(f"Upsert applied    : {self.upsert_applied}")
        print(f"Idempotent run    : {self.idempotent_run}  "
              f"({'no new business records inserted' if self.idempotent_run else 'new records were inserted this run (expected on first load)'})")
        if self.counts_case_error:
            print("Quarantine breakdown (why records were isolated):")
            for code, count in sorted(self.counts_case_error.items(), key=lambda x: -x[1]):
                print(f"  - {code}: {count}")
        if self.counts_correction_rule:
            print("Correction rule breakdown (why records were 'corrected'):")
            for code, count in sorted(self.counts_correction_rule.items(), key=lambda x: -x[1]):
                pct = (count / self.count_corrected * 100) if self.count_corrected else 0
                print(f"  - {code}: {count} ({pct:.1f}% of corrected)")
        print("=" * 70)


def save_run_metrics(run_metrics: RunMetrics):
    """
    يضيف نتيجة هذا التشغيل إلى reports/results.json (قائمة تراكمية
    لكل تشغيل، بدل الكتابة فوق النتائج السابقة، حتى يمكن مقارنة
    التشغيلات المتعددة - إثبات Idempotency يتطلب تشغيلين على الأقل).
    """
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    history = []
    if RESULTS_FILE.exists():
        try:
            with open(RESULTS_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
                if not isinstance(history, list):
                    history = [history]
        except (json.JSONDecodeError, OSError):
            history = []

    history.append(run_metrics.to_dict())

    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    print(f"[OK] Metrics appended to {RESULTS_FILE}")
