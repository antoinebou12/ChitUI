"""
Database models for ChitUI
"""
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import json

db = SQLAlchemy()

class User(db.Model, UserMixin):
    """User model for authentication and user management."""
    
    __tablename__ = 'users'
    
    id = db.Column(db.String(36), primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), default='user')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    
    # Relationships
    printers = db.relationship('Printer', back_populates='user', cascade='all, delete-orphan')
    print_jobs = db.relationship('PrintJob', back_populates='user', cascade='all, delete-orphan')
    
    def __init__(self, **kwargs):
        """Initialize a new user."""
        self.id = kwargs.get('id')
        self.username = kwargs.get('username')
        self.role = kwargs.get('role', 'user')
        
        if 'password' in kwargs:
            self.set_password(kwargs['password'])
    
    def set_password(self, password):
        """Set password hash."""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Check if the provided password matches the stored hash."""
        return check_password_hash(self.password_hash, password)
    
    def is_admin(self):
        """Check if the user has admin role."""
        return self.role == 'admin'
    
    def to_dict(self):
        """Convert user to dictionary for serialization."""
        return {
            'id': self.id,
            'username': self.username,
            'role': self.role,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None
        }
    
    def __repr__(self):
        return f'<User {self.username}>'


class Printer(db.Model):
    """Printer model for storing printer configurations."""
    
    __tablename__ = 'printers'
    
    id = db.Column(db.String(36), primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    ip_address = db.Column(db.String(15), nullable=False)
    model = db.Column(db.String(80))
    brand = db.Column(db.String(80))
    connection_id = db.Column(db.String(80))
    firmware = db.Column(db.String(80))
    protocol = db.Column(db.String(80))
    last_seen = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Settings stored as JSON
    settings = db.Column(db.Text)
    
    # Relationships
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'))
    user = db.relationship('User', back_populates='printers')
    print_jobs = db.relationship('PrintJob', back_populates='printer', cascade='all, delete-orphan')
    
    def get_settings(self):
        """Get printer settings as dictionary."""
        if not self.settings:
            return {}
        try:
            return json.loads(self.settings)
        except Exception:
            return {}
    
    def set_settings(self, settings_dict):
        """Set printer settings from dictionary."""
        self.settings = json.dumps(settings_dict)
    
    def to_dict(self):
        """Convert printer to dictionary for serialization."""
        return {
            'id': self.id,
            'name': self.name,
            'ip_address': self.ip_address,
            'model': self.model,
            'brand': self.brand,
            'firmware': self.firmware,
            'protocol': self.protocol,
            'last_seen': self.last_seen.isoformat() if self.last_seen else None,
            'settings': self.get_settings(),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
    
    def __repr__(self):
        return f'<Printer {self.name}>'


class PrintJob(db.Model):
    """Print job model for storing print history."""
    
    __tablename__ = 'print_jobs'
    
    id = db.Column(db.String(36), primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    start_time = db.Column(db.DateTime, default=datetime.utcnow)
    end_time = db.Column(db.DateTime)
    duration = db.Column(db.Integer)  # Duration in seconds
    status = db.Column(db.String(20), default='started')  # started, completed, failed, cancelled
    layers = db.Column(db.Integer)
    completed_layers = db.Column(db.Integer, default=0)
    
    # Additional print settings stored as JSON
    settings = db.Column(db.Text)
    
    # Error information if job failed
    error_message = db.Column(db.Text)
    
    # Relationships
    printer_id = db.Column(db.String(36), db.ForeignKey('printers.id'), nullable=False)
    printer = db.relationship('Printer', back_populates='print_jobs')
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    user = db.relationship('User', back_populates='print_jobs')
    
    def get_settings(self):
        """Get print job settings as dictionary."""
        if not self.settings:
            return {}
        try:
            return json.loads(self.settings)
        except Exception:
            return {}
    
    def set_settings(self, settings_dict):
        """Set print job settings from dictionary."""
        self.settings = json.dumps(settings_dict)
    
    def calculate_progress(self):
        """Calculate print job progress as percentage."""
        if not self.layers or self.layers == 0:
            return 0
        return int((self.completed_layers / self.layers) * 100)
    
    def to_dict(self):
        """Convert print job to dictionary for serialization."""
        return {
            'id': self.id,
            'filename': self.filename,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'duration': self.duration,
            'status': self.status,
            'layers': self.layers,
            'completed_layers': self.completed_layers,
            'progress': self.calculate_progress(),
            'printer_id': self.printer_id,
            'printer_name': self.printer.name if self.printer else None,
            'settings': self.get_settings(),
            'error_message': self.error_message
        }
    
    def __repr__(self):
        return f'<PrintJob {self.filename}>'


class SystemSetting(db.Model):
    """System settings model for storing application configuration."""
    
    __tablename__ = 'system_settings'
    
    key = db.Column(db.String(80), primary_key=True)
    value = db.Column(db.Text)
    type = db.Column(db.String(20), default='string')  # string, int, float, bool, json
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def get_value(self):
        """Get setting value with proper type conversion."""
        if not self.value:
            return None
        
        if self.type == 'int':
            return int(self.value)
        elif self.type == 'float':
            return float(self.value)
        elif self.type == 'bool':
            return self.value.lower() in ('true', 't', 'yes', 'y', '1')
        elif self.type == 'json':
            try:
                return json.loads(self.value)
            except Exception:
                return {}
        else:
            return self.value
    
    def set_value(self, value):
        """Set setting value with proper type conversion."""
        if value is None:
            self.value = None
            return
        
        if self.type == 'int':
            self.value = str(int(value))
        elif self.type == 'float':
            self.value = str(float(value))
        elif self.type == 'bool':
            self.value = 'true' if value else 'false'
        elif self.type == 'json':
            self.value = json.dumps(value)
        else:
            self.value = str(value)
    
    def __repr__(self):
        return f'<SystemSetting {self.key}>'