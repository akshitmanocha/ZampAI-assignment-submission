"""Run the focused submission examples and retain readable, assertion-based evidence.

Uses the already-built local test image and disposable PostgreSQL schemas. Never
builds images, resets demo data, reads account credentials, or changes OCR policy.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TEST = 'backend/tests/test_submission_edge_cases.py'
SOURCE = [TEST, 'backend/tests/test_application_postgres.py',
    'scripts/evaluate_submission_edges.py',
    'backend/reconcile/pipeline.py', 'backend/reconcile/business_validation.py',
    'backend/reconcile/ingest.py', 'backend/reconcile/worker.py',
    'backend/reconcile/invoice_parser.py', 'backend/reconcile/gst_parser.py',
    'backend/reconcile/paddle_text.py', 'backend/reconcile/source_quality.py',
    'backend/reconcile/settings.py', 'backend/reconcile/workflows.py',
    'backend/reconcile/history.py', 'ml/render_workflows.py',
    'fixtures/workflows/v1/manifest.json']
FAMILIES = {'missing_pack', 'offsetting_prices', 'partial_invoices', 'duplicates'}
EXPECTED_TESTS = {
    'test_happy_path_and_explicit_pack_size': 'control',
    'test_missing_pack_needs_evidence_before_approval': 'missing_pack',
    'test_same_total_does_not_hide_wrong_item_prices[agreed-prices]': 'offsetting_prices',
    'test_same_total_does_not_hide_wrong_item_prices[offsetting-errors]': 'offsetting_prices',
    'test_partial_invoice_uses_remaining_not_original_quantity[remaining-600]': 'partial_invoices',
    'test_partial_invoice_uses_remaining_not_original_quantity[over-by-100]': 'partial_invoices',
    'test_competing_partial_approvals_cannot_spend_the_same_balance': 'partial_invoices',
    'test_duplicate_different_pdf_bytes_is_still_detected': 'duplicates',
    'test_same_invoice_number_from_another_vendor_is_not_a_duplicate': 'duplicates',
    'test_changed_total_with_same_identity_needs_revision_review': 'duplicates',
    'test_mobile_scan_keeps_original_and_routes_uncertain_reading_to_review': 'scan_control',
}


def source_snapshot():
    return {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in SOURCE}


def load_run_inputs(xml_path):
    """Archived results retain the code identity captured when tests ran."""
    path = xml_path.parent/'run-inputs.json'
    if not path.exists():
        raise SystemExit('Original run-inputs.json is required; rerun the suite instead of relabelling old evidence.')
    saved = json.loads(path.read_text())
    if saved.get('junit_sha256') != hashlib.sha256(xml_path.read_bytes()).hexdigest():
        raise SystemExit('JUnit evidence differs from the recorded run; refusing to summarize it.')
    if not saved.get('source_sha256') or not saved.get('runtime_provenance'):
        raise SystemExit('Original source and runtime provenance are required.')
    return saved


def runtime_provenance():
    environment = dict(os.environ, LOCAL_UID=str(os.getuid()), LOCAL_GID=str(os.getgid()))
    names = [name for name in SOURCE if name.startswith('backend/reconcile/')]
    program = ('import hashlib,json,pathlib; names='+repr(names)+'; '
        'print(json.dumps({n:hashlib.sha256(pathlib.Path("/app",n).read_bytes()).hexdigest() for n in names}))')
    probe = subprocess.run(['docker', 'compose', '--profile', 'test', 'run', '--rm', '--no-deps',
        'test', 'python', '-c', program], cwd=ROOT, env=environment, text=True, capture_output=True)
    if probe.returncode:
        raise SystemExit('Could not verify the test runtime source; no evaluation started.')
    hashes = json.loads(probe.stdout)
    if any(hashes[name] != hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in names):
        raise SystemExit('Test image differs from the checkout. Rebuild it before evaluating.')
    image = subprocess.run(['docker', 'image', 'inspect', 'reconcile-local:test', '--format', '{{.Id}}'],
        cwd=ROOT, text=True, capture_output=True, check=True).stdout.strip()
    compose_files = os.getenv('COMPOSE_FILE', str(ROOT/'compose.yaml')).split(os.pathsep)
    return {'test_image': image, 'runtime_production_source_sha256': hashes,
        'production_sources_match_checkout': True,
        'compose_files_sha256': {str(Path(name)): hashlib.sha256(Path(name).read_bytes()).hexdigest()
            for name in compose_files}}


def report(xml_path, output, run_inputs):
    root = ET.parse(xml_path).getroot()
    cases = []
    for case in root.iter('testcase'):
        evidence = None
        for prop in case.findall('./properties/property'):
            if prop.get('name') == 'edge_evidence':
                evidence = json.loads(prop.get('value'))
        status = 'failed' if case.find('failure') is not None or case.find('error') is not None else 'skipped' if case.find('skipped') is not None else 'passed'
        cases.append({'test': case.get('name'), 'status': status,
            'seconds': float(case.get('time', 0)), 'evidence': evidence})
    families = {name: {'checks': sum(c['evidence'] is not None and c['evidence']['family'] == name for c in cases),
        'passed': sum(c['status'] == 'passed' and c['evidence'] is not None and c['evidence']['family'] == name for c in cases)}
        for name in sorted(FAMILIES)}
    result = {
        'version': 'submission-edges-v1', 'reported_at_utc': datetime.now(timezone.utc).isoformat(),
        'method': 'Actual PDF bytes -> authenticated upload -> durable worker -> persisted recommendation -> authenticated review/approval where specified; isolated real PostgreSQL schemas.',
        'labels': 'Implementation-agent authored expectations from explicit printed fields and seeded company facts. No model-generated labels. Existing known fixtures, not an independent holdout.',
        'ocr': 'PP-OCRv5 mobile; engine asserted on the image-only scan control.',
        'cases': cases, 'families': families, 'total': len(cases),
        'passed': sum(c['status'] == 'passed' and c['evidence'] is not None for c in cases),
        'failed': sum(c['status'] == 'failed' for c in cases),
        'skipped': sum(c['status'] == 'skipped' for c in cases),
        'source_sha256': run_inputs['source_sha256'],
        'runtime_provenance': run_inputs['runtime_provenance'],
        'run_started_at_utc': run_inputs['started_at_utc'],
        'junit_sha256': run_inputs['junit_sha256'],
        'sources_unchanged_during_run': run_inputs['sources_unchanged_during_run'],
        'limitations': [
            'Authored acceptance cases, not a production accuracy, precision or automation estimate.',
            'Eleven checks comprise four edge families and two controls; related variants share invoice content.',
            'Most examples use native PDF text. One image-only scan checks the deployed OCR and review path; this is not an OCR benchmark.',
            'Review corrections are simulated from authored source/specification evidence, not an independent human accuracy measurement.',
            'MiniLM semantic retrieval quality is not measured by these exact-SKU business scenarios.',
        ],
    }
    identities_complete = len(cases) == len(EXPECTED_TESTS) and {c['test'] for c in cases} == set(EXPECTED_TESTS)
    families_match = all(c['evidence'] and c['evidence']['family'] == EXPECTED_TESTS.get(c['test']) for c in cases)
    result['all_passed'] = (identities_complete and families_match and result['passed'] == len(EXPECTED_TESTS)
        and result['failed'] == 0 and result['skipped'] == 0 and run_inputs['sources_unchanged_during_run']
        and run_inputs['junit_sha256'] == hashlib.sha256(xml_path.read_bytes()).hexdigest())
    output.write_text(json.dumps(result, indent=2)+'\n')
    return result


def demo_inputs(output):
    """Bundle the actual source PDFs, without embedding expectations in a PDF."""
    sys.path.insert(0, str(ROOT/'ml'))
    from render_workflows import render
    from copy import deepcopy
    data = ROOT/'fixtures/workflows/v1/inputs'
    base = json.loads((data/'W01.json').read_text())['document']
    files = {name+'.pdf': (ROOT/'backend/reconcile/demo_samples'/f'{name}.pdf').read_bytes()
        for name in ['happy', 'missing-pack', 'offset-prices', 'partial-a', 'partial-b', 'scan']}
    over = deepcopy(base)
    over['lines'][0].update(qty='7', amount='3500.00')
    over.update(subtotal='3500.00', grand_total='3500.00')
    files['over-remaining-quantity.pdf'] = render(over)
    files['invoice-original.pdf'] = render(base)
    files['invoice-another-layout.pdf'] = render(base, 'columnar')
    files['README.txt'] = (
        'Fictional submission examples. Use a fresh seeded company dataset.\n'
        'Each automated test uses its own isolated company; these PDFs are not one approval batch.\n'
        'happy.pdf: explicit pack evidence; 600 remaining items can be approved.\n'
        'missing-pack.pdf: review until separately verified pack evidence is provided.\n'
        'offset-prices.pdf: total matches but BOTH item prices violate the order.\n'
        'over-remaining-quantity.pdf: requests 700 when only 600 remain; hold.\n'
        'partial-a.pdf + partial-b.pdf: each requests 400; together exceed the 600 remaining.\n'
        'invoice-original.pdf + invoice-another-layout.pdf: same supplier/invoice/amount, different PDF bytes.\n'
        'scan.pdf: actual image-only invoice. Current OCR may need source review.\n'
        'Approval changes balances; use fresh isolated contexts or separate orders for demonstrations.\n'
    ).encode()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('/tmp/reconcile-submission-edges-v1'))
    parser.add_argument('--from-junit', type=Path, help='Summarize a completed run without repeating tests.')
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    xml_path = args.output/'junit.xml'
    provenance_path = args.output/'runtime-provenance.json'
    run_inputs_path = args.output/'run-inputs.json'
    exit_code = 0
    if args.from_junit:
        run_inputs = load_run_inputs(args.from_junit)
        if args.from_junit.resolve() != xml_path:
            shutil.copyfile(args.from_junit, xml_path)
        provenance_path.write_text(json.dumps(run_inputs['runtime_provenance'], indent=2)+'\n')
        run_inputs_path.write_text(json.dumps(run_inputs, indent=2)+'\n')
    else:
        # Never summarize a stale success if the new runner fails to start.
        xml_path.unlink(missing_ok=True)
        (args.output/'report.json').unlink(missing_ok=True)
        provenance = runtime_provenance()
        provenance_path.write_text(json.dumps(provenance, indent=2)+'\n')
        run_inputs = {'version': 1, 'started_at_utc': datetime.now(timezone.utc).isoformat(),
            'source_sha256': source_snapshot(), 'runtime_provenance': provenance}
        run_inputs_path.write_text(json.dumps(run_inputs, indent=2)+'\n')
        environment = dict(os.environ, LOCAL_UID=str(os.getuid()), LOCAL_GID=str(os.getgid()))
        command = ['docker', 'compose', '--profile', 'test', 'run', '--rm', '--no-deps',
            '-v', str(args.output)+':/edge-results', 'test', 'python', '-m', 'pytest', '-q',
            '-o', 'cache_dir=/tmp/reconcile-pytest-cache', '-o', 'junit_family=legacy',
            '--junitxml=/edge-results/junit.xml', TEST]
        exit_code = subprocess.run(command, cwd=ROOT, env=environment).returncode
        if xml_path.exists():
            run_inputs['junit_sha256'] = hashlib.sha256(xml_path.read_bytes()).hexdigest()
            run_inputs['sources_unchanged_during_run'] = source_snapshot() == run_inputs['source_sha256']
            run_inputs_path.write_text(json.dumps(run_inputs, indent=2)+'\n')
    if not xml_path.exists():
        raise SystemExit('No JUnit evidence produced; evaluation did not complete.')
    result = report(xml_path, args.output/'report.json', run_inputs)
    demo_inputs(args.output/'demo-inputs.zip')
    print(json.dumps({k: result[k] for k in ['total', 'passed', 'failed', 'skipped', 'all_passed', 'families']}, indent=2))
    if exit_code or not result['all_passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
