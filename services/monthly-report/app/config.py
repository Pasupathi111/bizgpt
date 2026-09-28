"""Settings for the Monthly Report POC. Everything here belongs to this project only."""

import json
import os
from pathlib import Path

OPENWEBUI_URL = os.getenv('OPENWEBUI_BASE_URL', 'http://open-webui:8080').rstrip('/')
# The custom Biz GPT model "Monthly Report Vision"; its base
# (vision) model is set in Biz GPT Workspace -> Models.
MODEL = os.getenv('MONTHLY_REPORT_MODEL', 'monthly-report-vision')
# Optional service key; when empty the signed-in user's own Biz GPT session calls the model.
OPENWEBUI_API_KEY = os.getenv('MONTHLY_REPORT_OPENWEBUI_API_KEY', '')
MODEL_TIMEOUT = float(os.getenv('MONTHLY_REPORT_MODEL_TIMEOUT', '240'))
# Images are shrunk to this longest side before they go to the model (speed, token cost).
MODEL_IMAGE_SIZE = int(os.getenv('MONTHLY_REPORT_MODEL_IMAGE_SIZE', '896'))

# Optional timer for the Gmail intake (seconds, 0 = only when asked from chat or the page).
GMAIL_POLL_SECONDS = int(os.getenv('MONTHLY_REPORT_GMAIL_POLL_SECONDS') or 0)

DATA_DIR = Path(os.getenv('MONTHLY_REPORT_DATA_DIR', '/data'))
MAX_PHOTOS = int(os.getenv('MONTHLY_REPORT_MAX_PHOTOS', '60'))
MAX_PHOTO_BYTES = int(os.getenv('MONTHLY_REPORT_MAX_PHOTO_MB', '15')) * 1024 * 1024

CONFIG_PATH = Path(
    os.getenv('MONTHLY_REPORT_CONFIG')
    or Path(__file__).resolve().parents[3] / 'config' / 'monthly-report' / 'projects.json'
)


def load_config() -> dict:
    config = json.loads(CONFIG_PATH.read_text())
    threshold = os.getenv('MONTHLY_REPORT_CONFIDENCE_THRESHOLD')
    if threshold:
        config['confidence_threshold'] = int(threshold)
    return config


def get_project(project_id: str) -> dict | None:
    return next((p for p in load_config()['projects'] if p['id'] == project_id), None)
