"""
Database utility functions for ChitUI
"""
from app.models import db, User, Printer, PrintJob, SystemSetting
from loguru import logger
import uuid
from datetime import datetime
import json
import os
from flask import current_app


def sync_printers_to_db(runtime_printers):
    """
    Sync runtime printers dictionary to database.
    
    Args:
        runtime_printers (dict): Dictionary of printers discovered at runtime
    """
    # Import here to avoid circular imports
    from app import printers
    
    for printer_id, printer_data in runtime_printers.items():
        # Check if printer exists in database
        db_printer = Printer.query.get(printer_id)
        
        if not db_printer:
            # Create new printer record
            db_printer = Printer(
                id=printer_id,
                name=printer_data.get('name', f"Printer {printer_id[:8]}"),
                ip_address=printer_data.get('ip', '0.0.0.0'),
                model=printer_data.get('model', 'unknown'),
                brand=printer_data.get('brand', 'unknown'),
                connection_id=printer_data.get('connection', ''),
                firmware=printer_data.get('firmware', ''),
                protocol=printer_data.get('protocol', ''),
                last_seen=datetime.utcnow(),
                user_id=current_app.config.get('CHITUI_CONFIG', {}).get('default_user_id', None)
            )
            db.session.add(db_printer)
            logger.info(f"Added new printer to database: {printer_data.get('name')}")
        else:
            # Update existing printer
            db_printer.name = printer_data.get('name', db_printer.name)
            db_printer.ip_address = printer_data.get('ip', db_printer.ip_address)
            db_printer.model = printer_data.get('model', db_printer.model)
            db_printer.brand = printer_data.get('brand', db_printer.brand)
            db_printer.connection_id = printer_data.get('connection', db_printer.connection_id)
            db_printer.firmware = printer_data.get('firmware', db_printer.firmware)
            db_printer.protocol = printer_data.get('protocol', db_printer.protocol)
            db_printer.last_seen = datetime.utcnow()
            
            # Update settings if needed
            settings = db_printer.get_settings() or {}
            
            # Add camera settings if available
            if printer_data.get('supports_camera', False):
                settings['supports_camera'] = True
                if 'camera_config' in printer_data:
                    settings['camera_config'] = printer_data['camera_config']
            
            # Save settings
            db_printer.set_settings(settings)
            
            logger.debug(f"Updated printer in database: {db_printer.name}")
    
    db.session.commit()


def load_printers_from_db():
    """
    Load printers from database into runtime dictionary.
    
    Returns:
        dict: Dictionary of printers loaded from database
    """
    # Import here to avoid circular imports
    from app import printers
    
    db_printers = Printer.query.all()
    loaded_printers = {}
    
    for db_printer in db_printers:
        settings = db_printer.get_settings() or {}
        
        printer_data = {
            'id': db_printer.id,
            'name': db_printer.name,
            'ip': db_printer.ip_address,
            'model': db_printer.model,
            'brand': db_printer.brand,
            'connection': db_printer.connection_id,
            'firmware': db_printer.firmware,
            'protocol': db_printer.protocol,
            'status': 'disconnected',
            'last_seen': db_printer.last_seen.timestamp() if db_printer.last_seen else None,
            'machine_status': None,
            'print_status': None,
            'print_progress': None,
            'current_file': None,
            'remain_time': None,
            'files': [],
            'supports_camera': settings.get('supports_camera', False),
            'camera_config': settings.get('camera_config', {}),
            'from_database': True
        }
        
        # Set printer icon based on brand and model
        from app.constants import PRINTER_ICONS
        icon_key = f"{printer_data['brand']}_{printer_data['model']}".replace(" ", "")
        printer_data['icon'] = PRINTER_ICONS.get(icon_key, PRINTER_ICONS['default'])
        
        loaded_printers[db_printer.id] = printer_data
        logger.debug(f"Loaded printer from database: {db_printer.name}")
    
    return loaded_printers


