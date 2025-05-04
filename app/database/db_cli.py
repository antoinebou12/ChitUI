# db_cli.py
import click
import typer
from rich.console import Console
from rich.table import Table
from pathlib import Path
from datetime import datetime
import time

from app.database.db_config import setup_db_engine
from app.database.db_migration import (
    create_migration, run_migrations, downgrade_migrations,
    list_migrations, get_current_version
)
from app.database.db_backup import DatabaseBackup
from app.utils import load_config_file as load_config

# Create console for rich output
console = Console()

# Create CLI app
app = typer.Typer(name="chituidb", help="ChitUI Database Management CLI")

@app.command()
def info(
    config_file: str = typer.Option(None, "--config", "-c", help="Path to configuration file")
):
    """Display database information."""
    from app.utils import load_config
    
    # Load configuration
    config = load_config(config_file)
    
    # Get engine
    engine, _ = setup_db_engine(config)
    
    # Display information
    table = Table(title="Database Information")
    
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Database URI", config.get('database_uri', 'Not set'))
    table.add_row("Driver", engine.driver)
    table.add_row("Dialect", engine.dialect.name)
    
    if engine.dialect.name == 'sqlite':
        db_path = config.get('database_uri', '').replace('sqlite:///', '')
        if db_path:
            path = Path(db_path)
            if path.exists():
                size_mb = path.stat().st_size / (1024 * 1024)
                table.add_row("Database Size", f"{size_mb:.2f} MB")
                table.add_row("Last Modified", datetime.fromtimestamp(path.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S'))
    
    # Get current version
    current_version = get_current_version(engine)
    table.add_row("Current Version", current_version)
    
    # Get connection pool info
    table.add_row("Pool Size", str(engine.pool.size()))
    table.add_row("Pool Timeout", str(engine.pool.timeout()))
    
    console.print(table)

@app.command()
def migrate(
    message: str = typer.Argument(..., help="Migration message"),
    config_file: str = typer.Option(None, "--config", "-c", help="Path to configuration file")
):
    """Create a new migration."""
    if create_migration(message):
        console.print(f"[green]Migration created: {message}[/green]")
    else:
        console.print("[red]Failed to create migration[/red]")

@app.command()
def upgrade(
    config_file: str = typer.Option(None, "--config", "-c", help="Path to configuration file")
):
    """Run all pending migrations."""
    with console.status("[bold green]Running migrations...[/bold green]") as status:
        if run_migrations():
            console.print("[green]Migrations completed successfully[/green]")
        else:
            console.print("[red]Failed to run migrations[/red]")

@app.command()
def downgrade(
    revision: str = typer.Argument(..., help="Revision to downgrade to"),
    config_file: str = typer.Option(None, "--config", "-c", help="Path to configuration file")
):
    """Downgrade migrations to a specific revision."""
    with console.status(f"[bold yellow]Downgrading to revision: {revision}[/bold yellow]") as status:
        if downgrade_migrations(revision):
            console.print(f"[green]Downgraded to revision: {revision}[/green]")
        else:
            console.print("[red]Failed to downgrade migrations[/red]")

@app.command()
def backup(
    description: str = typer.Option(None, "--desc", "-d", help="Backup description"),
    config_file: str = typer.Option(None, "--config", "-c", help="Path to configuration file")
):
    """Create a database backup."""
    from app.utils import load_config
    
    # Load configuration
    config = load_config(config_file)
    
    backup_manager = DatabaseBackup(config)
    
    with console.status("[bold green]Creating backup...[/bold green]") as status:
        backup_info = backup_manager.create_backup(description)
        
        if backup_info:
            console.print(f"[green]Backup created: {backup_info['filename']}[/green]")
            
            # Print details
            table = Table(title="Backup Information")
            table.add_column("Property", style="cyan")
            table.add_column("Value", style="green")
            
            table.add_row("ID", backup_info["id"])
            table.add_row("Filename", backup_info["filename"])
            table.add_row("Timestamp", backup_info["timestamp"])
            table.add_row("Size", f"{backup_info['size'] / (1024 * 1024):.2f} MB")
            
            if backup_info["description"]:
                table.add_row("Description", backup_info["description"])
            
            console.print(table)
        else:
            console.print("[red]Backup failed[/red]")

@app.command()
def backups(
    limit: int = typer.Option(10, "--limit", "-l", help="Maximum number of backups to list"),
    config_file: str = typer.Option(None, "--config", "-c", help="Path to configuration file")
):
    """List database backups."""
    from app.utils import load_config
    
    # Load configuration
    config = load_config(config_file)
    
    backup_manager = DatabaseBackup(config)
    backups = backup_manager.list_backups(limit)
    
    if not backups:
        console.print("[yellow]No backups found[/yellow]")
        return
    
    table = Table(title=f"Database Backups (showing {len(backups)} of {len(backup_manager.metadata['backups'])})")
    
    table.add_column("ID", style="cyan")
    table.add_column("Timestamp", style="green")
    table.add_column("Size (MB)", justify="right")
    table.add_column("Status", style="cyan")
    table.add_column("Description")
    
    for backup in backups:
        size_mb = f"{backup['size'] / (1024 * 1024):.2f}"
        status = "[green]Success[/green]" if backup["success"] else f"[red]Failed: {backup['error']}[/red]"
        description = backup["description"] or ""
        
        table.add_row(
            backup["id"],
            backup["timestamp"],
            size_mb,
            status,
            description
        )
    
    console.print(table)

@app.command()
def restore(
    backup_id: str = typer.Argument(..., help="Backup ID to restore"),
    config_file: str = typer.Option(None, "--config", "-c", help="Path to configuration file")
):
    """Restore database from backup."""
    from app.utils import load_config
    
    # Load configuration
    config = load_config(config_file)
    
    backup_manager = DatabaseBackup(config)
    
    # Get backup info
    backup_info = None
    for backup in backup_manager.metadata["backups"]:
        if backup["id"] == backup_id:
            backup_info = backup
            break
    
    if not backup_info:
        console.print(f"[red]Backup not found: {backup_id}[/red]")
        return
    
    # Confirm
    if not typer.confirm(f"Are you sure you want to restore from backup: {backup_info['filename']}?"):
        console.print("[yellow]Restore cancelled[/yellow]")
        return
    
    with console.status("[bold green]Restoring database...[/bold green]") as status:
        if backup_manager.restore_backup(backup_id):
            console.print(f"[green]Database restored from backup: {backup_info['filename']}[/green]")
        else:
            console.print("[red]Restore failed[/red]")

@app.command()
def optimize(
    config_file: str = typer.Option(None, "--config", "-c", help="Path to configuration file")
):
    """Optimize the database."""
    from app.utils import load_config
    
    # Load configuration
    config = load_config(config_file)
    
    # Get engine
    engine, _ = setup_db_engine(config)
    
    with console.status("[bold green]Optimizing database...[/bold green]") as status:
        try:
            if engine.dialect.name == 'sqlite':
                # Execute VACUUM for SQLite
                with engine.connect() as conn:
                    conn.execute("VACUUM;")
                    conn.execute("ANALYZE;")
                console.print("[green]Database optimized successfully[/green]")
            elif engine.dialect.name == 'mysql':
                # Optimize tables for MySQL
                with engine.connect() as conn:
                    result = conn.execute("SHOW TABLES;")
                    tables = [row[0] for row in result]
                    
                    for table in tables:
                        conn.execute(f"OPTIMIZE TABLE {table};")
                console.print("[green]Database tables optimized successfully[/green]")
            elif engine.dialect.name == 'postgresql':
                # VACUUM for PostgreSQL
                with engine.connect() as conn:
                    conn.execute("VACUUM FULL;")
                    conn.execute("ANALYZE;")
                console.print("[green]Database optimized successfully[/green]")
            else:
                console.print(f"[yellow]Optimization not supported for {engine.dialect.name}[/yellow]")
        except Exception as e:
            console.print(f"[red]Optimization failed: {e}[/red]")

if __name__ == "__main__":
    app()