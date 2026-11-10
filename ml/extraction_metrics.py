"""Independent extraction scoring; expected labels never enter the parser."""
from collections import Counter
from decimal import Decimal
from difflib import SequenceMatcher
import re
import unicodedata
import numpy as np
from scipy.optimize import linear_sum_assignment

MAP={'vendor_name':'supplier_name','invoice_number':'invoice_number','po_reference':'po_number','invoice_date':'document_date','currency':'document_currency','grand_total':'document_total_amount'}

def normalized(value):return re.sub(r'\W+','',unicodedata.normalize('NFKC',str(value)).casefold())

def equal(field,a,b):
    if a is None or b is None:return a is None and b is None
    if field in ['grand_total','qty','unit_price','amount']:
        try:return Decimal(str(a))==Decimal(str(b))
        except Exception:return False
    if field in ['invoice_number','po_reference']:
        return re.sub(r'\s+','',str(a)).casefold()==re.sub(r'\s+','',str(b)).casefold()
    return normalized(a)==normalized(b)

def line_score(predicted,gold,require_unit_price=True):
    if not predicted or not gold:return {'tp':0,'predicted':len(predicted),'gold':len(gold)}
    similarities=np.array([[SequenceMatcher(None,normalized(p['description']['value'] or ''),normalized(g['description'])).ratio() for g in gold] for p in predicted])
    ri,ci=linear_sum_assignment(-similarities);correct=0
    for i,j in zip(ri,ci):
        p,g=predicted[i],gold[j]
        if similarities[i,j]<.85:continue
        # Fuzzy similarity aligns rows only; a true-positive row must also
        # preserve the complete normalized description.
        if normalized(p['description']['value'] or '')!=normalized(g['description']):continue
        checks=[('qty','quantity'),('amount','amount')]+([('unit_price','unit_price')] if require_unit_price else [])
        if all(p[k]['status']=='found' and equal(k,p[k]['value'],g[other]) for k,other in checks):correct+=1
    return {'tp':correct,'predicted':len(predicted),'gold':len(gold)}

def summarize(records):
    fields={}
    for field in MAP:
        eligible=sum(r['gold'][MAP[field]] is not None for r in records)
        found=sum(r['prediction']['header'][field]['status']=='found' for r in records)
        correct=sum(r['gold'][MAP[field]] is not None and r['prediction']['header'][field]['status']=='found' and equal(field,r['prediction']['header'][field]['value'],r['gold'][MAP[field]]) for r in records)
        hallucinated=sum(r['gold'][MAP[field]] is None and r['prediction']['header'][field]['status']=='found' for r in records)
        fields[field]={'labelled_non_null':eligible,'predicted_found':found,'correct':correct,'accuracy_on_non_null_labels':correct/eligible if eligible else None,'precision_of_found_values':correct/found if found else None,'predicted_when_label_null':hallucinated,'status_counts':dict(Counter(r['prediction']['header'][field]['status'] for r in records))}
    tp=sum(r['line_metrics']['tp'] for r in records);pred=sum(r['line_metrics']['predicted'] for r in records);gold=sum(r['line_metrics']['gold'] for r in records)
    p=tp/pred if pred else 0;r=tp/gold if gold else 0
    core=[line_score(r['prediction']['lines'],r['gold']['line_items'],require_unit_price=False) for r in records]
    core_tp=sum(r['tp'] for r in core);core_pred=sum(r['predicted'] for r in core);core_gold=sum(r['gold'] for r in core)
    core_p=core_tp/core_pred if core_pred else 0;core_r=core_tp/core_gold if core_gold else 0
    required=['invoice_number','invoice_date','currency','grand_total']
    eligible_records=[r for r in records if all(r['gold'][MAP[k]] is not None for k in required)]
    all_correct=sum(all(r['prediction']['header'][k]['status']=='found' and equal(k,r['prediction']['header'][k]['value'],r['gold'][MAP[k]]) for k in required) for r in eligible_records)
    five=required+['vendor_name']
    five_eligible=[r for r in records if all(r['gold'][MAP[k]] is not None for k in five)]
    five_correct=sum(all(r['prediction']['header'][k]['status']=='found' and equal(k,r['prediction']['header'][k]['value'],r['gold'][MAP[k]]) for k in five) for r in five_eligible)
    times=[r['seconds'] for r in records]
    return {'images':len(records),'independent_documents':len({r['file_name'] for r in records}),'fields':fields,'complete_rows':{'true_positive':tp,'predicted':pred,'labelled':gold,'precision':p,'recall':r,'f1':2*p*r/(p+r) if p+r else 0},'rows_description_quantity_amount':{'true_positive':core_tp,'predicted':core_pred,'labelled':core_gold,'precision':core_p,'recall':core_r,'f1':2*core_p*core_r/(core_p+core_r) if core_p+core_r else 0},'all_four_critical_fields':{'eligible_images':len(eligible_records),'correct':all_correct,'accuracy':all_correct/len(eligible_records) if eligible_records else None},'all_five_critical_fields':{'eligible_images':len(five_eligible),'correct':five_correct,'accuracy':five_correct/len(five_eligible) if five_eligible else None},'latency_s':{'p50':float(np.percentile(times,50)) if times else None,'p95':float(np.percentile(times,95)) if times else None}}