def create_print_job(printer_id, filename, user_id=None):
    """
    Create a new print job record.
    
    Args:
        printer_id (str): Printer ID
        filename (str): File name
        user_id (str, optional): User ID (defaults to admin)
        
    Returns:
        PrintJob: Created print job record
    """
    # Get user ID if not provided
    if not user_id:
        admin_user = User.query.filter_by(role='admin').first()
        user_id = admin_user.id if admin_user else None
    
    # Create print job
    print_job = PrintJob(
        id=str(uuid.uuid4()),
        filename=filename,
        start_time=datetime.utcnow(),
        status='started',
        printer_id=printer_id,
        user_id=user_id
    )
    
    db.session.add(print_job)
    db.session.commit()
    
    logger.info(f"Created new print job: {filename} on printer {printer_id}")
    return print_job


def update_print_job(printer_id, status, progress=None, completed_layers=None, total_layers=None):
    """
    Update an active print job record.
    
    Args:
        printer_id (str): Printer ID
        status (str): Job status (started, printing, completed, failed, cancelled)
        progress (int, optional): Job progress percentage
        completed_layers (int, optional): Number of completed layers
        total_layers (int, optional): Total number of layers
        
    Returns:
        PrintJob: Updated print job record or None if not found
    """
    # Find active print job for printer
    print_job = PrintJob.query.filter_by(printer_id=printer_id, end_time=None).order_by(PrintJob.start_time.desc()).first()
    
    if not print_job:
        logger.warning(f"No active print job found for printer {printer_id}")
        return None
    
    # Update print job
    print_job.status = status
    
    if status in ['completed', 'failed', 'cancelled']:
        print_job.end_time = datetime.utcnow()
        if print_job.start_time:
            # Calculate duration in seconds
            duration = (print_job.end_time - print_job.start_time).total_seconds()
            print_job.duration = int(duration)
    
    if total_layers is not None:
        print_job.layers = total_layers
    
    if completed_layers is not None:
        print_job.completed_layers = completed_layers
    
    db.session.commit()
    
    logger.debug(f"Updated print job {print_job.id}: status={status}, progress={progress}")
    return print_job


def get_setting(key, default=None):
    """
    Get a system setting value.
    
    Args:
        key (str): Setting key
        default: Default value if setting not found
        
    Returns:
        The setting value or default
    """
    setting = SystemSetting.query.get(key)
    
    if setting:
        return setting.get_value()
    else:
        return default


def set_setting(key, value, type_name='string'):
    """
    Set a system setting value.
    
    Args:
        key (str): Setting key
        value: Setting value
        type_name (str): Value type (string, int, float, bool, json)
    """
    setting = SystemSetting.query.get(key)
    
    if not setting:
        setting = SystemSetting(key=key, type=type_name)
        db.session.add(setting)
    
    setting.set_value(value)
    db.session.commit()


def backup_database(backup_dir='backups'):
    """
    Create a backup of the database.
    
    Args:
        backup_dir (str): Directory to store backups
        
    Returns:
        str: Path to backup file or None if failed
    """
    try:
        # Create backup directory if it doesn't exist
        os.makedirs(backup_dir, exist_ok=True)
        
        # Get database URI
        db_uri = current_app.config['SQLALCHEMY_DATABASE_URI']
        
        # SQLite backup is simple file copy
        if db_uri.startswith('sqlite:///'):
            import shutil
            from sqlalchemy.engine.url import make_url
            
            url = make_url(db_uri)
            db_path = url.database
            
            # Remove sqlite:/// prefix for filesystem path
            if db_path.startswith('/'):
                db_path = db_path[1:]
            
            # Create backup filename with timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_file = os.path.join(backup_dir, f'chitui_backup_{timestamp}.db')
            
            # Copy database file
            shutil.copy2(db_path, backup_file)
            
            # Update last backup setting
            set_setting('last_backup', datetime.utcnow().isoformat())
            
            logger.info(f"Database backup created: {backup_file}")
            return backup_file
            
        else:
            # For other databases, we'd need to use database-specific tools
            # This is a simplified version that only works for SQLite
            logger.warning(f"Backup not implemented for database type: {db_uri}")
            return None
            
    except Exception as e:
        logger.error(f"Database backup failed: {e}")
        return None