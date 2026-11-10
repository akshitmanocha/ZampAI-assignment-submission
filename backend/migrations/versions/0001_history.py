"""Initial history subset; future pipeline/auth tables are additive."""
from alembic import op
import sqlalchemy as sa
revision='0001_history'
down_revision=None
branch_labels=None
depends_on=None


def upgrade():
    # Explicit immutable migration schema; never import evolving runtime models.
    op.create_table('vendors',sa.Column('id',sa.Uuid(),primary_key=True),sa.Column('legal_name',sa.String(250),nullable=False),sa.Column('status',sa.String(20),nullable=False),sa.CheckConstraint("status IN ('approved','pending','blocked')"))
    op.create_table('purchase_orders',sa.Column('id',sa.Uuid(),primary_key=True),sa.Column('po_number',sa.String(100),nullable=False,unique=True),sa.Column('vendor_id',sa.Uuid(),sa.ForeignKey('vendors.id'),nullable=False),sa.Column('status',sa.String(20),nullable=False),sa.Column('currency',sa.String(3),nullable=False),sa.Column('order_date',sa.Date(),nullable=False),sa.Column('revision',sa.Integer(),nullable=False),sa.CheckConstraint("status IN ('open','closed','cancelled')"))
    op.create_table('po_lines',sa.Column('id',sa.Uuid(),primary_key=True),sa.Column('po_id',sa.Uuid(),sa.ForeignKey('purchase_orders.id'),nullable=False),sa.Column('line_no',sa.Integer(),nullable=False),sa.Column('item_code',sa.String(100),nullable=False),sa.Column('description',sa.String(1000),nullable=False),sa.Column('attributes',sa.JSON(),nullable=False),sa.Column('uom',sa.String(20),nullable=False),sa.Column('ordered_qty',sa.Numeric(18,4),nullable=False),sa.Column('unit_price',sa.Numeric(18,4),nullable=False),sa.Column('allocations_version',sa.Integer(),nullable=False),sa.UniqueConstraint('po_id','line_no'),sa.CheckConstraint('ordered_qty > 0'),sa.CheckConstraint('unit_price >= 0'))
    op.create_table('invoices',sa.Column('id',sa.Uuid(),primary_key=True),sa.Column('vendor_id',sa.Uuid(),sa.ForeignKey('vendors.id'),nullable=False),sa.Column('po_id',sa.Uuid(),sa.ForeignKey('purchase_orders.id'),nullable=False),sa.Column('invoice_number',sa.String(100),nullable=False),sa.Column('invoice_number_key',sa.String(100),nullable=False),sa.Column('document_sha256',sa.String(64),nullable=False),sa.Column('currency',sa.String(3),nullable=False),sa.Column('gross_total',sa.Numeric(18,2),nullable=False),sa.Column('review_state',sa.String(20),nullable=False),sa.Column('recommendation',sa.String(30)),sa.Column('decision_version',sa.Integer(),nullable=False),sa.Column('uploaded_at',sa.DateTime(timezone=True),nullable=False),sa.CheckConstraint("review_state IN ('open','approved','rejected')"),sa.CheckConstraint("recommendation IS NULL OR recommendation IN ('ready_for_approval','hold','needs_review')"),sa.CheckConstraint('gross_total >= 0'))
    op.create_index('ix_invoices_invoice_number_key','invoices',['invoice_number_key']);op.create_index('ix_invoices_document_sha256','invoices',['document_sha256']);op.create_index('ix_invoice_vendor_number','invoices',['vendor_id','invoice_number_key'])
    op.create_table('invoice_lines',sa.Column('id',sa.Uuid(),primary_key=True),sa.Column('invoice_id',sa.Uuid(),sa.ForeignKey('invoices.id'),nullable=False),sa.Column('po_line_id',sa.Uuid(),sa.ForeignKey('po_lines.id'),nullable=False),sa.Column('normalized_qty',sa.Numeric(18,4),nullable=False),sa.Column('normalized_unit_price',sa.Numeric(18,4),nullable=False),sa.Column('evidence',sa.JSON(),nullable=False),sa.CheckConstraint('normalized_qty > 0'),sa.CheckConstraint('normalized_unit_price >= 0'))
    op.create_table('approvals',sa.Column('id',sa.Uuid(),primary_key=True),sa.Column('invoice_id',sa.Uuid(),sa.ForeignKey('invoices.id'),nullable=False,unique=True),sa.Column('actor',sa.String(200),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_table('allocations',sa.Column('id',sa.Uuid(),primary_key=True),sa.Column('approval_id',sa.Uuid(),sa.ForeignKey('approvals.id'),nullable=False),sa.Column('invoice_line_id',sa.Uuid(),sa.ForeignKey('invoice_lines.id'),nullable=False,unique=True),sa.Column('po_line_id',sa.Uuid(),sa.ForeignKey('po_lines.id'),nullable=False),sa.Column('qty',sa.Numeric(18,4),nullable=False),sa.Column('net_amount',sa.Numeric(18,2),nullable=False),sa.CheckConstraint('qty > 0'),sa.CheckConstraint('net_amount >= 0'))
    op.create_index('ix_allocations_po_line_id','allocations',['po_line_id'])


def downgrade():
    raise RuntimeError('Destructive downgrade is not supported; roll back application only')
