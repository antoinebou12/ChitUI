#!/usr/bin/env python3
"""
ChitUI - Web UI for Chitubox SDCP 3.0 resin printers

This is the main entry point for the application, handling CLI arguments
and starting the web server (with livereload in debug mode).
"""
import os
import sys
import typer
import time
from pathlib import Path
from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from livereload import Server

# Database & migration helpers
from app.database.db_config import setup_db_engine, get_db_session, close_db_session
from app.database.db_migration import run_migrations, get_current_version
from app.database.db_backup import DatabaseBackup
from app.database.db_cli import app as db_app

# CLI app
app = typer.Typer(
    name="ChitUI",
    help="Web UI for Chitubox SDCP 3.0 resin printers",
    add_completion=False,
)
app.add_typer(db_app, name="db", help="Database management commands")

console = Console()

def load_config(config_path: str | None = None) -> dict:
    """Load configuration from YAML file or environment."""
    import yaml

    cfg = {
        "host": os.environ.get("HOST", "0.0.0.0"),
        "port": int(os.environ.get("PORT", 54780)),
        "debug": os.environ.get("DEBUG", "false").lower() == "true",
        "log_level": os.environ.get("LOG_LEVEL", "INFO"),
        "upload_folder": os.environ.get("UPLOAD_FOLDER", "uploads"),
        "log_folder": os.environ.get("LOG_FOLDER", "logs"),
        "config_folder": os.environ.get("CONFIG_FOLDER", "config"),
        "backup_folder": os.environ.get("BACKUP_FOLDER", "backups"),
        "discovery_timeout": int(os.environ.get("DISCOVERY_TIMEOUT", 1)),
        "admin_user": os.environ.get("ADMIN_USER", "admin"),
        "admin_password": os.environ.get("ADMIN_PASSWORD", "admin"),
        "secret_key": os.environ.get("SECRET_KEY", os.urandom(24).hex()),
        "database_uri": os.environ.get("DATABASE_URI", "sqlite:///chitui.db"),
        "db_pool_size": int(os.environ.get("DB_POOL_SIZE", 10)),
        "db_max_overflow": int(os.environ.get("DB_MAX_OVERFLOW", 20)),
        "db_pool_timeout": int(os.environ.get("DB_POOL_TIMEOUT", 30)),
        "auto_backup_enabled": os.environ.get("AUTO_BACKUP_ENABLED", "true").lower() == "true",
        "auto_backup_interval": int(os.environ.get("AUTO_BACKUP_INTERVAL", 24)),
        "auto_backup_keep": int(os.environ.get("AUTO_BACKUP_KEEP", 7)),
    }

    if config_path:
        try:
            with open(config_path, "r") as f:
                user_cfg = yaml.safe_load(f)
            if isinstance(user_cfg, dict):
                cfg.update(user_cfg)
        except Exception as e:
            logger.warning(f"Failed to load config from {config_path}: {e}")

    return cfg

def setup_logging(config: dict):
    """Initialize loguru logging to stdout and file."""
    logger.remove()
    Path(config["log_folder"]).mkdir(parents=True, exist_ok=True)

    logger.add(
        sys.stderr,
        level=config["log_level"],
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
               "<level>{level: <8}</level> | "
               "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
               "<level>{message}</level>",
        colorize=True,
    )
    logger.add(
        Path(config["log_folder"]) / "chitui.log",
        rotation="10 MB",
        retention="1 week",
        level=config["log_level"],
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    )

