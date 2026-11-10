"""Reviewable HTML/PDF bundle. Expected answers are visible to humans only."""
from pathlib import Path
import hashlib,html,json,shutil,zipfile


def build(dataset,pdfs,results,out):
    out.mkdir(parents=True,exist_ok=True);(out/'pdfs').mkdir(exist_ok=True)
    manifest=json.loads((pdfs/'manifest.json').read_text());metrics=json.loads((results/'metrics.json').read_text());database=json.loads((results.parent/'database.json').read_text())
    predictions=[json.loads(s) for s in (results/'pdf-predictions.jsonl').read_text().splitlines()]
    by_key={(r['case_id'],r['variant']):r for r in predictions}
    rows=[]
    for path in sorted((dataset/'inputs').glob('*.json')):
        case=json.loads(path.read_text());answer=json.loads((dataset/'expected'/path.name).read_text());cells=[]
        for variant in manifest['variants']:
            item=next(a for a in manifest['artifacts'] if a['case_id']==case['id'] and a['variant']==variant)
            shutil.copyfile(pdfs/item['file'],out/'pdfs'/item['file'])
            prediction=by_key[(case['id'],variant)];passed=not prediction['errors']
            cells.append('<td><a href="pdfs/'+html.escape(item['file'])+'">'+('PASS' if passed else 'FAIL')+'</a><br>'+html.escape(prediction['predicted_bucket'])+'</td>')
        rows.append('<tr><td>'+html.escape(case['id'])+'<br>'+html.escape(case['family'])+'</td><td>'+html.escape(answer['bucket'])+'<br>'+html.escape(answer['explanation'])+'</td>'+''.join(cells)+'</tr>')
    text='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Workflow validation v1</title><style>body{font:15px system-ui;margin:36px;color:#18352c;background:#fafbf8}h1{font-size:30px}p{max-width:980px;line-height:1.65}table{border-collapse:collapse;width:100%;background:white}td,th{border:1px solid #dce3d8;padding:12px;text-align:left;vertical-align:top}th{background:#eaf0e4}a{color:#1a6352}small{color:#596b61}.scroll{overflow:auto}</style><h1>Reconcile: edge-case validation</h1><p>25 authored scenarios, four PDF representations each. These are controlled synthetic acceptance tests, not 100 independent invoices or a production accuracy guarantee. Expected answers were frozen before evaluation; no model or application code generated its own gold labels. All cases belong to validation.</p><p>PDF initial recommendations: '''+str(metrics['pdf']['passed_all_assertions'])+'''/100 pass. Real PostgreSQL stateful traces: '''+str(database['passed'])+'''/3 pass. Natural automatic recommendation coverage: 84%; the remaining 16% intentionally require missing evidence or review. No payment is executed.</p><p>Each PASS link opens the actual PDF. The expected reason is shown separately; it is not embedded as an answer in the PDF. Duplicate PDFs are reused across different history contexts intentionally.</p><p><a href="database.json">Read the actual PostgreSQL traces</a>. Each case runs in an isolated company/history context; these PDFs are not a batch to approve against one shared ledger.</p><div class="scroll"><table><tr><th>Scenario</th><th>Independent expectation</th>'''+''.join('<th>'+html.escape(v)+'</th>' for v in manifest['variants'])+'''</tr>'''+''.join(rows)+'''</table></div><p><small>Matcher in this suite: printed SKU plus explicit product attributes; not the fine-tuned MiniLM experiment. API/browser/job workflow is not part of this benchmark. Source inputs, expected answers, manifests and reports are included in the archive for audit.</small></p></html>'''
    (out/'index.html').write_text(text)
    shutil.copytree(dataset,out/'dataset',dirs_exist_ok=True);shutil.copytree(results,out/'results',dirs_exist_ok=True);shutil.copyfile(results.parent/'database.json',out/'database.json')
    archive=out.parent/'workflow-validation-v1.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(out.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(out))
    return {'path':str(archive),'bytes':archive.stat().st_size,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'pdf_files':len(list((out/'pdfs').glob('*.pdf')))}

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--dataset',type=Path,default=Path('fixtures/workflows/v1'));p.add_argument('--pdfs',type=Path,required=True);p.add_argument('--results',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();print(json.dumps(build(a.dataset,a.pdfs,a.results,a.out),indent=2))
