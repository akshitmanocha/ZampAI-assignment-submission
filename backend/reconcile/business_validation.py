"""Bounded deterministic procurement validation over a company snapshot.

No fixture IDs, expected labels, filenames, or model scores enter this module.
Exact printed SKU plus explicit attributes supplies the baseline identity check.
Unresolved identity/conversion stays review; learned matching is not enabled.
"""
from collections import defaultdict
from copy import deepcopy
from dataclasses import asdict
from datetime import date
from decimal import Decimal,ROUND_HALF_UP,InvalidOperation
import re
from reconcile.invoice_routing import Finding,route_invoice
from reconcile.matching_review import MatchRoute
from reconcile.history import identifier_key


def money(value):
    if not isinstance(value,(str,Decimal)):raise ValueError('Amounts/quantities must be decimal strings')
    d=Decimal(value)
    if not d.is_finite():raise ValueError('Nonfinite numeric input')
    return d


def key(value):return re.sub(r'\s+','',value or '').casefold()


def attributes(description):
    text=description or ''
    sku=re.match(r'^([A-Za-z][A-Za-z0-9-]{1,})\b',text)
    mats=set(re.findall(r'\b(nitrile|latex|steel|brass|nylon|paper)\b',text,re.I))
    sizes=set(re.findall(r'\b(medium|small|large|M\d+)\b',text,re.I))
    unit=re.search(r'\[(BOX|EA)\b',text,re.I)
    pack=re.search(r'\b(\d+)\s*EA\s*/\s*box\b',text,re.I)
    return {'sku':sku.group(1) if sku else None,'material':next(iter(mats)).lower() if len(mats)==1 else None,'size':next(iter(sizes)).lower() if len(sizes)==1 else None,'unit':unit.group(1).upper() if unit else None,'pack':pack.group(1) if pack else None}


def from_extraction(extracted):
    """Missing/ambiguous/invalid readings stay None. No oracle or PO repair."""
    def read(value):return value.get('value') if value.get('status')=='found' else None
    names=['vendor_name','invoice_number','invoice_date','po_reference','currency','subtotal','tax_total','grand_total']
    result={name:read(extracted['header'].get(name,{})) for name in names}
    result['lines']=[{name:read(line.get(name,{})) for name in ['description','qty','unit_price','amount']} for line in extracted['lines']]
    result['source_warnings']=extracted.get('warnings',[])
    return result


def product(line,po):
    attrs=attributes(line.get('description'))
    if not attrs['sku']:return None,'unknown'
    matches=[p for p in po['lines'] if key(p['sku'])==key(attrs['sku'])]
    if len(matches)!=1:return None,'unknown'
    candidate=matches[0]
    for name in ['material','size']:
        if not attrs[name] or not candidate.get(name):return None,'unknown'
        if key(attrs[name])!=key(candidate[name]):return candidate,'conflict'
    return candidate,'matched'