def print_banner(config: dict):
    """Render Rich ASCII banner with startup info."""
    banner = Text()
    banner.append("  _____ _     _ _   _   _ ___ \n", style="blue")
    banner.append(" / ____| |   (_) | | | |_|__ \\\n", style="blue")
    banner.append("| |    | |__  _| |_| | | | | |\n", style="cyan")
    banner.append("| |    | '_ \\| | __| | | | | |\n", style="cyan")
    banner.append("| |____| | | | | |_| |_| |_| |\n", style="green")
    banner.append(" \\_____|_| |_|_|\\__|\\___/\\___/\n", style="green")

    sub = Text()
    sub.append("Web UI for Chitubox SDCP 3.0 resin printers\n\n", style="yellow")
    sub.append("Server running at: ", style="white")
    sub.append(f"http://{config['host']}:{config['port']}\n", style="cyan bold")
    sub.append("Debug mode: ", style="white")
    sub.append("Enabled\n" if config["debug"] else "Disabled\n",
               style="yellow bold" if config["debug"] else "green bold")

    # DB info
    db_uri = config["database_uri"]
    db_type = ("SQLite" if "sqlite" in db_uri else
               "MySQL" if "mysql" in db_uri else
               "PostgreSQL" if "postgresql" in db_uri else
               "Unknown")
    sub.append("Database: ", style="white")
    sub.append(f"{db_type}\n", style="cyan bold")

    engine, _ = setup_db_engine(config)
    version = get_current_version(engine)
    sub.append("DB version: ", style="white")
    sub.append(f"{version}\n", style="cyan bold")

    console.print(Panel(Text.assemble(banner, "\n", sub),
                        title="ChitUI", subtitle="v1.0.0", border_style="blue"))

def setup_auto_backup(config: dict):
    """Spawn background thread for periodic backups."""
    if not config["auto_backup_enabled"]:
        return

    from threading import Thread
    def worker():
        interval = config["auto_backup_interval"] * 3600
        keep = config["auto_backup_keep"]
        while True:
            time.sleep(interval)
            try:
                mgr = DatabaseBackup(config)
                info = mgr.create_backup("Automatic backup")
                if info:
                    logger.info(f"Backup done: {info['filename']}")
                    all_bk = mgr.list_backups()
                    for old in all_bk[keep:]:
                        mgr.delete_backup(old["id"])
                        logger.info(f"Removed old backup {old['filename']}")
                else:
                    logger.error("Backup failed")
            except Exception as e:
                logger.error(f"Backup error: {e}")

    Thread(target=worker, daemon=True).start()
    logger.info("Auto-backup thread started")

@app.command()
def run(
    config_file: str = typer.Option(None, "--config", "-c"),
    host: str        = typer.Option(None, "--host", "-h"),
    port: int        = typer.Option(None, "--port", "-p"),
    debug: bool      = typer.Option(None, "--debug", "-d"),
    log_level: str   = typer.Option(None, "--log-level", "-l"),
    database_uri: str= typer.Option(None, "--db", "--database"),
    auto_backup: bool= typer.Option(None, "--auto-backup/--no-auto-backup")
):
    """Launch the ChitUI server (with optional Livereload in debug)."""
    cfg = load_config(config_file)
    # CLI overrides
    for k,v in [("host",host),("port",port),("debug",debug),
                ("log_level",log_level),("database_uri",database_uri),
                ("auto_backup_enabled",auto_backup)]:
        if v is not None:
            cfg[k] = v

    setup_logging(cfg)
    Path(cfg["upload_folder"]).mkdir(exist_ok=True)
    Path(cfg["config_folder"]).mkdir(exist_ok=True)
    Path(cfg["backup_folder"]).mkdir(exist_ok=True)

    engine, Session = setup_db_engine(cfg,
        pool_size=cfg["db_pool_size"],
        max_overflow=cfg["db_max_overflow"],
        timeout=cfg["db_pool_timeout"],
    )

    try:
        run_migrations()
        logger.info("Migrations applied")
    except Exception as e:
        logger.error(f"Migration error: {e}")

    print_banner(cfg)
    setup_auto_backup(cfg)

    from app import create_app
    flask_app, socketio = create_app(cfg)

    # Run
    if cfg["debug"]:
        server = Server(flask_app.wsgi_app)
        server.watch("app/**/*.py")
        server.watch("app/templates/**/*.html")
        server.watch("app/static/**/*.*")
        server.serve(
            host=cfg["host"],
            port=cfg["port"],
            liveport=35729,
            debug=True,
            open_url_delay=1
        )
    else:
        socketio.run(
            flask_app,
            host=cfg["host"],
            port=cfg["port"],
            debug=False,
            use_reloader=False,
            log_output=True
        )

if __name__ == "__main__":
    app()
