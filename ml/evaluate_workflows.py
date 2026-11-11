"""Frozen validation cases: oracle-input diagnosis plus actual PDF evaluation."""
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import hashlib,json,time
from reconcile.business_validation import validate,from_extraction
from reconcile.document_text import extract_document
from reconcile.invoice_parser import parse_invoice


def check_hashes(dataset):
    manifest=json.loads((dataset/'manifest.json').read_text())
    for path,expected in manifest['files'].items():
        if hashlib.sha256((dataset/path).read_bytes()).hexdigest()!=expected:raise RuntimeError('Frozen input/oracle changed: '+path)
    return manifest


def value_equal(a,b):
    if isinstance(a,list) and isinstance(b,list):return len(a)==len(b) and all(value_equal(x,y) for x,y in zip(a,b))
    if isinstance(a,dict) and isinstance(b,dict):return a.keys()==b.keys() and all(value_equal(a[k],b[k]) for k in b)
    try:return Decimal(str(a))==Decimal(str(b))
    except Exception:return a==b


def compare(result,answer,check_values=True):
    errors=[]
    if result['bucket']!=answer['bucket']:errors.append('bucket')
    if sorted(result['blocking_rules'])!=sorted(answer['blocking_rules']):errors.append('blocking_rules')
    if not set(answer['required_unknown_rules']).issubset(result['unknown_rules']):errors.append('required_unknown_rules')
    if check_values:
        for name,value in answer['values'].items():
            if name in ['final_remaining_qty','successful_new_approvals']:continue
            if not value_equal(result['values'].get(name),value):errors.append('value:'+name)
    return errors


def extraction_errors(actual,printed):
    errors=[]
    def text(value):return ' '.join((value or '').split()).casefold()
    for name in ['vendor_name','invoice_number','invoice_date','po_reference','currency']:
        if text(actual.get(name))!=text(printed.get(name)):errors.append('extraction:'+name)
    for name in ['subtotal','tax_total','grand_total']:
        if not value_equal(actual.get(name),printed.get(name)):errors.append('extraction:'+name)
    if len(actual['lines'])!=len(printed['lines']):errors.append('extraction:line_count')
    for i,(a,b) in enumerate(zip(actual['lines'],printed['lines'])):
        if text(a.get('description'))!=text(b.get('description')):errors.append(f'extraction:line_{i+1}_description')
        for name in ['qty','unit_price','amount']:
            if not value_equal(a.get(name),b.get(name)):errors.append(f'extraction:line_{i+1}_{name}')
    return errors


def context_for(case,sha):
    company=deepcopy(case['company'])
    for row in company['invoice_history']:
        row['document_sha256']=sha if row['document_sha256']=='same_current_document' else hashlib.sha256(b'a different prior invoice').hexdigest()
    return company


def summarize(rows):
    buckets=['accept','human_review','reject']
    matrix={a:{b:0 for b in buckets} for a in buckets}
    for r in rows:matrix[r['expected_bucket']][r['predicted_bucket']]+=1
    auto=[r for r in rows if r['predicted_bucket']!='human_review']
    accepted=[r for r in rows if r['predicted_bucket']=='accept'];rejected=[r for r in rows if r['predicted_bucket']=='reject']
    groups={r['group_id'] for r in rows}
    return {'assignments':len(rows),'case_groups':len(groups),'passed_all_assertions':sum(not r['errors'] for r in rows),'bucket_accuracy':sum(r['predicted_bucket']==r['expected_bucket'] for r in rows)/len(rows) if rows else None,'automatic_coverage':len(auto)/len(rows) if rows else None,'correct_automatic_coverage':sum(r['predicted_bucket']==r['expected_bucket'] for r in auto)/len(rows) if rows else None,'accept_precision':sum(r['expected_bucket']=='accept' for r in accepted)/len(accepted) if accepted else None,'reject_precision':sum(r['expected_bucket']=='reject' for r in rejected)/len(rejected) if rejected else None,'review_rate':1-len(auto)/len(rows) if rows else None,'confusion_expected_rows_predicted_columns':matrix,'all_members_correct_groups':sum(all(not r['errors'] for r in rows if r['group_id']==g) for g in groups)}


