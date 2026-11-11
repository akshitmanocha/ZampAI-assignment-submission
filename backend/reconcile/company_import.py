"""Explicit administrator CLI import of supplier and purchase-order master data.

Never accepts allocations, invoice history or a policy. Existing allocated
quantities and amounts cannot be erased by replacing an order line.
"""
from datetime import date
from decimal import Decimal
from sqlalchemy import select
from reconcile.models import Vendor, PurchaseOrder, POLine
from reconcile.history import remaining_balance
from reconcile.business_validation import money, key
from reconcile.workflows import audit


def import_company(db, data):
    if not isinstance(data, dict) or set(data) != {'vendors','purchase_orders'}:
        raise ValueError('Use exactly vendors and purchase_orders; ledger and policy imports are prohibited')
    if not isinstance(data['vendors'],list) or not isinstance(data['purchase_orders'],list) or len(data['purchase_orders'])>1000:
        raise ValueError('Invalid company import size')
    for row in sorted(data['vendors'],key=lambda v:v['legal_name']):
        if set(row)-{'legal_name','status'} or not isinstance(row['legal_name'],str) or not 1<=len(row['legal_name'])<=250 or row.get('status','approved') not in ['approved','pending','blocked']:
            raise ValueError('Invalid supplier')
        vendors=list(db.scalars(select(Vendor).order_by(Vendor.id)))
        matched=[v for v in vendors if key(v.legal_name)==key(row['legal_name'])]
        if len(matched)>1:raise ValueError('Ambiguous supplier name')
        if matched:
            vendor=db.scalar(select(Vendor).where(Vendor.id==matched[0].id).with_for_update())
            vendor.status=row.get('status','approved')
        else:db.add(Vendor(legal_name=row['legal_name'],status=row.get('status','approved')))
        db.flush()
    for row in sorted(data['purchase_orders'],key=lambda p:p['number']):
        if set(row)-{'number','vendor_name','status','currency','order_date','lines'} or row.get('currency','INR')!='INR' or row.get('status','open') not in ['open','closed','cancelled']:
            raise ValueError('Invalid purchase order')
        vendor=next((v for v in db.scalars(select(Vendor)) if key(v.legal_name)==key(row['vendor_name'])),None)
        if not vendor:raise ValueError('Order supplier must exist in the supplier master')
        db.scalar(select(Vendor).where(Vendor.id==vendor.id).with_for_update())
        po=db.scalar(select(PurchaseOrder).where(PurchaseOrder.po_number==row['number']).with_for_update())
        if not po:
            po=PurchaseOrder(po_number=row['number'],vendor_id=vendor.id);db.add(po);db.flush()
        elif po.vendor_id!=vendor.id:raise ValueError('An existing order cannot be transferred to another supplier')
        po.status,po.currency,po.order_date=row.get('status','open'),'INR',date.fromisoformat(row['order_date'])
        po.revision+=1
        if not 1<=len(row['lines'])<=100:raise ValueError('Use 1 to 100 order lines')
        existing=list(db.scalars(select(POLine).where(POLine.po_id==po.id).order_by(POLine.id).with_for_update()))
        if len(existing)>len(row['lines']):raise ValueError('Existing order lines cannot be deleted; close the order instead')
        for number,item in enumerate(row['lines'],1):
            if set(item)-{'sku','description','material','size','uom','ordered_qty','unit_price','tax_rate'}:raise ValueError('Unknown order-line fields')
            if item.get('tax_rate') is not None and not Decimal('0')<=money(item['tax_rate'])<=Decimal('1'):raise ValueError('Tax rate must be a decimal fraction from 0 to 1')
            qty,price=money(item['ordered_qty']),money(item['unit_price'])
            if qty<=0 or price<0 or qty!=qty.quantize(Decimal('.0001')) or price!=price.quantize(Decimal('.0001')) or item['uom']!='EA':raise ValueError('Use positive EA quantities and nonnegative prices, with at most four decimal places')
            line=next((l for l in existing if l.line_no==number),None)
            if line:
                balance=remaining_balance(db,line.id)
                if balance['approved_qty']>qty or balance['approved_net_amount']>qty*price:
                    raise ValueError('An order cannot be reduced below already approved quantities or value')
                if balance['approved_qty']>0 and (line.item_code!=item['sku'] or line.uom!=item['uom']):
                    raise ValueError('An allocated order line cannot be replaced by another product')
            else:
                line=POLine(po_id=po.id,line_no=number);db.add(line)
            line.item_code,line.description,line.uom=item['sku'],item['description'],item['uom']
            line.ordered_qty,line.unit_price=qty,price
            line.attributes={'material':item.get('material'),'size':item.get('size'),'tax_rate':item.get('tax_rate')}
        db.flush()
    audit(db,'local-cli','company.imported',vendors=len(data['vendors']),orders=len(data['purchase_orders']))
