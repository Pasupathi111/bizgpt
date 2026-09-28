import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('MONTHLY_REPORT_DATA_DIR', tempfile.mkdtemp(prefix='monthly-report-test-'))
os.environ.setdefault('MONTHLY_REPORT_CONFIG', str(ROOT.parents[1] / 'config' / 'monthly-report' / 'projects.json'))