def run(dataset,pdfs,out):
    manifest=check_hashes(dataset);out.mkdir(parents=True,exist_ok=True)
    artifacts=json.loads((pdfs/'manifest.json').read_text())
    oracle=[];pdf_rows=[];reading_cache={}
    cases={}
    for path in sorted((dataset/'inputs').glob('*.json')):
        case=json.loads(path.read_text());answer=json.loads((dataset/'expected'/path.name).read_text());cases[case['id']]=(case,answer)
        snapshot=context_for(case,'oracle-document-fingerprint')
        before=json.dumps(snapshot,sort_keys=True)
        result=validate(deepcopy(case['document']),snapshot,'oracle-document-fingerprint',today='2026-11-10')
        errors=compare(result,answer)
        if json.dumps(snapshot,sort_keys=True)!=before:errors.append('recommendation_mutated_history')
        signature=hashlib.sha256(json.dumps({'document':case['document'],'company':case['company'],'actions':case['actions']},sort_keys=True).encode()).hexdigest()
        oracle.append({'scenario_signature':signature,'case_id':case['id'],'group_id':case['group_id'],'family':case['family'],'mode':'oracle_inputs_no_extraction','expected_bucket':answer['bucket'],'predicted_bucket':result['bucket'],'errors':errors,'result':result})
    required_variants={'native_table','native_columnar','scan_clean','scan_degraded'}
    if set(artifacts['variants'])!=required_variants or len(artifacts['variants'])!=4 or not cases or len(cases)!=manifest['cases']:
        raise RuntimeError('Missing required variants or frozen cases; zero-test runs are invalid')
    expected_pairs={(id,v) for id in cases for v in artifacts['variants']}
    actual_pairs=[(a['case_id'],a['variant']) for a in artifacts['artifacts']]
    if len(actual_pairs)!=len(expected_pairs) or set(actual_pairs)!=expected_pairs:raise RuntimeError('Incomplete or repeated case/variant assignments')
    for artifact in artifacts['artifacts']:
        case,answer=cases[artifact['case_id']];data=(pdfs/artifact['file']).read_bytes()
        if hashlib.sha256(data).hexdigest()!=artifact['sha256']:raise RuntimeError('PDF hash mismatch')
        started=time.perf_counter();technical=None
        try:
            if artifact['sha256'] not in reading_cache:reading_cache[artifact['sha256']]=parse_invoice(extract_document(data))
            readings=reading_cache[artifact['sha256']];document=from_extraction(readings)
            snapshot=context_for(case,artifact['sha256']);before=json.dumps(snapshot,sort_keys=True)
            result=validate(document,snapshot,artifact['sha256'],today='2026-11-10');errors=compare(result,answer)+extraction_errors(document,case['document'])
            if json.dumps(snapshot,sort_keys=True)!=before:errors.append('recommendation_mutated_history')
        except Exception as e:
            technical=type(e).__name__;readings=None;result={'bucket':'human_review'};errors=['technical_failure']
        signature=hashlib.sha256(json.dumps({'document':case['document'],'company':case['company'],'actions':case['actions']},sort_keys=True).encode()).hexdigest()
        pdf_rows.append({'scenario_signature':signature,'case_id':case['id'],'group_id':case['group_id'],'family':case['family'],'mode':'actual_pdf','variant':artifact['variant'],'sha256':artifact['sha256'],'seconds':time.perf_counter()-started,'expected_bucket':answer['bucket'],'predicted_bucket':result['bucket'],'errors':errors,'technical_failure':technical,'result':result,'readings':readings})
        print('PDF',len(pdf_rows),'/',len(artifacts['artifacts']),case['id'],artifact['variant'],'PASS' if not errors else 'FAIL '+','.join(errors),flush=True)
    for name,rows in [('oracle',oracle),('pdf',pdf_rows)]:
        (out/(name+'-predictions.jsonl')).write_text(''.join(json.dumps(r)+'\n' for r in rows))
    unique_cases={r['scenario_signature']:r for r in oracle}
    unique_pdf_cases={(r['scenario_signature'],r['variant']):r for r in pdf_rows}
    report={'evaluation_date':'2026-11-10','unique_document_extractions':len(reading_cache),'unique_document_context_action_scenarios':len(unique_cases),'deduplicated_oracle':summarize(list(unique_cases.values())),'deduplicated_pdf':summarize(list(unique_pdf_cases.values())),'code_sha256':{name:hashlib.sha256((Path(__file__).resolve().parents[1]/name).read_bytes()).hexdigest() for name in ['backend/reconcile/business_validation.py','backend/reconcile/invoice_parser.py','backend/reconcile/document_text.py']},'extraction_assertions':'Header fields, exact normalized descriptions, numeric row values and line count checked in addition to bucket/reasons/normalized business values','dataset_manifest_sha256':hashlib.sha256((dataset/'manifest.json').read_bytes()).hexdigest(),'dataset_version':manifest['version'],'oracle':summarize(oracle),'pdf':summarize(pdf_rows),'by_variant':{v:summarize([r for r in pdf_rows if r['variant']==v]) for v in artifacts['variants']},'by_family':{f:summarize([r for r in pdf_rows if r['family']==f]) for f in sorted({r['family'] for r in pdf_rows})},'technical_failures':sum(r['technical_failure'] is not None for r in pdf_rows),'limitations':['Author-known synthetic acceptance set, not representative accuracy estimate','Variants and controls correlated; counts are not independent invoices','All cases in validation, no training/threshold tuning on this dataset','Deterministic SKU/attribute baseline only; trained MiniLM/Nemotron not used','No browser/API/job workflow evaluated here','Stateful approval outcomes evaluated separately in real PostgreSQL']}
    (out/'metrics.json').write_text(json.dumps(report,indent=2));print('WORKFLOW_RESULT '+json.dumps({'oracle':report['oracle'],'pdf':report['pdf']}),flush=True)
    return report

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--dataset',type=Path,default=Path('fixtures/workflows/v1'));p.add_argument('--pdfs',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--require-all',action='store_true');a=p.parse_args();r=run(a.dataset,a.pdfs,a.output)
    if a.require_all and (r['oracle']['passed_all_assertions']!=r['oracle']['assignments'] or r['pdf']['passed_all_assertions']!=r['pdf']['assignments']):raise SystemExit(1)
