#!/usr/bin/env python3
"""
ChitUI - Web UI for Chitubox SDCP 3.0 resin printers

This is the main entry point for the application, handling CLI arguments
and starting the web server.
"""
import os
import sys
import typer
from pathlib import Path
from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich import print as rprint
import time

# Import our database management modules
from app.db_config import setup_db_engine, get_db_session, close_db_session
from app.db_migration import run_migrations, get_current_version
from app.db_backup import DatabaseBackup
from app.db_cli import app as db_app

from app.utils import load_config_file as load_config

# Create Typer app
app = typer.Typer(
    name="ChitUI",
    help="Web UI for Chitubox SDCP 3.0 resin printers",
    add_completion=False,
)

# Add the database management CLI as a subcommand
app.add_typer(db_app, name="db", help="Database management commands")

# Create Rich console
console = Console()

def load_config(config_path=None):
    """Load configuration from YAML file."""
    import yaml
    
    default_config = {
        "host": os.environ.get("HOST", "0.0.0.0"),
        "port": int(os.environ.get("PORT", 54780)),
        "debug": os.environ.get("DEBUG", "false").lower() == "true",
        "log_level": os.environ.get("LOG_LEVEL", "INFO"),
        "upload_folder": os.environ.get("UPLOAD_FOLDER", "uploads"),
        "log_folder": os.environ.get("LOG_FOLDER", "logs"),
        "discovery_timeout": int(os.environ.get("DISCOVERY_TIMEOUT", 1)),
        "admin_user": os.environ.get("ADMIN_USER", "admin"),
        "admin_password": os.environ.get("ADMIN_PASSWORD", "admin"),
        "secret_key": os.environ.get("SECRET_KEY", os.urandom(24).hex()),
        "database_uri": os.environ.get("DATABASE_URI", "sqlite:///chitui.db"),
        "config_folder": os.environ.get("CONFIG_FOLDER", "config"),
        "backup_folder": os.environ.get("BACKUP_FOLDER", "backups"),
        # Database connection pool settings
        "db_pool_size": int(os.environ.get("DB_POOL_SIZE", 10)),
        "db_max_overflow": int(os.environ.get("DB_MAX_OVERFLOW", 20)),
        "db_pool_timeout": int(os.environ.get("DB_POOL_TIMEOUT", 30)),
        # Backup settings
        "auto_backup_enabled": os.environ.get("AUTO_BACKUP_ENABLED", "true").lower() == "true",
        "auto_backup_interval": int(os.environ.get("AUTO_BACKUP_INTERVAL", 24)),  # hours
        "auto_backup_keep": int(os.environ.get("AUTO_BACKUP_KEEP", 7)),  # number of backups to keep
    }
    
    if config_path:
        try:
            with open(config_path, "r") as f:
                user_config = yaml.safe_load(f)
                if user_config:
                    default_config.update(user_config)
        except Exception as e:
            logger.warning(f"Failed to load config from {config_path}: {e}")
    
    return default_config


def setup_logging(config):
    """Configure logging with loguru."""
    # Remove default logger
    logger.remove()
    
    # Create log directory if it doesn't exist
    log_dir = Path(config["log_folder"])
    log_dir.mkdir(exist_ok=True)
    
    # Add stderr logger
    logger.add(
        sys.stderr,
        level=config["log_level"],
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        colorize=True,
    )
    
    # Add file logger
    logger.add(
        log_dir / "chitui.log",
        rotation="10 MB",
        retention="1 week",
        level=config["log_level"],
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    )


def print_banner(config):
    """Print a nice ASCII banner for the application."""
    banner = Text()
    banner.append("  _____ _     _ _   _   _ ___ \n", style="blue")
    banner.append(" / ____| |   (_) | | | |_|__ \\\n", style="blue")
    banner.append("| |    | |__  _| |_| | | | | |\n", style="cyan")
    banner.append("| |    | '_ \\| | __| | | | | |\n", style="cyan")
    banner.append("| |____| | | | | |_| |_| |_| |\n", style="green")
    banner.append(" \\_____|_| |_|_|\\__|\\___/\\___/\n", style="green")
    
    subtext = Text()
    subtext.append("Web UI for Chitubox SDCP 3.0 resin printers\n\n", style="yellow")
    subtext.append(f"Server running at: ", style="white")
    subtext.append(f"http://{config['host']}:{config['port']}\n", style="cyan bold")
    subtext.append(f"Debug mode: ", style="white")
    subtext.append(f"{'Enabled' if config['debug'] else 'Disabled'}\n", 
                  style="green bold" if not config['debug'] else "yellow bold")
    subtext.append(f"Database: ", style="white")
    
    # Simple detection of database type from URI
    db_uri = config.get('database_uri', '')
    if 'sqlite' in db_uri:
        db_type = "SQLite"
    elif 'mysql' in db_uri:
        db_type = "MySQL"
    elif 'postgresql' in db_uri:
        db_type = "PostgreSQL"
    else:
        db_type = "Unknown"
    
    subtext.append(f"{db_type}\n", style="cyan bold")
    
    # Get database version
    engine, _ = setup_db_engine(config)
    db_version = get_current_version(engine)
    subtext.append(f"Database version: ", style="white")
    subtext.append(f"{db_version}\n", style="cyan bold")
    
    panel = Panel(
        Text.assemble(banner, "\n", subtext),
        title="ChitUI",
        subtitle="v1.0.0",
        border_style="blue",
    )
    
    console.print(panel)


