"""Bounded, separated, uniform-rate tax checks; ambiguity remains review.

This verifies arithmetic and the imported PO classification. It is not tax
advice. Inclusive, mixed-rate or component-only layouts require manual handling.
"""
from dataclasses import asdict
from decimal import Decimal, ROUND_HALF_UP
import re
from reconcile.invoice_parser import Reading, resolve, text_rows


def read_tax_rate(pages):
    kinds={}
    for row in text_rows(pages):
        m=re.search(r'\b(CGST|SGST|IGST|GST|TAX|VAT)\b\s*(?:@|rate|:)?\s*(\d{1,2}(?:\.\d{1,4})?)\s*%',row.text,re.I)
        if m:
            kinds.setdefault(m[1].upper(),[]).append((str(Decimal(m[2])/100),row.evidence()))
    if not kinds:return asdict(Reading(None,'missing'))
    resolved={kind:resolve(values) for kind,values in kinds.items()}
    if any(r.status!='found' for r in resolved.values()):
        return asdict(Reading(None,'ambiguous',tuple(e for r in resolved.values() for e in r.evidence)))
    if set(resolved)=={'CGST','SGST'}:
        return asdict(Reading(str(sum(Decimal(r.value) for r in resolved.values())),'found',tuple(e for r in resolved.values() for e in r.evidence)))
    if len(resolved)==1 and not set(resolved)&{'CGST','SGST'}:
        return asdict(next(iter(resolved.values())))
    return asdict(Reading(None,'ambiguous',tuple(e for r in resolved.values() for e in r.evidence)))


def check_tax(document, company, normalized_lines, po_id):
    unknown={'status':'unknown','reason':'TAX_EVIDENCE_UNRESOLVED','details':[]}
    if document.get('subtotal') is None or document.get('tax_total') is None or not normalized_lines:
        return unknown
    po=next((p for p in company['purchase_orders'] if p['id']==po_id),None)
    if not po:return unknown
    targets={l['id']:l for l in po['lines']}
    rates={targets[l['po_line_id']].get('tax_rate') for l in normalized_lines}
    if None in rates or len(rates)!=1:
        return {**unknown,'details':['The order must provide one uniform tax classification; missing or mixed rates require review.']}
    expected_rate=Decimal(next(iter(rates)))
    printed_rate=Decimal(document['tax_rate']) if document.get('tax_rate') is not None else None
    tax=Decimal(document['tax_total'])
    if printed_rate is None:
        if tax==0 and expected_rate==0:
            return {'status':'pass','reason':'EXPLICIT_ZERO_TAX_MATCHES_ORDER','details':[]}
        return {**unknown,'details':['Verify the printed or human-attested combined tax rate. Do not infer it from the order.']}
    if printed_rate!=expected_rate:
        return {**unknown,'reason':'TAX_CLASSIFICATION_CONFLICT','details':[f'Invoice rate {printed_rate}; order rate {expected_rate}. Verify the classification.']}
    expected=(Decimal(document['subtotal'])*printed_rate).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
    return {'status':'pass' if abs(expected-tax)<=Decimal('.10') else 'fail',
        'reason':'SEPARATED_TAX_ARITHMETIC','line_checks':[{'taxable':document['subtotal'],'rate':str(printed_rate),
        'expected_tax':str(expected),'actual_tax':str(tax),'tolerance':'0.10'}]}
