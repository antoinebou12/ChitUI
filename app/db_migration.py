# db_migration.py
import os
import sys
import uuid
import shutil
from datetime import datetime
from pathlib import Path
from loguru import logger
from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import inspect

def get_alembic_config(config_path='migrations/alembic.ini'):
    """Get Alembic configuration."""
    alembic_cfg = AlembicConfig(config_path)
    # Set script location
    alembic_cfg.set_main_option("script_location", "migrations")
    return alembic_cfg

def create_migration(message, config_path='migrations/alembic.ini'):
    """Create a new migration."""
    try:
        alembic_cfg = get_alembic_config(config_path)
        command.revision(alembic_cfg, message=message, autogenerate=True)
        logger.info(f"Created migration: {message}")
        return True
    except Exception as e:
        logger.error(f"Failed to create migration: {e}")
        return False

def run_migrations(config_path='migrations/alembic.ini'):
    """Run all pending migrations."""
    try:
        alembic_cfg = get_alembic_config(config_path)
        command.upgrade(alembic_cfg, "head")
        logger.info("Migrations completed successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to run migrations: {e}")
        return False

def downgrade_migrations(revision, config_path='migrations/alembic.ini'):
    """Downgrade migrations to a specific revision."""
    try:
        alembic_cfg = get_alembic_config(config_path)
        command.downgrade(alembic_cfg, revision)
        logger.info(f"Downgraded to revision: {revision}")
        return True
    except Exception as e:
        logger.error(f"Failed to downgrade migrations: {e}")
        return False

def list_migrations(config_path='migrations/alembic.ini'):
    """List all migrations and their status."""
    try:
        alembic_cfg = get_alembic_config(config_path)
        command.history(alembic_cfg, verbose=True)
        return True
    except Exception as e:
        logger.error(f"Failed to list migrations: {e}")
        return False

def get_current_version(engine):
    """Get current database version."""
    try:
        inspector = inspect(engine)
        has_alembic_table = inspector.has_table('alembic_version')
        
        if not has_alembic_table:
            return "No migrations applied"
            
        from alembic.migration import MigrationContext
        from alembic.operations import Operations
        
        conn = engine.connect()
        context = MigrationContext.configure(conn)
        current_rev = context.get_current_revision()
        conn.close()
        
        return current_rev or "No migrations applied"
    except Exception as e:
        logger.error(f"Failed to get current database version: {e}")
        return "Error getting version"