# db_config.py
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.pool import QueuePool
from sqlalchemy.exc import SQLAlchemyError
from loguru import logger
import time
import os

def get_database_url(config):
    """Get database URL from config or environment."""
    return config.get('database_uri', os.environ.get('DATABASE_URI', 'sqlite:///chitui.db'))

def setup_db_engine(config, pool_size=10, max_overflow=20, timeout=30):
    """Set up database engine with connection pooling."""
    db_url = get_database_url(config)
    
    connect_args = {}
    if db_url.startswith('sqlite:'):
        # SQLite-specific configuration
        connect_args = {'check_same_thread': False}
    
    engine = create_engine(
        db_url,
        poolclass=QueuePool,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=timeout,
        pool_pre_ping=True,  # Verify connections before using them
        connect_args=connect_args
    )
    
    # Set up connection event listeners
    @event.listens_for(engine, 'connect')
    def on_connect(dbapi_connection, connection_record):
        logger.debug("Database connection established")
    
    @event.listens_for(engine, 'checkout')
    def on_checkout(dbapi_connection, connection_record, connection_proxy):
        connection_record.info['checkout_time'] = time.time()
    
    @event.listens_for(engine, 'checkin')
    def on_checkin(dbapi_connection, connection_record):
        checkout_time = connection_record.info.get('checkout_time')
        if checkout_time is not None:
            connection_record.info.pop('checkout_time')
            elapsed = time.time() - checkout_time
            if elapsed > 10:
                logger.warning(f"Connection held for {elapsed:.2f}s")
    
    # Create session factory
    session_factory = sessionmaker(bind=engine)
    Session = scoped_session(session_factory)
    
    return engine, Session

def get_db_session(config):
    """Get a database session."""
    _, Session = setup_db_engine(config)
    return Session()

def close_db_session(session):
    """Close a database session."""
    try:
        session.close()
    except SQLAlchemyError as e:
        logger.error(f"Error closing database session: {e}")