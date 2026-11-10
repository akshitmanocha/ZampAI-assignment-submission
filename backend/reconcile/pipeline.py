"""Application orchestration over extracted fields, SQL facts and review evidence."""
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
import re
from sqlalchemy import select, or_, and_
from reconcile.business_validation import validate, key, money
from reconcile.company_records import snapshot
from reconcile.models import Submission, Decision
from reconcile.settings import POLICY, RECOMMENDATIONS, business_date
from reconcile.invoice_parser import PARSER_VERSION
from reconcile.retrieval import VERSION
from reconcile.tax_validation import check_tax


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def company_for(db, submission):
    company = snapshot(db, POLICY, exclude_invoice_id=submission.ledger_invoice_id)
    # Only earlier submissions can block a later copy. A subsequent accidental
    # upload must not make the first legitimate invoice impossible to approve.
    earlier = db.scalars(select(Submission).where(Submission.id != submission.id,
        Submission.review_state != 'rejected', or_(Submission.created_at < submission.created_at,
        and_(Submission.created_at == submission.created_at, Submission.id < submission.id))))
    for prior in earlier:
        if prior.ledger_invoice_id:
            for item in company['invoice_history']:
                if item.get('invoice_id') == str(prior.ledger_invoice_id):item['submission_id'] = str(prior.id)
            continue  # already present in trusted ledger history
        decision = db.scalar(select(Decision).where(Decision.submission_id == prior.id).order_by(Decision.version.desc()).limit(1))
        doc = decision.result['document'] if decision else {}
        vendors = [v for v in company['vendors'] if key(v['legal_name']) == key(doc.get('vendor_name'))]
        company['invoice_history'].append({'vendor_id': vendors[0]['id'] if len(vendors) == 1 else 'unresolved',
            'invoice_number': doc.get('invoice_number') or '', 'gross_total': doc.get('grand_total') or '0',
            'document_sha256': prior.document_hash, 'review_state': prior.review_state,
            'submission_id': str(prior.id)})
    return company


def evaluate(document, company, fingerprint, reviewed_lines=None):
    doc = deepcopy(document)
    invalid = []
    for name in ['subtotal', 'tax_total', 'grand_total', 'tax_rate']:
        value = doc.get(name)
        if value is not None and (not isinstance(value, str) or not re.fullmatch(r'\d{1,12}(?:\.\d{1,4})?', value)):
            doc[name] = None
            invalid.append(name)
    if doc.get('tax_rate') is not None and Decimal(doc['tax_rate']) > 1:
        doc['tax_rate'] = None
        invalid.append('tax_rate')
    for i, line in enumerate(doc['lines'], 1):
        for name in ['qty', 'unit_price', 'amount']:
            value = line.get(name)
            if value is not None and (not isinstance(value, str) or not re.fullmatch(r'\d{1,12}(?:\.\d{1,4})?', value)):
                line[name] = None
                invalid.append(f'lines[{i}].{name}')
    result = validate(doc, company, fingerprint, today=business_date(), reviewed_lines=reviewed_lines)
    po = next((p for p in company['purchase_orders'] if p['id'] == result['po_id']), None)
    checks = []
    for line_id in result['values']['requested_by_po_line']:
        target = next(l for l in po['lines'] if l['id'] == line_id)
        authorized = money(target['ordered_qty']) * money(target['unit_price'])
        allocated = sum((money(a['amount']) for a in company['allocations'] if a['po_line_id'] == line_id), Decimal('0'))
        amount = sum((money(l['printed_amount']) for l in result['normalized_lines'] if l['po_line_id'] == line_id), Decimal('0'))
        tolerance = max(money(POLICY['absolute_po_amount_tolerance']), authorized * money(POLICY['relative_po_amount_tolerance']))
        checks.append({'po_line_id': line_id, 'authorized': str(authorized), 'allocated': str(allocated),
            'requested': str(amount), 'remaining': str(authorized - allocated), 'tolerance': str(tolerance),
            'status': 'pass' if allocated + amount <= authorized + tolerance else 'fail'})
    amount_status = 'fail' if any(c['status'] == 'fail' for c in checks) else 'pass' if checks and len(result['normalized_lines']) == len(doc['lines']) else 'unknown'
    result['findings']['po_amount'] = {'status': amount_status, 'reason': 'CUMULATIVE_PO_NET_AMOUNT', 'line_checks': checks}
    if amount_status == 'fail':
        result['blocking_rules'].append('po_amount')
    elif amount_status == 'unknown':
        result['unknown_rules'].append('po_amount')
    scope_reasons = list(document.get('unsupported_features', []))
    if len(doc['lines']) > 100:
        scope_reasons.append('More than 100 invoice lines')
    if po and doc.get('invoice_date') and po.get('order_date') and doc['invoice_date'] < po['order_date']:
        result['unknown_rules'].append('invoice_predates_order')
    tax = check_tax(doc, company, result['normalized_lines'], result['po_id'])
    result['findings']['tax'] = tax
    if tax['status'] == 'fail':
        result['blocking_rules'].append('tax')
    elif tax['status'] == 'unknown':
        result['unknown_rules'].append('tax')
    if invalid:
        result['unknown_rules'].append('invalid_numeric_format')
    if any(money(line[k]) != money(line[k]).quantize(Decimal('.0001')) for line in result['normalized_lines'] for k in ['qty','unit_price']):
        result['unknown_rules'].append('normalization_precision')
    if scope_reasons:
        # Unsupported tax/credit/bundle bases cannot justify price/arithmetic
        # rejections. Keep independently confirmed supplier/duplicate blockers.
        result['blocking_rules'] = [r for r in result['blocking_rules'] if r in ['vendor_identity', 'vendor_status', 'duplicate', 'purchase_order', 'product_specification']]
        result['unknown_rules'].append('supported_scope')
        result['findings']['supported_scope'] = {'status': 'unknown', 'reason': 'MANUAL_SCOPE_REVIEW', 'details': scope_reasons}
    result['bucket'] = 'reject' if result['blocking_rules'] else 'human_review' if result['unknown_rules'] else result['bucket']
    result.update(recommendation=RECOMMENDATIONS[result['bucket']], document=doc,
        reviewed_lines=deepcopy(reviewed_lines or {}), policy=deepcopy(POLICY),
        versions={'parser': PARSER_VERSION, 'matcher': VERSION, 'policy': POLICY['version'], 'source_quality':'ocr-minimum-word-score-60-v1','tax_extractor':'uniform-separated-tax-v1'},
        company_snapshot=company, inputs_fingerprint=canonical_hash({'document': doc, 'company': company, 'reviews': reviewed_lines}),
        numeric_warnings=invalid)
    return result


def unsupported_features(pages):
    text = ' '.join(w['text'] for p in pages for w in p['words'])
    patterns = {
        'Tax-inclusive pricing needs manual verification': r'\b(?:inclusive of|including|incl\.?|embedded)\s+(?:gst|tax)|\btax[- ]inclusive\b',
        'Credit notes require a separate process': r'\bcredit\s+note\b',
        'Bundles require component evidence': r'\b(?:bundle|kit of|assorted set)\b',
        'Discounts or additional charges require manual allocation': r'\b(?:discount|freight|shipping|surcharge)\b',
    }
    found = [reason for reason, pattern in patterns.items() if re.search(pattern, text, re.I)]
    refs = set(re.findall(r'\bPO[-/]\d[\w/-]*', text, re.I))
    if len(refs) > 1:
        found.append('Multiple purchase orders require a separate process')
    return found
