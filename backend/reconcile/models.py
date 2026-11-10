"""Initial procurement/history schema; later pipeline tables are additive."""
from datetime import datetime, timezone, date
from decimal import Decimal
import uuid
from sqlalchemy import String, DateTime, Date, Numeric, ForeignKey, CheckConstraint, UniqueConstraint, Index, Uuid, JSON, LargeBinary, Identity, Text
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
    validation_policy: Mapped[dict]=mapped_column(JSON,default=dict,server_default='{}')
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


# Uploads remain separate from trusted ledger invoices. An incomplete extraction
# must never require invented vendor/PO/amount values to satisfy ledger FKs.
class User(Base):
    __tablename__ = 'users'
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(250), unique=True)
    display_name: Mapped[str] = mapped_column(String(150))
    role: Mapped[str] = mapped_column(String(20))
    password_hash: Mapped[str] = mapped_column(String(500))
    active: Mapped[bool] = mapped_column(default=True)
    __table_args__ = (CheckConstraint("role IN ('clerk','approver','admin')"),)


class AuthSession(Base):
    __tablename__ = 'auth_sessions'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id'), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class LoginAttempt(Base):
    __tablename__ = 'login_attempts'
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    subject: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)


class Document(Base):
    __tablename__ = 'documents'
    sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    content: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Submission(Base):
    __tablename__ = 'submissions'
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    number: Mapped[int] = mapped_column(Identity(), unique=True)
    document_hash: Mapped[str] = mapped_column(ForeignKey('documents.sha256'), index=True)
    filename: Mapped[str] = mapped_column(String(250))
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    review_state: Mapped[str] = mapped_column(String(20), default='open')
    version: Mapped[int] = mapped_column(default=0)
    ledger_invoice_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('invoices.id'), nullable=True)
    __table_args__ = (CheckConstraint("review_state IN ('open','approved','rejected')"),)


class Run(Base):
    __tablename__ = 'runs'
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    submission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('submissions.id'), index=True)
    run_no: Mapped[int]
    kind: Mapped[str] = mapped_column(String(20))
    state: Mapped[str] = mapped_column(String(30), default='queued', index=True)
    inputs: Mapped[dict] = mapped_column(JSON, default=dict)
    extraction: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    owner: Mapped[str | None] = mapped_column(String(100), nullable=True)
    attempt: Mapped[int] = mapped_column(default=0)
    fence: Mapped[int] = mapped_column(default=0)
    event_seq: Mapped[int] = mapped_column(default=0)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    __table_args__ = (UniqueConstraint('submission_id', 'run_no'),
        CheckConstraint("state IN ('queued','running','completed','processing_failed')"),
        Index('uq_active_run', 'submission_id', unique=True,
              postgresql_where=__import__('sqlalchemy').text("state IN ('queued','running')")))


class RunEvent(Base):
    __tablename__ = 'run_events'
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('runs.id'), index=True)
    seq: Mapped[int]
    type: Mapped[str] = mapped_column(String(40))
    stage: Mapped[str | None] = mapped_column(String(30), nullable=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (UniqueConstraint('run_id', 'seq'),)


class Decision(Base):
    __tablename__ = 'decisions'
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    submission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('submissions.id'), index=True)
    run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('runs.id'), nullable=True)
    version: Mapped[int]
    origin: Mapped[str] = mapped_column(String(30), default='run')
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (UniqueConstraint('submission_id', 'version'),)


class Correction(Base):
    __tablename__ = 'corrections'
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    submission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('submissions.id'), index=True)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('runs.id'))
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id'))
    field_path: Mapped[str] = mapped_column(String(150))
    old_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Audit(Base):
    __tablename__ = 'audit_entries'
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    submission_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('submissions.id'), nullable=True, index=True)
    actor: Mapped[str] = mapped_column(String(250))
    action: Mapped[str] = mapped_column(String(60))
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Idempotency(Base):
    __tablename__ = 'idempotency_records'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[int]
    body: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class WorkerHeartbeat(Base):
    __tablename__ = 'worker_heartbeats'
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    touched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
