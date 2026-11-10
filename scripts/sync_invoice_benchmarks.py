"""Refresh saved UI benchmark cards from the completed primary evaluation.

This writes a local JSON asset only. It makes no API, database or deployment calls.
"""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def percent(value):
    return f'{value:.1%}' if value is not None else 'No proposed values'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', type=Path,
                        default=ROOT / 'ml/results/indian-gst/baseline-v4-ppocr/metrics.json')
    args = parser.parse_args()
    report = json.loads(args.report.read_text())
    registry = json.loads((ROOT / 'ml/evaluation_config.json').read_text())['primary_invoice_evaluation']
    if any(report['dataset'][key] != registry[key] for key in ['dataset', 'revision']):
        raise RuntimeError('Report does not match the primary evaluation registry')
    primary = report['primary_official_test']
    if primary['raw_extracted']['documents'] != registry['primary_count']:
        raise RuntimeError('Incomplete primary report')
    for suite, count in registry['robustness_counts'].items():
        if report['robustness'][suite]['raw_extracted']['documents'] != count:
            raise RuntimeError('Incomplete robustness report')
    for path, expected in report['run']['source_sha256'].items():
        if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != expected:
            raise RuntimeError('Reader/evaluator source changed since baseline: ' + path)
    raw = primary['raw_extracted']
    verified = primary['source_verified']
    micro = raw['core_header_micro']
    target = ROOT / 'backend/reconcile/benchmark_summary.json'
    saved = json.loads(target.read_text())
    cards = [
        {
            'name': 'Indian GST invoice extraction — primary benchmark',
            'scope': 'All 197 official test invoices from Divya52/indian-gst-invoices. '
                     'PP-OCRv5 English mobile on CPU (about 3.1M stored model values), GST-aware parser, original publisher labels, no fine-tuning. '
                     'Five core header fields; numbers below use raw found readings.',
            'metrics': {
                'Official test invoices': '197',
                'Correct core header values': f"{micro['correct']} / {micro['labelled_non_null']} ({percent(micro['recall_on_non_null_labels'])})",
                'Precision of proposed headers': percent(micro['precision_of_found_values']),
                'All five headers correct': f"{raw['all_five_core_headers']['correct_documents']} / 197",
                'Complete line-row F1': percent(raw['complete_core_rows']['f1']),
                'Reader failures (included)': f"{raw['technical_failures']} / 197"
            },
            'limitation': 'Synthetic Indian invoices; publisher labels are not independently human audited. '
                          'Core values are not every GST field. Missing readings and processing failures count against recall. '
                          'This test was already inspected in the older baseline; the new pipeline was developed on training/validation data. '
                          'No verified purchase-order history or catalog-match labels: these are extraction scores, not invoice approval accuracy or automation.'
        },
        {
            'name': 'Indian GST source-verification gate',
            'scope': 'Same 197 test invoices after withholding readings flagged by the application for source verification. '
                     'No human corrections are applied. Denominators include all labelled core values.',
            'metrics': {
                'Core header recall after gate': percent(verified['core_header_micro']['recall_on_non_null_labels']),
                'Precision after gate': percent(verified['core_header_micro']['precision_of_found_values']),
                'All five headers present': f"{verified['all_five_core_headers']['complete_predictions']} / 197"
            },
            'limitation': 'The gate is an OCR-quality heuristic, not a calibrated correctness probability. '
                          'Withholding reduces coverage and does not prove that retained readings are safe to approve.'
        },
        {
            'name': 'Indian GST separate robustness suites',
            'scope': '24 source adversarial invoices and 40 Hindi/Kannada invoices, reported separately from the main English test. '
                     'Raw five-header recall includes missing values and technical failures.',
            'metrics': {
                'Adversarial header recall (24 documents)': percent(report['robustness']['injection']['raw_extracted']['core_header_micro']['recall_on_non_null_labels']),
                'Hindi/Kannada header recall (40 documents)': percent(report['robustness']['regional']['raw_extracted']['core_header_micro']['recall_on_non_null_labels'])
            },
            'limitation': 'Regional scripts exceed the current automatic application scope. '
                          'These scores are not averaged into the primary result and do not establish resistance to every document attack.'
        }
    ]
    selection_path=ROOT/'ml/results/ocr-upgrade/selection-v2-pdf-coordinates/metrics.json'
    if selection_path.exists():
        selection=json.loads(selection_path.read_text())['model_selection']
        cards.append({
            'name':'OCR validation comparison',
            'scope':'Same 60 validation images with the GST parser. Model selection evidence; separate from the official test. Both readers run without invoice-answer access.',
            'metrics':{
                'Tesseract header recall':percent(selection['tesseract']['raw_extracted']['core_header_micro']['recall_on_non_null_labels']),
                'Compact OCR header recall':percent(selection['paddle-mobile']['raw_extracted']['core_header_micro']['recall_on_non_null_labels']),
                'Tesseract complete-row F1':percent(selection['tesseract']['raw_extracted']['complete_core_rows']['f1']),
                'Compact OCR complete-row F1':percent(selection['paddle-mobile']['raw_extracted']['complete_core_rows']['f1'])},
            'limitation':'Validation is used for selection, not independent confirmation. Separate 130-image calibration retains some high-confidence errors; OCR scores are not correctness probabilities.'})
    saved['primary_invoice_evaluation'] = {**registry, 'report': str(args.report.relative_to(ROOT)),
        'report_sha256': hashlib.sha256(args.report.read_bytes()).hexdigest(),
        'finished_at': report['finished_at']}
    saved['experiments'] = cards + [card for card in saved['experiments']
                                     if not card['name'].startswith('Indian GST') and card['name']!='OCR validation comparison']
    target.write_text(json.dumps(saved, indent=2, ensure_ascii=False) + '\n')
    print('Updated local benchmark cards from', args.report.relative_to(ROOT))


if __name__ == '__main__':
    main()
