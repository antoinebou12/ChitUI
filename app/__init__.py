#!/usr/bin/env python3
"""
ChitUI application initialization
"""
import os
import time
import uuid
from datetime import datetime

from flask import Flask, current_app
from flask_socketio import SocketIO
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_swagger_ui import get_swaggerui_blueprint
from loguru import logger
from werkzeug.security import generate_password_hash
from apscheduler.schedulers.background import BackgroundScheduler

# Initialize extensions
socketio = SocketIO()
login_manager = LoginManager()
migrate = Migrate()
sched = BackgroundScheduler()

# Runtime state
printers = {}
websockets = {}
upload_progress = {}

from app.models import JobStatus, db, User, PrintJob, SystemSetting
from app.printer_manager import start_print  # needed for scheduler

def create_app(config=None):
    """Create and configure the Flask application."""
    base = os.path.abspath(os.path.dirname(__file__))
    app = Flask(
        __name__,
        static_folder=os.path.join(base, '..', 'static'),
        static_url_path='/static',
        template_folder=os.path.join(base, '..', 'templates'),
    )

    # ── Load and normalize config ────────────────────────────────────────────
    # your YAML loader / env loader should populate `config` with at least:
    #   host, port, debug, log_folder, upload_folder, secret_key, database_uri, admin_user, admin_password, etc.
    app.config['SECRET_KEY'] = config.get('secret_key', os.urandom(24).hex())
    app.config['UPLOAD_FOLDER'] = config.get('upload_folder', 'uploads')
    app.config['MAX_CONTENT_LENGTH'] = config.get('max_upload_size_bytes', 1024**3)
    app.config['DEBUG'] = config.get('debug', False)

    # ── FIXED: Ensure we write our app log into the configured log_folder ─────
    log_folder = config.get('log_folder', 'logs')
    os.makedirs(log_folder, exist_ok=True)
    app.config['LOG_FILE'] = os.path.join(log_folder, 'chitui.log')

    # ── Database ─────────────────────────────────────────────────────────────
    app.config['SQLALCHEMY_DATABASE_URI'] = config.get('database_uri', 'sqlite:///chitui.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    migrate.init_app(app, db)

    # ── Login manager ───────────────────────────────────────────────────────
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'

    # ── Blueprints ─────────────────────────────────────────────────────────
    from app.routes import routes_bp
    from app.auth import auth_bp
    from app.api import api_bp

    app.register_blueprint(routes_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(api_bp, url_prefix='/api')

    # ── Swagger UI ─────────────────────────────────────────────────────────
    swagger_bp = get_swaggerui_blueprint(
        '/swagger',
        '/api/swagger.json',
        config={'app_name': "ChitUI API"}
    )
    app.register_blueprint(swagger_bp, url_prefix='/swagger')

    # ── Socket.IO ──────────────────────────────────────────────────────────
    socketio.init_app(app, async_mode='gevent', cors_allowed_origins="*")
    from app.socket_handlers import register_handlers
    register_handlers(socketio)

    # ── On first launch, create tables, admin user, system settings, schedule jobs ─
    with app.app_context():
        db.create_all()
        _create_admin_user(config)
        _load_system_settings(config)
        _schedule_existing_jobs()
        # Store a single startup timestamp so health/u
        current_app.config.setdefault('_start_time', datetime.utcnow().timestamp())

    if not sched.running:
        sched.start()

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(user_id)
    
    app.config['_start_time'] = time.time()

    logger.info("Application initialized")
    return app, socketio


def _create_admin_user(config):
    if not config.get('admin_user') or not config.get('admin_password'):
        return
    admin = User.query.filter_by(username=config['admin_user']).first()
    if not admin:
        admin = User(
            id=str(uuid.uuid4()),
            username=config['admin_user'],
            password=generate_password_hash(config['admin_password']),
            role='admin'
        )
        db.session.add(admin)
        db.session.commit()
        logger.info(f"Admin user created: {config['admin_user']}")
    else:
        logger.info(f"Admin user exists: {config['admin_user']}")


def _load_system_settings(config):
    """Load system settings from database or create defaults."""
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
    for key, setting in default_settings.items():
        db_setting = SystemSetting.query.get(key)
        if not db_setting:
            db_setting = SystemSetting(key=key, type=setting['type'])
            db_setting.set_value(setting['value'])
            db.session.add(db_setting)
        elif key in ['version', 'startup_time']:
            db_setting.set_value(setting['value'])
    db.session.commit()
    logger.info("System settings loaded")

def _schedule_existing_jobs():
    for job in PrintJob.query.filter_by(status=JobStatus.QUEUED).all():
        sched.add_job(
            func=start_print,
            trigger='date',
            run_date=job.scheduled,
            args=[job.printer_id, job.filename],
            id=str(job.id),
        )
    logger.info("Existing print jobs scheduled")
