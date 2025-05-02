"""
Utility functions for ChitUI
"""
import os
import yaml
from pathlib import Path
from flask import current_app
from loguru import logger


def get_config():
    """
    Get configuration from Flask app.
    
    Returns:
        dict: Configuration dictionary
    """
    try:
        return current_app.config.get('CHITUI_CONFIG', {})
    except RuntimeError:
        # Outside of application context
        return {}


def load_config_file(config_path):
    """
    Load configuration from YAML file.
    
    Args:
        config_path (str): Path to configuration file
        
    Returns:
        dict: Configuration dictionary
    """
    if not os.path.exists(config_path):
        return {}
    
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
            return config or {}
    except Exception as e:
        logger.error(f"Failed to load config from {config_path}: {e}")
        return {}


def save_config_file(config, config_path):
    """
    Save configuration to YAML file.
    
    Args:
        config (dict): Configuration dictionary
        config_path (str): Path to configuration file
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        
        with open(config_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
        return True
    except Exception as e:
        logger.error(f"Failed to save config to {config_path}: {e}")
        return False


def format_time(seconds):
    """
    Format time in seconds to human-readable format.
    
    Args:
        seconds (int): Time in seconds
        
    Returns:
        str: Formatted time string
    """
    if not seconds:
        return "0m 0s"
    
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    remaining_seconds = seconds % 60
    
    if hours > 0:
        return f"{hours}h {minutes}m {remaining_seconds}s"
    else:
        return f"{minutes}m {remaining_seconds}s"


def format_size(size_bytes):
    """
    Format file size in bytes to human-readable format.
    
    Args:
        size_bytes (int): Size in bytes
        
    Returns:
        str: Formatted size string
    """
    if not size_bytes:
        return "0 B"
    
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = 0
    while size_bytes >= 1024 and i < len(size_name) - 1:
        size_bytes /= 1024
        i += 1
    
    return f"{size_bytes:.2f} {size_name[i]}"


def is_allowed_file(filename):
    """
    Check if a file has an allowed extension.
    
    Args:
        filename (str): File name
        
    Returns:
        bool: True if file extension is allowed, False otherwise
    """
    # Get allowed extensions from app config or use defaults
    from app.constants import ALLOWED_EXTENSIONS
    
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def create_default_config():
    """
    Create default configuration file if it doesn't exist.
    
    Returns:
        dict: Default configuration
    """
    config_dir = Path('config')
    config_file = config_dir / 'config.yaml'
    
    if config_file.exists():
        return load_config_file(config_file)
    
    # Default configuration
    default_config = {
        'host': '0.0.0.0',
        'port': 54780,
        'debug': False,
        'log_level': 'INFO',
        'discovery_timeout': 1,
        'upload_folder': 'uploads',
        'log_folder': 'logs',
        'admin_user': 'admin',
        'admin_password': 'admin',
    }
    
    # Save default configuration
    config_dir.mkdir(exist_ok=True)
    save_config_file(default_config, config_file)
    
    return default_config

def load_config(config_path=None):
    """
    Load configuration from YAML file.
    
    Args:
        config_path (str, optional): Path to configuration file
        
    Returns:
        dict: Configuration dictionary
    """
    if not config_path:
        # Use default config path
        config_path = os.path.join('config', 'config.yaml')
    
    return load_config_file(config_path)