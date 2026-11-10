"""Initial procurement/history schema; later pipeline tables are additive."""
from datetime import datetime, timezone, date
from decimal import Decimal
import uuid
from sqlalchemy import String, DateTime, Date, Numeric, ForeignKey, CheckConstraint, UniqueConstraint, Index, Uuid, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now():
    return datetime.now(timezone.utc)

class Base(DeclarativeBase):
    pass

class Vendor(Base):
    __tablename__='vendors'
    id: Mapped[uuid.UUID]=mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    legal_name: Mapped[str]=mapped_column(String(250))
    status: Mapped[str]=mapped_column(String(20), default='approved')
    __table_args__=(CheckConstraint("status IN ('approved','pending','blocked')"),)

class PurchaseOrder(Base):
    __tablename__='purchase_orders'
    id: Mapped[uuid.UUID]=mapped_column(Uuid,primary_key=True,default=uuid.uuid4)
    po_number: Mapped[str]=mapped_column(String(100),unique=True)
    vendor_id: Mapped[uuid.UUID]=mapped_column(ForeignKey('vendors.id'))
    status: Mapped[str]=mapped_column(String(20),default='open')
    currency: Mapped[str]=mapped_column(String(3),default='INR')
    order_date: Mapped[date]=mapped_column(Date,default=date.today)
    revision: Mapped[int]=mapped_column(default=1)
    __table_args__=(CheckConstraint("status IN ('open','closed','cancelled')"),)

class POLine(Base):
    __tablename__='po_lines'
    id: Mapped[uuid.UUID]=mapped_column(Uuid,primary_key=True,default=uuid.uuid4)
    po_id: Mapped[uuid.UUID]=mapped_column(ForeignKey('purchase_orders.id'))
    line_no: Mapped[int]
    item_code: Mapped[str]=mapped_column(String(100))
    description: Mapped[str]=mapped_column(String(1000))
    attributes: Mapped[dict]=mapped_column(JSON,default=dict)
    uom: Mapped[str]=mapped_column(String(20))
    ordered_qty: Mapped[Decimal]=mapped_column(Numeric(18,4))
    unit_price: Mapped[Decimal]=mapped_column(Numeric(18,4))
    allocations_version: Mapped[int]=mapped_column(default=0)
    __table_args__=(UniqueConstraint('po_id','line_no'),CheckConstraint('ordered_qty > 0'),CheckConstraint('unit_price >= 0'))

class Invoice(Base):
    __tablename__='invoices'
    id: Mapped[uuid.UUID]=mapped_column(Uuid,primary_key=True,default=uuid.uuid4)
    vendor_id: Mapped[uuid.UUID]=mapped_column(ForeignKey('vendors.id'))
    po_id: Mapped[uuid.UUID]=mapped_column(ForeignKey('purchase_orders.id'))
    invoice_number: Mapped[str]=mapped_column(String(100))
    invoice_number_key: Mapped[str]=mapped_column(String(100),index=True)
    document_sha256: Mapped[str]=mapped_column(String(64),index=True)
    currency: Mapped[str]=mapped_column(String(3),default='INR')
    gross_total: Mapped[Decimal]=mapped_column(Numeric(18,2))
    review_state: Mapped[str]=mapped_column(String(20),default='open')
    recommendation: Mapped[str | None]=mapped_column(String(30),nullable=True)
    decision_version: Mapped[int]=mapped_column(default=1)
    uploaded_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    __table_args__=(CheckConstraint("review_state IN ('open','approved','rejected')"),CheckConstraint("recommendation IS NULL OR recommendation IN ('ready_for_approval','hold','needs_review')"),CheckConstraint('gross_total >= 0'),Index('ix_invoice_vendor_number','vendor_id','invoice_number_key'))

class InvoiceLine(Base):
    __tablename__='invoice_lines'
    id: Mapped[uuid.UUID]=mapped_column(Uuid,primary_key=True,default=uuid.uuid4)
    invoice_id: Mapped[uuid.UUID]=mapped_column(ForeignKey('invoices.id'))
    po_line_id: Mapped[uuid.UUID]=mapped_column(ForeignKey('po_lines.id'))
    # Only already validated, evidence-backed base-unit values belong here.
    normalized_qty: Mapped[Decimal]=mapped_column(Numeric(18,4))
    normalized_unit_price: Mapped[Decimal]=mapped_column(Numeric(18,4))
    evidence: Mapped[dict]=mapped_column(JSON)
    __table_args__=(CheckConstraint('normalized_qty > 0'),CheckConstraint('normalized_unit_price >= 0'))

class Approval(Base):
    __tablename__='approvals'
    id: Mapped[uuid.UUID]=mapped_column(Uuid,primary_key=True,default=uuid.uuid4)
    invoice_id: Mapped[uuid.UUID]=mapped_column(ForeignKey('invoices.id'),unique=True)
    actor: Mapped[str]=mapped_column(String(200))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)

class Allocation(Base):
    __tablename__='allocations'
    id: Mapped[uuid.UUID]=mapped_column(Uuid,primary_key=True,default=uuid.uuid4)
    approval_id: Mapped[uuid.UUID]=mapped_column(ForeignKey('approvals.id'))
    invoice_line_id: Mapped[uuid.UUID]=mapped_column(ForeignKey('invoice_lines.id'),unique=True)
    po_line_id: Mapped[uuid.UUID]=mapped_column(ForeignKey('po_lines.id'),index=True)
    qty: Mapped[Decimal]=mapped_column(Numeric(18,4))
    net_amount: Mapped[Decimal]=mapped_column(Numeric(18,2))
    __table_args__=(CheckConstraint('qty > 0'),CheckConstraint('net_amount >= 0'))
