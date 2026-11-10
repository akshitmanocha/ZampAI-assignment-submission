"""Read a company snapshot from PostgreSQL; contains no validation labels."""
from sqlalchemy import select
from reconcile.models import Vendor,PurchaseOrder,POLine,Invoice,Allocation


def snapshot(session,policy,exclude_invoice_id=None):
    vendors=[{'id':str(v.id),'legal_name':v.legal_name,'status':v.status} for v in session.scalars(select(Vendor))]
    orders=[]
    for p in session.scalars(select(PurchaseOrder).order_by(PurchaseOrder.id)):
        lines=[{'id':str(l.id),'sku':l.item_code,'description':l.description,'material':l.attributes.get('material'),'size':l.attributes.get('size'),'uom':l.uom,'ordered_qty':str(l.ordered_qty),'unit_price':str(l.unit_price)} for l in session.scalars(select(POLine).where(POLine.po_id==p.id).order_by(POLine.line_no))]
        orders.append({'id':str(p.id),'number':p.po_number,'vendor_id':str(p.vendor_id),'status':p.status,'currency':p.currency,'lines':lines})
    allocations=[{'po_line_id':str(a.po_line_id),'qty':str(a.qty),'amount':str(a.net_amount)} for a in session.scalars(select(Allocation))]
    q=select(Invoice)
    if exclude_invoice_id is not None:q=q.where(Invoice.id!=exclude_invoice_id)
    history=[{'vendor_id':str(i.vendor_id),'invoice_number':i.invoice_number,'gross_total':str(i.gross_total),'document_sha256':i.document_sha256,'review_state':i.review_state} for i in session.scalars(q)]
    return {'vendors':vendors,'purchase_orders':orders,'allocations':allocations,'invoice_history':history,'policy':dict(policy)}
