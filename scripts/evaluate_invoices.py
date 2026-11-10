"""Run the primary invoice benchmark with the application's Docker OCR engine."""
import os
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]


def main():
    data=Path(os.getenv('INVOICE_EVAL_DATA',str(ROOT.parent/'reconcile-artifacts/indian-gst-v1'))).resolve()
    output=Path(os.getenv('INVOICE_EVAL_OUT','/tmp/reconcile-indian-gst-evaluation')).resolve()
    output.mkdir(parents=True,exist_ok=True)
    if not (ROOT/'ml/data/indian-gst-v1/manifest.json').is_file():
        raise SystemExit('Prepare the pinned dataset first: make invoice-data')
    if not data.is_dir():raise SystemExit('Missing dataset directory; run make invoice-data')
    environment={**os.environ,'LOCAL_UID':str(os.getuid()),'LOCAL_GID':str(os.getgid())}
    subprocess.run(['docker','compose','--profile','test','run','--rm','--no-deps',
        '-v',str(data)+':/evaluation-data:ro','-v',str(output)+':/evaluation-output',
        'test','python','/app/ml/evaluate_indian_gst.py','--data','/evaluation-data',
        '--manifest','/app/ml/data/indian-gst-v1/manifest.json','--output','/evaluation-output/results','--workers','3'],
        cwd=ROOT,env=environment,check=True)
    print('Primary Indian GST results:',output/'results')

if __name__=='__main__':main()
