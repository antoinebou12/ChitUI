"""
ChitUI application initialization
"""
from flask import Flask
from flask_socketio import SocketIO
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_swagger_ui import get_swaggerui_blueprint
from loguru import logger
import os
import uuid
from werkzeug.security import generate_password_hash
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler

# Initialize extensions
socketio = SocketIO()
login_manager = LoginManager()
migrate = Migrate()

# Create scheduler
sched = BackgroundScheduler()

# Global state for runtime data
printers = {}
websockets = {}
upload_progress = {}

# Import database models
from app.models import db, User, PrintJob, SystemSetting


def create_app(config=None):
    """Create and configure the Flask application."""
    app = Flask(__name__, 
                static_folder='../static',
                template_folder='../templates')
    
    # Configure app
    app.config['SECRET_KEY'] = config.get('secret_key', os.urandom(24).hex())
    app.config['UPLOAD_FOLDER'] = config.get('upload_folder', 'uploads')
    app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024  # 1GB limit
    app.config['DEBUG'] = config.get('debug', False)
    
    # Configure database
    app.config['SQLALCHEMY_DATABASE_URI'] = config.get('database_uri', 'sqlite:///chitui.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Save config for other modules to access
    app.config['CHITUI_CONFIG'] = config
    
    # Initialize database
    db.init_app(app)
    migrate.init_app(app, db)
    
    # Setup login manager
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'
    
    # Register blueprints
    from app.routes import routes_bp
    from app.auth import auth_bp
    from app.api import api_bp
    
    app.register_blueprint(routes_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(api_bp, url_prefix='/api')
    
    # Setup Swagger UI
    swagger_blueprint = get_swaggerui_blueprint(
        '/swagger',
        '/api/swagger.json',
        config={
            'app_name': "ChitUI API"
        }
    )
    app.register_blueprint(swagger_blueprint, url_prefix='/swagger')
    
    # Initialize SocketIO
    socketio.init_app(app, 
                      async_mode='gevent',
                      cors_allowed_origins="*")
    
    # Register socket event handlers
    from app.socket_handlers import register_handlers
    register_handlers(socketio)
    
    # Create database tables and initial admin user
    with app.app_context():
        db.create_all()
        create_admin_user(config)
        load_system_settings(config)
    
    # Start the scheduler
    if not sched.running:
        sched.start()
    
    # Load user model
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(user_id)
    
    logger.info("Application initialized")
    return app, socketio


def create_admin_user(config):
    """Create admin user if it doesn't exist."""
    if not config.get('admin_user') or not config.get('admin_password'):
        return
    
    admin_username = config.get('admin_user')
    admin_password = config.get('admin_password')
    
    # Check if admin user exists
    admin_user = User.query.filter_by(username=admin_username).first()
    
    if not admin_user:
        # Create admin user
        admin_user = User(
            id=str(uuid.uuid4()),
            username=admin_username,
            password=admin_password,
            role='admin'
        )
        db.session.add(admin_user)
        db.session.commit()
        logger.info(f"Admin user created: {admin_username}")
    else:
        logger.info(f"Admin user already exists: {admin_username}")


def load_system_settings(config):
    """Load system settings from database or create defaults."""
    # Default settings
    default_settings = {
        'discovery_timeout': {'value': config.get('discovery_timeout', 1), 'type': 'int'},
        'host': {'value': config.get('host', '0.0.0.0'), 'type': 'string'},
        'port': {'value': config.get('port', 54780), 'type': 'int'},
        'debug': {'value': config.get('debug', False), 'type': 'bool'},
        'log_level': {'value': config.get('log_level', 'INFO'), 'type': 'string'},
        'uploads_enabled': {'value': True, 'type': 'bool'},
        'auto_discovery': {'value': True, 'type': 'bool'},
        'last_backup': {'value': None, 'type': 'string'},
        'version': {'value': '1.0.0', 'type': 'string'},
        'startup_time': {'value': datetime.utcnow().isoformat(), 'type': 'string'}
    }
    
    # Create or update settings
    for key, setting in default_settings.items():
        db_setting = SystemSetting.query.get(key)
        
        if not db_setting:
            # Create new setting
            db_setting = SystemSetting(
                key=key,
                type=setting['type']
            )
            db_setting.set_value(setting['value'])
            db.session.add(db_setting)
        
        # Don't override existing values except for version and startup_time
        if key in ['version', 'startup_time']:
            db_setting.set_value(setting['value'])
    
    db.session.commit()
    logger.info("System settings loaded")


# Import needed for the job runner
from app.printer_manager import start_print

def _run_queued_job(job_id):
    """Run a queued print job."""
    job = PrintJob.query.get(job_id)
    if not job:
        return

    ok = start_print(job.printer_id, job.file_name)
    if ok:
        job.status = "RUNNING"
        job.started_at = datetime.utcnow()
    else:
        job.status = "ERROR"
    db.session.commit()