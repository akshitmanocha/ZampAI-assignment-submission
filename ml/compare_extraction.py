"""Compare extraction engines on identical images using independent labels."""
import argparse
import hashlib
import json
from pathlib import Path
from extraction_metrics import line_score,summarize

INVOICE_TEMPLATES={'formal_corporate','freelancer_invoice','modern_minimal'}


def load(path):
    rows=[json.loads(x) for x in path.read_text().splitlines()]
    assert len({(r['file_name'],r['quality']) for r in rows})==len(rows)
    for r in rows:r['line_metrics']=line_score(r['prediction']['lines'],r['gold']['line_items'])
    return rows


def compare(local_path,vision_path,out):
    local=load(local_path);vision=load(vision_path)
    index={(r['file_name'],r['quality']):r for r in local}
    selected=[]
    for r in vision:
        original=index[(r['file_name'],r['quality'])]
        assert json.dumps(original['gold'],sort_keys=True)==json.dumps(r['gold'],sort_keys=True)
        selected.append(original)
    def slices(rows):
        return {'overall':summarize(rows),'invoice_templates_only':summarize([r for r in rows if r['template'] in INVOICE_TEMPLATES]),'by_quality':{q:summarize([r for r in rows if r['quality']==q]) for q in ['clean','faded','bad_scan']}}
    report={'comparison':'same public images and unchanged publisher labels','images':len(vision),'independent_documents':len({r['file_name'] for r in vision}),'local':slices(selected),'vision':slices(vision),'vision_reported_cost':sum(float(r['provider_response'].get('usage',{}).get('cost') or 0) for r in vision),'metric_version':'v2: identifiers preserve punctuation/zeros; exact normalized descriptions required for row TP; source-label observability not assumed','metric_source_sha256':hashlib.sha256(Path(__file__).with_name('extraction_metrics.py').read_bytes()).hexdigest(),'limitations':['Small stratified synthetic sample, quality variants correlated','Gold fields may not be printed: strict full rows and core rows reported separately, no labels edited','Predictions on null-labelled fields remain visible as disagreements until source audited','Model boxes/values remain proposals, not automatically verified','No invoice matching, approval precision or automation rate measured']}
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2))
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--local',type=Path,required=True);p.add_argument('--vision',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=compare(a.local,a.vision,a.output)
    for name in ['local','vision']:
        s=r[name]['overall'];print(name,'fields', {k:f"{v['correct']}/{v['labelled_non_null']}" for k,v in s['fields'].items()},'strict rows',s['complete_rows'],'core rows',s['rows_description_quantity_amount'])
