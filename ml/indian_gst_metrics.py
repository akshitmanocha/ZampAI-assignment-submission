"""Fixed publisher-label scoring. This module never extracts or repairs fields."""
from collections import Counter
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
import re
import unicodedata
import numpy as np
from scipy.optimize import linear_sum_assignment

VERSION = 'indian-gst-extraction-metrics-v1'
CORE = {
    'vendor_name':('supplier','name'), 'invoice_number':('invoice_number',),
    'invoice_date':('invoice_date',), 'subtotal':('totals','taxable_value'),
    'grand_total':('totals','grand_total'),
}
EXTRA = {
    'supplier_gstin':('supplier','gstin'), 'supplier_address':('supplier','address'),
    'supplier_state':('supplier','state'), 'buyer_name':('buyer','name'),
    'buyer_gstin':('buyer','gstin'), 'buyer_address':('buyer','address'),
    'buyer_state':('buyer','state'), 'place_of_supply':('place_of_supply',),
    'supply_type':('supply_type',), 'reverse_charge':('reverse_charge',),
    'cgst_total':('totals','cgst'), 'sgst_total':('totals','sgst'),
    'igst_total':('totals','igst'), 'round_off':('totals','round_off'),
}
ROW_CORE = {'description':'description','qty':'quantity','unit_price':'rate','amount':'taxable_value'}
ROW_EXTRA = {'unit':'unit','hsn_sac':'hsn_sac','gst_rate':'gst_rate',
    'cgst_amount':'cgst_amount','sgst_amount':'sgst_amount','igst_amount':'igst_amount','gross_amount':'total'}
NUMBERS = {'subtotal','grand_total','cgst_total','sgst_total','igst_total','round_off',
    'qty','unit_price','amount','gst_rate','cgst_amount','sgst_amount','igst_amount','gross_amount'}


def at(value, path):
    for name in path:
        if not isinstance(value,dict):return None
        value=value.get(name)
    return value


def text(value):
    return re.sub(r'\s+',' ',unicodedata.normalize('NFKC',str(value))).strip().casefold()


def equal(field,a,b):
    if a is None or b is None:return a is None and b is None
    if field in NUMBERS:
        try:
            left,right=Decimal(str(a)),Decimal(str(b))
            return left.is_finite() and right.is_finite() and left==right
        except (InvalidOperation,ValueError):return False
    if field=='invoice_number':
        # Do not erase leading zeros, separators or meaningful suffixes.
        return re.sub(r'\s+','',str(a)).casefold()==re.sub(r'\s+','',str(b)).casefold()
    return text(a)==text(b)


def reading(field):
    return field if isinstance(field,dict) else {'value':None,'status':'missing'}


def found(field,verified):
    field=reading(field)
    return field.get('status')=='found' and field.get('value') is not None and not (
        verified and field.get('requires_source_verification'))


def pairs(predicted,gold):
    """Align by description only; numeric values never choose their best gold row."""
    if not predicted or not gold:return []
    matrix=np.array([[SequenceMatcher(None,text(reading(p.get('description')).get('value') or ''),text(g.get('description') or '')).ratio() for g in gold] for p in predicted])
    ii,jj=linear_sum_assignment(-matrix)
    return [(int(i),int(j)) for i,j in zip(ii,jj) if matrix[i,j]>=.65]


def count_cell(counter,field,prediction,gold,verified):
    is_found=found(prediction,verified)
    counter['cells']+=1
    counter['labelled_non_null']+=gold is not None
    counter['predicted_found']+=is_found
    correct=gold is not None and is_found and equal(field,reading(prediction).get('value'),gold)
    counter['correct']+=correct
    counter['predicted_when_label_null']+=gold is None and is_found
    counter['correct_absence']+=gold is None and not is_found
    return correct


def finish_counts(counter):
    c=dict(counter)
    for key in ['cells','labelled_non_null','predicted_found','correct','predicted_when_label_null','correct_absence']:
        c.setdefault(key,0)
    c['recall_on_non_null_labels']=c['correct']/c['labelled_non_null'] if c['labelled_non_null'] else None
    c['precision_of_found_values']=c['correct']/c['predicted_found'] if c['predicted_found'] else None
    return c


def score(records,verified=False):
    headers={name:Counter() for name in CORE|EXTRA}
    row_fields={name:Counter() for name in ROW_CORE|ROW_EXTRA}
    complete_rows=Counter()
    core_docs=Counter()
    for record in records:
        gold=record['gold'];prediction=record.get('prediction') or {'header':{},'lines':[]}
        for field,path in (CORE|EXTRA).items():
            count_cell(headers[field],field,prediction.get('header',{}).get(field),at(gold,path),verified)
        if all(at(gold,path) is not None for path in CORE.values()):
            core_docs['eligible']+=1
            complete=all(found(prediction.get('header',{}).get(name),verified) for name in CORE)
            correct=all(found(prediction.get('header',{}).get(name),verified) and equal(name,reading(prediction['header'][name]).get('value'),at(gold,path)) for name,path in CORE.items())
            core_docs['complete']+=complete
            core_docs['correct']+=correct
        predicted=prediction.get('lines',[]);expected=gold['line_items']
        alignment=pairs(predicted,expected)
        by_gold={j:i for i,j in alignment};matched_pred={i for i,_ in alignment}
        complete_rows['predicted']+=len(predicted)
        complete_rows['labelled']+=len(expected)
        for j,row in enumerate(expected):
            p=predicted[by_gold[j]] if j in by_gold else {}
            for name,target in (ROW_CORE|ROW_EXTRA).items():
                count_cell(row_fields[name],name,p.get(name),row.get(target),verified)
            if j in by_gold and all(
                (not found(p.get(name),verified) if row.get(target) is None else
                 found(p.get(name),verified) and equal(name,reading(p.get(name)).get('value'),row[target]))
                for name,target in ROW_CORE.items()):
                complete_rows['true_positive']+=1
        for i,p in enumerate(predicted):
            if i in matched_pred:continue
            # Unmatched predictions count as false proposals, not invisible rows.
            for name in ROW_CORE|ROW_EXTRA:
                count_cell(row_fields[name],name,p.get(name),None,verified)
    tp=complete_rows['true_positive'];n_pred=complete_rows['predicted'];n_gold=complete_rows['labelled']
    precision=tp/n_pred if n_pred else None;recall=tp/n_gold if n_gold else None
    row_f1=2*tp/(n_pred+n_gold) if n_pred+n_gold else None
    core={name:finish_counts(headers[name]) for name in CORE}
    extra={name:finish_counts(headers[name]) for name in EXTRA}
    total=Counter()
    for name in CORE:total.update(headers[name])
    eligible=core_docs['eligible'];complete=core_docs['complete'];correct=core_docs['correct']
    return {'documents':len(records),'technical_failures':sum(bool(r.get('technical_error')) for r in records),
        'core_headers':core,'core_header_micro':finish_counts(total),
        'additional_publisher_headers':extra,
        'row_fields':{k:finish_counts(v) for k,v in row_fields.items()},
        'complete_core_rows':{'true_positive':tp,'predicted':n_pred,'labelled':n_gold,
            'precision':precision,'recall':recall,'f1':row_f1},
        'all_five_core_headers':{'eligible_documents':eligible,'complete_predictions':complete,
            'correct_documents':correct,'accuracy':correct/eligible if eligible else None,
            'complete_prediction_coverage':complete/eligible if eligible else None,
            'precision_among_complete_predictions':correct/complete if complete else None}}


def summarize(records):
    if not records:raise RuntimeError('Cannot score zero documents')
    return {'raw_extracted':score(records,False),'source_verified':score(records,True)}
