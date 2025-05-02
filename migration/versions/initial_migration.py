"""
Initial database migration for ChitUI
"""

from alembic import op
import sqlalchemy as sa
from datetime import datetime

# revision identifiers
revision = '54a6ec76ddc1'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Create users table
    op.create_table(
        'users',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('username', sa.String(80), unique=True, nullable=False),
        sa.Column('password_hash', sa.String(256), nullable=False),
        sa.Column('role', sa.String(20), default='user'),
        sa.Column('created_at', sa.DateTime, default=datetime.utcnow),
        sa.Column('last_login', sa.DateTime)
    )
    
    # Create printers table
    op.create_table(
        'printers',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('name', sa.String(80), nullable=False),
        sa.Column('ip_address', sa.String(15), nullable=False),
        sa.Column('model', sa.String(80)),
        sa.Column('brand', sa.String(80)),
        sa.Column('connection_id', sa.String(80)),
        sa.Column('firmware', sa.String(80)),
        sa.Column('protocol', sa.String(80)),
        sa.Column('last_seen', sa.DateTime),
        sa.Column('created_at', sa.DateTime, default=datetime.utcnow),
        sa.Column('updated_at', sa.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow),
        sa.Column('settings', sa.Text),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'))
    )
    
    # Create print_jobs table
    op.create_table(
        'print_jobs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('filename', sa.String(255), nullable=False),
        sa.Column('start_time', sa.DateTime, default=datetime.utcnow),
        sa.Column('end_time', sa.DateTime),
        sa.Column('duration', sa.Integer),
        sa.Column('status', sa.String(20), default='started'),
        sa.Column('layers', sa.Integer),
        sa.Column('completed_layers', sa.Integer, default=0),
        sa.Column('settings', sa.Text),
        sa.Column('error_message', sa.Text),
        sa.Column('printer_id', sa.String(36), sa.ForeignKey('printers.id'), nullable=False),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False)
    )
    
    # Create system_settings table
    op.create_table(
        'system_settings',
        sa.Column('key', sa.String(80), primary_key=True),
        sa.Column('value', sa.Text),
        sa.Column('type', sa.String(20), default='string'),
        sa.Column('created_at', sa.DateTime, default=datetime.utcnow),
        sa.Column('updated_at', sa.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    )
    
    # Create indexes
    op.create_index('idx_printers_user_id', 'printers', ['user_id'])
    op.create_index('idx_print_jobs_printer_id', 'print_jobs', ['printer_id'])
    op.create_index('idx_print_jobs_user_id', 'print_jobs', ['user_id'])
    op.create_index('idx_print_jobs_status', 'print_jobs', ['status'])


def downgrade():
    # Drop tables in reverse order
    op.drop_table('print_jobs')
    op.drop_table('printers')
    op.drop_table('system_settings')
    op.drop_table('users')