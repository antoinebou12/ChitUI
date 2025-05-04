"""
Database models for ChitUI
"""
from datetime import datetime
from enum import Enum, auto
import uuid
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin

# Create SQLAlchemy instance
db = SQLAlchemy()

class JobStatus(str, Enum):
    """Print job status enum."""
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

class User(db.Model, UserMixin):
    """User model for authentication."""
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), default='user')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, nullable=True)

    def is_admin(self):
        """Check if user has admin role."""
        return self.role == 'admin'
        
    @property
    def password(self):
        """Password getter (raises error)."""
        raise AttributeError('Password is not a readable attribute')
    
    @password.setter
    def password(self, password):
        """Hash and store password."""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Check password against stored hash."""
        return check_password_hash(self.password_hash, password)
    
    def to_dict(self):
        """Convert user to dictionary."""
        return {
            'id': self.id,
            'username': self.username,
            'role': self.role,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None
        }

class Printer(db.Model):
    """Printer model for database storage."""
    id = db.Column(db.String(36), primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    ip = db.Column(db.String(15), nullable=False)
    model = db.Column(db.String(64))
    brand = db.Column(db.String(64))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_seen = db.Column(db.DateTime, nullable=True)
    
    def to_dict(self):
        """Convert printer to dictionary."""
        return {
            'id': self.id,
            'name': self.name,
            'ip': self.ip,
            'model': self.model,
            'brand': self.brand,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_seen': self.last_seen.isoformat() if self.last_seen else None
        }

class PrintJob(db.Model):
    """Print job model for database storage."""
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    printer_id = db.Column(db.String(36), db.ForeignKey('printer.id'), nullable=False)
    user_id = db.Column(db.String(36), db.ForeignKey('user.id'), nullable=True)
    file_name = db.Column(db.String(256), nullable=False)
    status = db.Column(db.String(20), default=JobStatus.QUEUED)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    scheduled = db.Column(db.DateTime, nullable=True)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    printer = db.relationship('Printer', backref=db.backref('jobs', lazy=True))
    user = db.relationship('User', backref=db.backref('jobs', lazy=True))
    
    def to_dict(self):
        """Convert print job to dictionary."""
        return {
            'id': self.id,
            'printer_id': self.printer_id,
            'user_id': self.user_id,
            'file_name': self.file_name,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'scheduled': self.scheduled.isoformat() if self.scheduled else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None
        }

class SystemSetting(db.Model):
    """System settings model for database storage."""
    key = db.Column(db.String(64), primary_key=True)
    value_string = db.Column(db.String(512), nullable=True)
    value_int = db.Column(db.Integer, nullable=True)
    value_float = db.Column(db.Float, nullable=True)
    value_bool = db.Column(db.Boolean, nullable=True)
    type = db.Column(db.String(16), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def get_value(self):
        """Get typed value based on type field."""
        if self.type == 'string':
            return self.value_string
        elif self.type == 'int':
            return self.value_int
        elif self.type == 'float':
            return self.value_float
        elif self.type == 'bool':
            return self.value_bool
        return None
    
    def set_value(self, value):
        """Set value in the appropriate field based on type."""
        if value is None:
            return
            
        if self.type == 'string':
            self.value_string = str(value)
        elif self.type == 'int':
            self.value_int = int(value)
        elif self.type == 'float':
            self.value_float = float(value)
        elif self.type == 'bool':
            self.value_bool = bool(value)
            
    def to_dict(self):
        """Convert setting to dictionary."""
        return {
            'key': self.key,
            'value': self.get_value(),
            'type': self.type,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }