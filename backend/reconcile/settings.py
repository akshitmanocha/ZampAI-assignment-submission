"""Single-tenant local application configuration and versioned money policy."""
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
POLICY = {
    'version': 'local-ap-2026.11.3',
    'absolute_unit_price_tolerance': '0.05',
    'relative_unit_price_tolerance': '0.01',
    'absolute_po_amount_tolerance': '1.00',
    'relative_po_amount_tolerance': '0.01',
    'quantity_tolerance': '0',
    'amount_rounding': 'ROUND_HALF_UP',
}
STAGES = ['intake', 'text_layer', 'ocr', 'field_extraction', 'normalization',
          'vendor_match', 'po_match', 'line_match', 'policy_checks', 'decision', 'finalize']
RECOMMENDATIONS = {'accept': 'ready_for_approval', 'human_review': 'needs_review', 'reject': 'hold'}
MAX_BYTES = 10 * 1024 * 1024
MAX_LINES = 100


def business_date():
    return datetime.now(ZoneInfo('Asia/Kolkata')).date().isoformat()


def model_dir():
    return Path(os.getenv('MINILM_DIR', str(ROOT / 'ml/artifacts/minilm')))


def origins():
    return {s.strip().rstrip('/') for s in os.getenv(
        'APP_ORIGINS', 'http://127.0.0.1:8000,http://localhost:8000').split(',') if s.strip()}
