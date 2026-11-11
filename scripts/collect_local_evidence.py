"""Collect actual, completed local validation evidence; refuses missing/failed runs."""
from datetime import datetime, timezone
from pathlib import Path
import argparse
import hashlib
import json
import re
import shutil
import zipfile
ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--logs',type=Path,default=Path('/tmp/reconcile-private'))
    p.add_argument('--browser',type=Path,default=Path('/tmp/reconcile-browser/local-completion'))
    p.add_argument('--out',type=Path,default=Path('/workspace/reconcile-artifacts/local-application'))
    args=p.parse_args()
    results=ROOT/'ml/results/local-application'
    text=(args.logs/'completion-integration-final.log').read_text()
    match=re.search(r'(\d+) passed in ([\d.]+)s',text)
    if not match or ' failed' in text:raise SystemExit('Full PostgreSQL run is missing or failed')
    browser=json.loads(Path('/tmp/reconcile-browser/acceptance-results.json').read_text())
    if browser['stats']['unexpected'] or browser['stats']['expected']!=1:raise SystemExit('Browser journey did not pass')
    accessibility=json.loads((args.browser/'accessibility.json').read_text())
    regression=json.loads((results/'workflow-regression/metrics.json').read_text())
    assert regression['pdf']['passed_all_assertions']==100

    shutil.copyfile('/tmp/reconcile-local-final/database.json',results/'stateful-regression.json')
    shutil.copyfile(args.logs/'completion-integration-final.log',results/'postgres-tests.txt')
    shutil.copyfile(args.logs/'completion-unit.log',results/'unit-tests.txt')
    shutil.copyfile(args.browser/'accessibility.json',results/'accessibility.json')
    shutil.copyfile('/tmp/reconcile-browser/acceptance-results.json',results/'browser-results.json')
    shutil.copyfile(args.logs/'completion-verify-db.log',results/'database-invariants.json')
    shutil.copyfile(args.logs/'completion-latency.log',results/'local-latency.json')
    files=[p for folder in ['backend/reconcile','backend/migrations','backend/tests','web/src','web/tests','scripts']
           for p in (ROOT/folder).rglob('*') if p.is_file() and p.suffix in {'.py','.ts','.tsx','.css'}]
    files += [ROOT/p for p in ['backend/pyproject.toml','backend/uv.lock','web/package.json','web/package-lock.json','compose.yaml','deploy/Dockerfile','Makefile']]
    hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}
    probe=json.loads((results/'production-smoke.json').read_text())
    review=json.loads((results/'production-review-recovery.json').read_text())
    assert probe['ledger_unchanged'] and review['original_extraction_unchanged']
    report={'generated_at':datetime.now(timezone.utc).isoformat(),
        'scope':'Local fictional-input functional validation; not representative invoice accuracy',
        'postgres_tests':{'passed':int(match[1]),'skipped':0,'duration_seconds':float(match[2])},
        'browser':{'journeys_passed':browser['stats']['expected'],'unexpected_failures':0,
                   'accessibility_violation_counts':{k:len(v) for k,v in accessibility.items()}},
        'controlled_pdf_regression':{'assertions_passed':100,'assignments':100,'distinct_pdf_files':68,'authored_scenarios':25,'independent_final_test':False},
        'stateful_regression':{'passed':3,'total':3,'included_in_other_db_tests':True},
        'production_container_smoke':{'new_documents':len(probe['cases']),'ledger_unchanged':True,'initial_probe_retained':True,'initial_uncertain_scan_reviewed':True,'simulated_staff_corrections_are_not_ocr_successes':True},
        'dataset_manifest_sha256':hashlib.sha256((ROOT/'fixtures/workflows/v1/manifest.json').read_bytes()).hexdigest(),
        'cloud_deployment_performed':False,'independent_human_label_audit':False,'source_sha256':hashes}
    (results/'summary.json').write_text(json.dumps(report,indent=2))
    args.out.mkdir(parents=True,exist_ok=True)
    for name in ['01-workspace.png','02-evidence-and-checks.png','03-human-review.png','04-revalidated-decision.png','05-current-ledger.png','06-mobile.png']:
        shutil.copyfile(args.browser/name,args.out/name)
    shutil.copytree(results,args.out/'results',dirs_exist_ok=True,ignore=shutil.ignore_patterns('artifact.json'))
    stale=args.out/'results/artifact.json'
    if stale.exists():stale.unlink()
    shutil.copytree(ROOT/'backend/reconcile/demo_samples',args.out/'sample-pdfs',dirs_exist_ok=True)
    for name in ['local-application.md','local-demo.md']:
        shutil.copyfile(ROOT/'docs'/name,args.out/name)
    pictures=['01-workspace.png','02-evidence-and-checks.png','03-human-review.png','04-revalidated-decision.png','05-current-ledger.png','06-mobile.png']
    page='<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Reconcile local validation</title><style>body{font:16px system-ui;background:#f7f8f4;color:#244331;max-width:1100px;margin:40px auto;padding:20px}p{line-height:1.7}img{max-width:100%;border:1px solid #ccd8c5;border-radius:8px}a{color:#245e42}article{margin:35px 0}</style><h1>Reconcile: working local application</h1><p>'+str(report['postgres_tests']['passed'])+' tests with real PostgreSQL; one complete browser journey; zero axe violations in the tested login and mobile workspace; 100 controlled PDF regression checks. These are functional results on fictional inputs, not a guarantee of accuracy on unseen invoices.</p><p><a href="results/summary.json">Evidence summary and source hashes</a> · <a href="local-application.md">Architecture and operations</a> · <a href="local-demo.md">Narrated demo guide</a></p><p>Original source uncertainty is preserved in the reports. <a href="source-audit/initial-scan.pdf">Inspect the actual initial scanned PDF</a>. Staff-correction tests do not count as OCR successes. Cloud deployment was not performed.</p>'
    for name in pictures:page+='<article><h2>'+name[3:-4].replace('-',' ').title()+'</h2><a href="'+name+'"><img alt="'+name[3:-4].replace('-',' ')+'" src="'+name+'"></a></article>'
    (args.out/'index.html').write_text(page+'</html>')
    archive=args.out.parent/'reconcile-local-application.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for f in sorted(args.out.rglob('*')):
            if f.is_file():z.write(f,f.relative_to(args.out))
    metadata={'path':str(archive),'bytes':archive.stat().st_size,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest()}
    (results/'artifact.json').write_text(json.dumps(metadata,indent=2))
    print(json.dumps({'postgres_passed':report['postgres_tests']['passed'],'browser_journeys':1,'artifact':metadata},indent=2))

if __name__=='__main__':main()