def setup_auto_backup(config):
    """Set up automatic database backup if enabled."""
    if not config.get('auto_backup_enabled', True):
        return
    
    import threading
    
    def backup_task():
        interval_hours = config.get('auto_backup_interval', 24)
        keep_count = config.get('auto_backup_keep', 7)
        
        while True:
            try:
                # Sleep for the interval
                time.sleep(interval_hours * 3600)
                
                # Create backup
                backup_manager = DatabaseBackup(config)
                backup_info = backup_manager.create_backup("Automatic backup")
                
                if backup_info:
                    logger.info(f"Automatic backup created: {backup_info['filename']}")
                    
                    # Clean up old backups
                    backups = backup_manager.list_backups()
                    if len(backups) > keep_count:
                        # Delete oldest backups
                        for backup in backups[keep_count:]:
                            backup_manager.delete_backup(backup["id"])
                            logger.info(f"Deleted old backup: {backup['filename']}")
                else:
                    logger.error("Automatic backup failed")
                    
            except Exception as e:
                logger.error(f"Error in backup task: {e}")
    
    # Start backup thread
    backup_thread = threading.Thread(target=backup_task, daemon=True)
    backup_thread.start()
    logger.info("Automatic database backup task started")


@app.command()
def run(
    config_file: str = typer.Option(
        None, "--config", "-c", help="Path to configuration file"
    ),
    host: str = typer.Option(
        None, "--host", "-h", help="Host to bind the server to"
    ),
    port: int = typer.Option(
        None, "--port", "-p", help="Port to bind the server to"
    ),
    debug: bool = typer.Option(
        None, "--debug", "-d", help="Enable debug mode"
    ),
    log_level: str = typer.Option(
        None, "--log-level", "-l", 
        help="Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)"
    ),
    database_uri: str = typer.Option(
        None, "--db", "--database", help="Database URI (e.g., sqlite:///chitui.db)"
    ),
    auto_backup: bool = typer.Option(
        None, "--auto-backup/--no-auto-backup", help="Enable/disable automatic database backup"
    ),
):
    """Run the ChitUI web server."""
    # Load configuration
    config = load_config(config_file)
    
    # Override config with CLI arguments
    if host is not None:
        config["host"] = host
    if port is not None:
        config["port"] = port
    if debug is not None:
        config["debug"] = debug
    if log_level is not None:
        config["log_level"] = log_level
    if database_uri is not None:
        config["database_uri"] = database_uri
    if auto_backup is not None:
        config["auto_backup_enabled"] = auto_backup
    
    # Setup logging
    setup_logging(config)
    
    # Create required directories
    Path(config["upload_folder"]).mkdir(exist_ok=True)
    Path(config["config_folder"]).mkdir(exist_ok=True)
    Path(config["backup_folder"]).mkdir(exist_ok=True)
    
    # Set up database engine
    engine, Session = setup_db_engine(
        config,
        pool_size=config.get("db_pool_size", 10),
        max_overflow=config.get("db_max_overflow", 20),
        timeout=config.get("db_pool_timeout", 30)
    )
    
    # Run migrations if needed
    try:
        run_migrations()
        logger.info("Database migrations completed")
    except Exception as e:
        logger.error(f"Error running migrations: {e}")
    
    # Print banner
    print_banner(config)
    
    # Set up automatic backup
    setup_auto_backup(config)
    
    # Import app here to avoid circular imports and use the config
    from app import create_app
    
    flask_app, socketio = create_app(config)
    
    # Run the app
    logger.info(f"Starting ChitUI server on {config['host']}:{config['port']}")
    socketio.run(
        flask_app,
        host=config["host"],
        port=config["port"],
        debug=config["debug"],
        use_reloader=config["debug"],
        log_output=True,
    )


if __name__ == "__main__":
    app()