def validate(document,company,document_sha256,*,today):
    """Pure recommendation. Caller injects the business date; no fixed production clock. History is input only; never consumes balances."""
    d=document;results={};details={};values={'normalized_qty':[],'normalized_unit_price':[],'remaining_qty':[],'price_tolerance':[],'excess_qty':[],'requested_by_po_line':{}}
    def finding(rule,status,reason,**data):
        results[rule]=Finding(rule,status,status!='unknown');details[rule]={'status':status,'reason':reason,**data}
    finding('scope','pass' if d.get('currency')=='INR' else 'unknown','INR_SCOPE' if d.get('currency')=='INR' else 'UNSUPPORTED_OR_UNCLEAR_CURRENCY')
    vendors=[v for v in company['vendors'] if key(v['legal_name'])==key(d.get('vendor_name'))]
    vendor=vendors[0] if len(vendors)==1 else None
    finding('vendor_identity','pass' if vendor else 'unknown','VENDOR_EXACT_NAME' if vendor else 'VENDOR_UNRESOLVED')
    finding('vendor_status','pass' if vendor and vendor['status']=='approved' else 'fail' if vendor and vendor['status']=='blocked' else 'unknown','VENDOR_STATUS',actual=vendor['status'] if vendor else None)
    po=None
    if d.get('po_reference'):
        candidates=[p for p in company['purchase_orders'] if key(p['number'])==key(d['po_reference'])]
        if len(candidates)==1:
            proposed=candidates[0]
            if vendor and proposed['vendor_id']!=vendor['id']:
                finding('vendor_identity','fail','VENDOR_PO_CONFLICT')
                finding('purchase_order','unknown','PO_VENDOR_NOT_AUTHORIZED')
            elif vendor:
                po=proposed;finding('purchase_order','pass' if po['status']=='open' else 'fail','PO_STATUS',actual=po['status'])
    elif vendor and d['lines']:
        candidates=[p for p in company['purchase_orders'] if p['vendor_id']==vendor['id'] and p['status']=='open' and p['currency']==d.get('currency') and all(product(line,p)[1]=='matched' for line in d['lines'])]
        if len(candidates)==1:po=candidates[0];finding('purchase_order','pass','UNIQUE_VENDOR_PO_INFERRED')
        else:finding('purchase_order','unknown','PO_CANDIDATES_UNRESOLVED',candidate_ids=[p['id'] for p in candidates])
    if 'purchase_order' not in results:finding('purchase_order','unknown','PO_UNRESOLVED')
    required=['vendor_name','invoice_number','invoice_date','currency','subtotal','tax_total','grand_total']
    missing=[name for name in required if d.get(name) is None]
    if not d['lines']:missing.append('lines')
    for i,line in enumerate(d['lines']):
        missing.extend(f'lines[{i+1}].{name}' for name in ['description','qty','unit_price','amount'] if line.get(name) is None)
    if d.get('invoice_date'):
        try:
            if date.fromisoformat(d['invoice_date'])>date.fromisoformat(today):missing.append('invoice_date_future')
        except ValueError:missing.append('invoice_date_invalid')
    finding('required_fields','unknown' if missing else 'pass','MISSING_OR_INVALID_FIELDS' if missing else 'REQUIRED_FIELDS_PRESENT',fields=missing)
    numeric=bool(d['lines']);arithmetic=True
    try:
        for line in d['lines']:
            if any(line.get(k) is None for k in ['qty','unit_price','amount']):numeric=False;break
            if money(line['qty'])<=0 or money(line['unit_price'])<0:arithmetic=False
            extension=(money(line['qty'])*money(line['unit_price'])).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
            if extension!=money(line['amount']):arithmetic=False
        if any(d.get(k) is None for k in ['subtotal','tax_total','grand_total']):numeric=False
        if numeric:
            if sum((money(l['amount']) for l in d['lines']),Decimal('0'))!=money(d['subtotal']):arithmetic=False
            if money(d['subtotal'])+money(d['tax_total'])!=money(d['grand_total']):arithmetic=False
        finding('arithmetic','unknown' if not numeric else 'pass' if arithmetic else 'fail','PRINTED_ARITHMETIC',subtotal=d.get('subtotal'),tax=d.get('tax_total'),total=d.get('grand_total'))
    except (ValueError,InvalidOperation):finding('arithmetic','unknown','UNPARSEABLE_NUMBER')
    duplicates=[];revision=False
    if vendor:
        for prior in company.get('invoice_history',[]):
            if prior['review_state']=='rejected':continue
            same_file=prior['document_sha256']==document_sha256
            exact=prior['vendor_id']==vendor['id'] and prior['invoice_number']==d.get('invoice_number')
            if same_file or exact:
                if same_file or (d.get('grand_total') is not None and money(prior['gross_total'])==money(d['grand_total'])):duplicates.append(prior)
                else:revision=True
            elif prior['vendor_id']==vendor['id'] and d.get('invoice_number') and identifier_key(prior['invoice_number'])==identifier_key(d['invoice_number']):
                revision=True
    finding('duplicate','fail' if duplicates else 'unknown' if revision or not vendor or not d.get('invoice_number') else 'pass','DUPLICATE_FOUND' if duplicates else 'REVISION_OR_ID_UNRESOLVED' if revision or not d.get('invoice_number') else 'NO_PRIOR_DUPLICATE')
    def merge_status(a,b):return 'fail' if 'fail' in (a,b) else 'unknown' if 'unknown' in (a,b) else 'pass'
    spec='pass';conversion='pass';price='pass';quantity='pass';normalized=[];matched_ids=[]
    requested=defaultdict(lambda:Decimal('0'));line_lookup={};price_checks=[];quantity_checks=[]
    if po is None or po['status']!='open' or not d['lines']:spec=conversion=price=quantity='unknown'
    else:
        for i,line in enumerate(d['lines']):
            matched,status=product(line,po)
            if status=='conflict':
                spec='fail';conversion,price,quantity=[merge_status(x,'unknown') for x in [conversion,price,quantity]];continue
            if status!='matched':
                if spec!='fail':spec='unknown'
                conversion,price,quantity=[merge_status(x,'unknown') for x in [conversion,price,quantity]];continue
            matched_ids.append(matched['id']);line_lookup[matched['id']]=matched
            attrs=attributes(line.get('description'));factor=Decimal('1') if attrs['unit']=='EA' else money(attrs['pack']) if attrs['unit']=='BOX' and attrs['pack'] is not None else None
            if factor is None or factor<=0 or matched['uom']!='EA':
                conversion,price,quantity=[merge_status(x,'unknown') for x in [conversion,price,quantity]];continue
            if any(line.get(k) is None for k in ['qty','unit_price','amount']):
                price,quantity=[merge_status(x,'unknown') for x in [price,quantity]];continue
            try:
                qty=money(line['qty'])*factor;unit_price=money(line['unit_price'])/factor
            except (ValueError,InvalidOperation):
                price,quantity=[merge_status(x,'unknown') for x in [price,quantity]];continue
            tolerance=max(money(company['policy']['absolute_unit_price_tolerance']),abs(money(matched['unit_price']))*money(company['policy']['relative_unit_price_tolerance']))
            price_bad=abs(unit_price-money(matched['unit_price']))>tolerance
            price_checks.append({'source_line':i+1,'po_line_id':matched['id'],'actual_unit_price':format(unit_price,'f'),'expected_unit_price':matched['unit_price'],'delta':format(unit_price-money(matched['unit_price']),'f'),'tolerance':format(tolerance,'f'),'status':'fail' if price_bad else 'pass'})
            if price_bad:price='fail'
            values['normalized_qty'].append(format(qty,'f'));values['normalized_unit_price'].append(format(unit_price,'f'));values['price_tolerance'].append(format(tolerance,'f'))
            requested[matched['id']]+=qty
            normalized.append({'source_line':i+1,'po_line_id':matched['id'],'qty':format(qty,'f'),'unit_price':format(unit_price,'f'),'printed_amount':line['amount'],'evidence':{'description':line['description'],'qty':line['qty'],'unit_price':line['unit_price'],'pack_factor':format(factor,'f')}})
        for line_id,qty in requested.items():
            target=line_lookup[line_id]
            allocated=sum((money(a['qty']) for a in company['allocations'] if a['po_line_id']==line_id),Decimal('0'))
            remaining=money(target['ordered_qty'])-allocated
            values['remaining_qty'].append(format(remaining,'f'));values['excess_qty'].append(format(max(Decimal('0'),qty-remaining),'f'))
            values['requested_by_po_line'][line_id]=format(qty,'f')
            quantity_checks.append({'po_line_id':line_id,'requested':format(qty,'f'),'remaining':format(remaining,'f'),'excess':format(max(Decimal('0'),qty-remaining),'f'),'status':'fail' if qty>remaining else 'pass'})
            if qty>remaining:quantity='fail'
    for rule,status in [('product_specification',spec),('unit_conversion',conversion),('unit_price',price),('remaining_quantity',quantity)]:finding(rule,status,rule.upper(),values=values)
    details['unit_price']['line_checks']=price_checks
    details['remaining_quantity']['line_checks']=quantity_checks
    match=MatchRoute('matched' if spec=='pass' and matched_ids else 'needs_review',matched_ids[0] if spec=='pass' and matched_ids else None,'deterministic_printed_sku_and_explicit_attributes',())
    route=route_invoice(results.values(),match)
    return {'bucket':route.bucket,'blocking_rules':sorted(k for k,v in results.items() if v.status=='fail' and v.evidence_verified),'unknown_rules':sorted(k for k,v in results.items() if v.status=='unknown'),'findings':details,'values':values,'po_id':po['id'] if po else None,'matched_po_line_ids':matched_ids,'normalized_lines':normalized,'history_mutated':False,'matcher':'exact printed SKU plus explicit attributes; no learned scoring','scope':'bounded two-way INR invoice validation over supplied company snapshot'}
