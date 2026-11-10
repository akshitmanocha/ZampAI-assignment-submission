"""SQL history checks and atomic approval. No model can change the ledger."""
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
import re
import uuid
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from reconcile.models import Vendor, PurchaseOrder, POLine, Invoice, InvoiceLine, Approval, Allocation


class HistoryConflict(Exception):
    def __init__(self,code):
        self.code=code
        super().__init__(code)


def identifier_key(value):
    # Candidate evidence only: canonical collisions are NOT exact duplicate proof.
    return re.sub(r'[\s\-/._]', '', value).upper()


def find_duplicates(session: Session, vendor_id, invoice_number, document_sha256, gross_total, exclude_id=None):
    """Different vendors never collide on invoice number alone. Rejected history is visible."""
    q=select(Invoice).where((Invoice.document_sha256==document_sha256) | ((Invoice.vendor_id==vendor_id) & (Invoice.invoice_number_key==identifier_key(invoice_number))))
    if exclude_id is not None:q=q.where(Invoice.id!=exclude_id)
    result=[]
    for invoice in session.scalars(q.order_by(Invoice.uploaded_at,Invoice.id)):
        same_file=invoice.document_sha256==document_sha256
        exact_number=invoice.vendor_id==vendor_id and invoice.invoice_number==invoice_number
        kind='exact_file' if same_file else 'same_vendor_number' if exact_number and invoice.gross_total==gross_total else 'possible_revision' if exact_number else 'identifier_collision'
        result.append({'invoice_id':str(invoice.id),'kind':kind,'review_state':invoice.review_state,'gross_total':str(invoice.gross_total)})
    return result


def remaining_balance(session: Session, po_line_id):
    line=session.get(POLine,po_line_id)
    if line is None:raise HistoryConflict('PO_LINE_NOT_FOUND')
    qty,amount=session.execute(select(func.coalesce(func.sum(Allocation.qty),0),func.coalesce(func.sum(Allocation.net_amount),0)).where(Allocation.po_line_id==po_line_id)).one()
    return {'ordered_qty':line.ordered_qty,'approved_qty':qty,'remaining_qty':line.ordered_qty-qty,'approved_net_amount':amount,'remaining_net_amount':line.ordered_qty*line.unit_price-amount,'allocations_version':line.allocations_version}


def previous_purchases(session: Session,vendor_id,limit=100):
    """Bounded SQL candidates for later lexical/ML ranking; never authorization."""
    if not 1<=limit<=100:raise ValueError('limit must be between 1 and 100')
    q=select(POLine,PurchaseOrder).join(PurchaseOrder,POLine.po_id==PurchaseOrder.id).where(PurchaseOrder.vendor_id==vendor_id).order_by(PurchaseOrder.order_date.desc(),PurchaseOrder.id,POLine.line_no).limit(limit)
    return [{'po_line_id':str(line.id),'po_number':po.po_number,'po_status':po.status,'item_code':line.item_code,'description':line.description,'attributes':line.attributes,'uom':line.uom,'unit_price':str(line.unit_price)} for line,po in session.execute(q)]


