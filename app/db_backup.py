# db_backup.py
import os
import sys
import time
import gzip
import shutil
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path
from loguru import logger
import json

class DatabaseBackup:
    def __init__(self, config):
        """Initialize backup manager with configuration."""
        self.config = config
        self.backup_dir = Path(config.get('backup_folder', 'backups'))
        self.backup_dir.mkdir(exist_ok=True)
        
        # Database URI
        self.db_uri = config.get('database_uri', 'sqlite:///chitui.db')
        
        # Metadata storage
        self.metadata_file = self.backup_dir / "backup_metadata.json"
        self.metadata = self._load_metadata()
    
    def _load_metadata(self):
        """Load backup metadata from file."""
        if not self.metadata_file.exists():
            return {"backups": []}
        
        try:
            with open(self.metadata_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load backup metadata: {e}")
            return {"backups": []}
    
    def _save_metadata(self):
        """Save backup metadata to file."""
        try:
            with open(self.metadata_file, 'w') as f:
                json.dump(self.metadata, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save backup metadata: {e}")
    
    def _get_db_type(self):
        """Get database type from URI."""
        if self.db_uri.startswith('sqlite:'):
            return 'sqlite'
        elif self.db_uri.startswith('mysql:') or self.db_uri.startswith('mysql+pymysql:'):
            return 'mysql'
        elif self.db_uri.startswith('postgresql:'):
            return 'postgresql'
        else:
            return 'unknown'
    
    def _get_db_path(self):
        """Get database file path for SQLite."""
        if self._get_db_type() == 'sqlite':
            if self.db_uri.startswith('sqlite:///'):
                # Relative path
                return self.db_uri[10:]
            elif self.db_uri.startswith('sqlite://'):
                # Absolute path
                return self.db_uri[9:]
        return None
    
    def create_backup(self, description=None):
        """Create a new database backup."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_id = f"{timestamp}_{os.urandom(4).hex()}"
        backup_filename = f"chitui_backup_{timestamp}.gz"
        backup_path = self.backup_dir / backup_filename
        
        db_type = self._get_db_type()
        success = False
        error_message = None
        
        try:
            if db_type == 'sqlite':
                # SQLite backup - file copy with compression
                db_path = self._get_db_path()
                if not db_path or not Path(db_path).exists():
                    raise FileNotFoundError(f"Database file not found: {db_path}")
                
                with open(db_path, 'rb') as f_in:
                    with gzip.open(backup_path, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                
                success = True
                
            elif db_type == 'mysql':
                # MySQL backup using mysqldump
                from sqlalchemy.engine.url import make_url
                url = make_url(self.db_uri)
                
                cmd = [
                    'mysqldump',
                    f'--host={url.host}',
                    f'--port={url.port or 3306}',
                    f'--user={url.username}',
                ]
                
                if url.password:
                    cmd.append(f'--password={url.password}')
                
                cmd.append(url.database)
                
                with gzip.open(backup_path, 'wb') as f_out:
                    process = subprocess.Popen(cmd, stdout=subprocess.PIPE)
                    for chunk in iter(lambda: process.stdout.read(4096), b''):
                        f_out.write(chunk)
                
                if process.wait() == 0:
                    success = True
                else:
                    error_message = "mysqldump command failed"
                
            elif db_type == 'postgresql':
                # PostgreSQL backup using pg_dump
                from sqlalchemy.engine.url import make_url
                url = make_url(self.db_uri)
                
                env = os.environ.copy()
                if url.password:
                    env['PGPASSWORD'] = url.password
                
                cmd = [
                    'pg_dump',
                    f'--host={url.host}',
                    f'--port={url.port or 5432}',
                    f'--username={url.username}',
                    f'--dbname={url.database}',
                    '--format=c',  # Custom format (compressed)
                ]
                
                with open(backup_path, 'wb') as f_out:
                    process = subprocess.Popen(cmd, stdout=f_out, env=env)
                    process.wait()
                
                if process.returncode == 0:
                    success = True
                else:
                    error_message = "pg_dump command failed"
                
            else:
                error_message = f"Unsupported database type: {db_type}"
                
        except Exception as e:
            error_message = str(e)
            logger.error(f"Backup failed: {e}")
            
            # Clean up if file was created
            if backup_path.exists():
                backup_path.unlink()
        
        # Add to metadata
        backup_info = {
            "id": backup_id,
            "filename": backup_filename,
            "timestamp": timestamp,
            "db_type": db_type,
            "description": description,
            "success": success,
            "error": error_message,
            "size": backup_path.stat().st_size if backup_path.exists() else 0,
        }
        
        self.metadata["backups"].append(backup_info)
        self._save_metadata()
        
        if success:
            logger.info(f"Backup created: {backup_filename}")
            return backup_info
        else:
            logger.error(f"Backup failed: {error_message}")
            return None
    
    def restore_backup(self, backup_id):
        """Restore database from backup."""
        # Find backup in metadata
        backup_info = None
        for backup in self.metadata["backups"]:
            if backup["id"] == backup_id:
                backup_info = backup
                break
        
        if not backup_info:
            logger.error(f"Backup not found: {backup_id}")
            return False
        
        backup_path = self.backup_dir / backup_info["filename"]
        if not backup_path.exists():
            logger.error(f"Backup file not found: {backup_path}")
            return False
        
        db_type = self._get_db_type()
        success = False
        error_message = None
        
        try:
            if db_type == 'sqlite':
                # SQLite restore - file copy
                db_path = self._get_db_path()
                if not db_path:
                    raise ValueError("Database path not found in URI")
                
                # Create backup of current database
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                current_backup = f"{db_path}.{timestamp}.bak"
                shutil.copy2(db_path, current_backup)
                
                # Restore from backup
                with gzip.open(backup_path, 'rb') as f_in:
                    with open(db_path, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                
                success = True
                
            elif db_type == 'mysql':
                # MySQL restore
                from sqlalchemy.engine.url import make_url
                url = make_url(self.db_uri)
                
                cmd = [
                    'mysql',
                    f'--host={url.host}',
                    f'--port={url.port or 3306}',
                    f'--user={url.username}',
                ]
                
                if url.password:
                    cmd.append(f'--password={url.password}')
                
                cmd.append(url.database)
                
                with gzip.open(backup_path, 'rb') as f_in:
                    process = subprocess.Popen(cmd, stdin=subprocess.PIPE)
                    for chunk in iter(lambda: f_in.read(4096), b''):
                        process.stdin.write(chunk)
                    process.stdin.close()
                
                if process.wait() == 0:
                    success = True
                else:
                    error_message = "mysql restore command failed"
                
            elif db_type == 'postgresql':
                # PostgreSQL restore
                from sqlalchemy.engine.url import make_url
                url = make_url(self.db_uri)
                
                env = os.environ.copy()
                if url.password:
                    env['PGPASSWORD'] = url.password
                
                cmd = [
                    'pg_restore',
                    f'--host={url.host}',
                    f'--port={url.port or 5432}',
                    f'--username={url.username}',
                    f'--dbname={url.database}',
                    '--clean',  # Clean (drop) database objects before recreating
                    backup_path
                ]
                
                process = subprocess.Popen(cmd, env=env)
                if process.wait() == 0:
                    success = True
                else:
                    error_message = "pg_restore command failed"
                
            else:
                error_message = f"Unsupported database type: {db_type}"
                
        except Exception as e:
            error_message = str(e)
            logger.error(f"Restore failed: {e}")
        
        if success:
            logger.info(f"Database restored from backup: {backup_info['filename']}")
            return True
        else:
            logger.error(f"Restore failed: {error_message}")
            return False
    
    def list_backups(self, limit=None):
        """List all backups."""
        backups = sorted(
            self.metadata["backups"], 
            key=lambda x: x["timestamp"], 
            reverse=True
        )
        
        if limit:
            return backups[:limit]
        return backups
    
    def delete_backup(self, backup_id):
        """Delete a backup."""
        # Find backup in metadata
        backup_info = None
        backup_index = -1
        
        for i, backup in enumerate(self.metadata["backups"]):
            if backup["id"] == backup_id:
                backup_info = backup
                backup_index = i
                break
        
        if not backup_info:
            logger.error(f"Backup not found: {backup_id}")
            return False
        
        backup_path = self.backup_dir / backup_info["filename"]
        if backup_path.exists():
            try:
                backup_path.unlink()
            except Exception as e:
                logger.error(f"Failed to delete backup file: {e}")
                return False
        
        # Remove from metadata
        self.metadata["backups"].pop(backup_index)
        self._save_metadata()
        
        logger.info(f"Backup deleted: {backup_info['filename']}")
        return True