def approve_invoice(session: Session,invoice_id,expected_decision_version,actor):
    """Caller owns the transaction. Only trusted, validated decisions may enter.

    Locks vendor -> PO -> invoice -> PO lines in stable order. READ COMMITTED is
    required so a contender sees allocations committed while it waited.
    """
    preview=session.get(Invoice,invoice_id)
    if preview is None:raise HistoryConflict('INVOICE_NOT_FOUND')
    vendor=session.scalar(select(Vendor).where(Vendor.id==preview.vendor_id).with_for_update().execution_options(populate_existing=True))
    po=session.scalar(select(PurchaseOrder).where(PurchaseOrder.id==preview.po_id).with_for_update().execution_options(populate_existing=True))
    inv=session.scalar(select(Invoice).where(Invoice.id==invoice_id).with_for_update().execution_options(populate_existing=True))
    if inv.review_state=='approved':
        return {'status':'already_approved','approval_id':str(session.scalar(select(Approval.id).where(Approval.invoice_id==inv.id)))}
    if inv.review_state!='open':raise HistoryConflict('INVOICE_CLOSED')
    if inv.decision_version!=expected_decision_version:raise HistoryConflict('DECISION_VERSION_CONFLICT')
    if inv.recommendation!='ready_for_approval':raise HistoryConflict('NOT_APPROVABLE')
    if vendor.status!='approved':raise HistoryConflict('VENDOR_NOT_APPROVED')
    if po.vendor_id!=inv.vendor_id:raise HistoryConflict('VENDOR_PO_CONFLICT')
    if po.status!='open':raise HistoryConflict('PO_NOT_OPEN')
    if po.currency!=inv.currency or inv.currency!='INR':raise HistoryConflict('CURRENCY_CONFLICT')
    duplicates=find_duplicates(session,inv.vendor_id,inv.invoice_number,inv.document_sha256,inv.gross_total,exclude_id=inv.id)
    if any(d['review_state']!='rejected' for d in duplicates):raise HistoryConflict('DUPLICATE_REVIEW_REQUIRED')
    lines=list(session.scalars(select(InvoiceLine).where(InvoiceLine.invoice_id==inv.id).order_by(InvoiceLine.id)))
    if not lines:raise HistoryConflict('NO_INVOICE_LINES')
    ids=sorted({line.po_line_id for line in lines})
    po_lines={line.id:line for line in session.scalars(select(POLine).where(POLine.id.in_(ids)).order_by(POLine.id).with_for_update().execution_options(populate_existing=True))}
    requested=defaultdict(lambda:Decimal('0'))
    for line in lines:
        target=po_lines.get(line.po_line_id)
        if target is None or target.po_id!=po.id:raise HistoryConflict('PO_LINE_CONFLICT')
        if not line.evidence:raise HistoryConflict('EVIDENCE_MISSING')
        # Conservative exact-price initial policy; configurable tolerance comes later.
        if line.normalized_unit_price!=target.unit_price:raise HistoryConflict('PRICE_CONFLICT')
        requested[target.id]+=line.normalized_qty
    for line_id,qty in requested.items():
        if qty>remaining_balance(session,line_id)['remaining_qty']:raise HistoryConflict('APPROVAL_STALE')
    approval=Approval(invoice_id=inv.id,actor=actor);session.add(approval);session.flush()
    for line in lines:
        session.add(Allocation(approval_id=approval.id,invoice_line_id=line.id,po_line_id=line.po_line_id,qty=line.normalized_qty,net_amount=(line.normalized_qty*line.normalized_unit_price).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)))
    for line in po_lines.values():line.allocations_version+=1
    inv.review_state='approved';session.flush()
    return {'status':'approved','approval_id':str(approval.id)}


def rank_previous_purchases(session: Session,vendor_id,description,limit=5):
    """Rank vendor-scoped historical candidates; a suggestion is NOT permission.

    Uses lexical TF-IDF screening. The GPU pilot is not promoted into the live
    approval path. Closed orders may be useful history but cannot authorize a
    new invoice. Unseen/no-overlap descriptions get no forced match.
    """
    from sklearn.feature_extraction.text import TfidfVectorizer
    if not description.strip():return []
    if not 1<=limit<=20:raise ValueError('limit must be between 1 and 20')
    candidates=previous_purchases(session,vendor_id,limit=100)
    if not candidates:return []
    vectorizer=TfidfVectorizer(analyzer='char_wb',ngram_range=(3,5))
    matrix=vectorizer.fit_transform([r['description'] for r in candidates])
    query=vectorizer.transform([description])
    scores=(matrix@query.T).toarray().ravel()
    ranked=sorted(zip(candidates,scores),key=lambda pair:(-pair[1],pair[0]['po_line_id']))
    return [{**row,'similarity':float(score),'evidence_type':'historical_similarity_only','authorizes_invoice':False} for row,score in ranked if score>0][:limit]
