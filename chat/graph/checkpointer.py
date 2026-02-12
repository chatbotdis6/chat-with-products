"""
PostgreSQL Checkpointer for LangGraph session persistence.

This module provides session persistence using PostgreSQL, which is
essential for WhatsApp where conversations must persist across sessions.
"""
import logging
from typing import Optional
from contextlib import contextmanager

from langgraph.checkpoint.postgres import PostgresSaver
from psycopg_pool import ConnectionPool

from chat.config.settings import settings

logger = logging.getLogger(__name__)


class PostgresCheckpointer:
    """
    PostgreSQL-based checkpointer for LangGraph conversations.
    
    This enables:
    1. Session persistence across server restarts
    2. Independent conversation threads (for WhatsApp)
    3. Conversation history retrieval
    """
    
    _instance: Optional['PostgresCheckpointer'] = None
    _pool: Optional[ConnectionPool] = None
    _saver: Optional[PostgresSaver] = None
    
    def __new__(cls):
        """Singleton pattern for connection pool efficiency."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialize the checkpointer (lazy initialization)."""
        pass
    
    def _get_connection_string(self) -> str:
        """Get PostgreSQL connection string compatible with psycopg3."""
        db_url = settings.database_url_normalized
        
        # Convert SQLAlchemy URL to psycopg3 format
        # From: postgresql+psycopg2://user:pass@host:port/db
        # To: postgresql://user:pass@host:port/db
        if "psycopg2" in db_url:
            db_url = db_url.replace("+psycopg2", "")
        if "psycopg" in db_url:
            db_url = db_url.replace("+psycopg", "")
        
        # Heroku uses postgres:// but psycopg3 needs postgresql://
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        
        return db_url
    
    def _ensure_initialized(self):
        """Ensure the connection pool and saver are initialized."""
        if self._pool is None:
            logger.info("🔧 Initializing PostgreSQL connection pool for checkpointer...")
            
            conn_string = self._get_connection_string()
            
            try:
                self._pool = ConnectionPool(
                    conn_string,
                    min_size=1,
                    max_size=5,
                    kwargs={"autocommit": True},
                    # Reconnect stale/broken SSL connections automatically
                    check=ConnectionPool.check_connection,
                    max_idle=300,  # Close idle connections after 5 min
                )
                
                # Create the saver
                self._saver = PostgresSaver(self._pool)
                
                # Setup the schema (creates tables if they don't exist)
                self._saver.setup()
                
                logger.info("✅ PostgreSQL checkpointer initialized successfully")
                
            except Exception as e:
                logger.error(f"❌ Failed to initialize PostgreSQL checkpointer: {e}")
                # Fallback: use memory checkpointer
                logger.warning("⚠️  Falling back to memory checkpointer (no persistence)")
                self._saver = None
                raise
    
    def get_saver(self) -> Optional[PostgresSaver]:
        """
        Get the PostgresSaver instance.
        
        Returns:
            PostgresSaver instance or None if initialization failed
        """
        try:
            self._ensure_initialized()
            return self._saver
        except Exception as e:
            logger.error(f"❌ Could not get checkpointer saver: {e}")
            return None
    
    @contextmanager
    def get_connection(self):
        """Context manager for getting a database connection."""
        self._ensure_initialized()
        if self._pool:
            conn = self._pool.getconn()
            try:
                yield conn
            finally:
                self._pool.putconn(conn)
        else:
            yield None
    
    def close(self):
        """Close the connection pool."""
        if self._pool:
            logger.info("🔧 Closing PostgreSQL connection pool...")
            self._pool.close()
            self._pool = None
            self._saver = None
            logger.info("✅ Connection pool closed")


# Singleton instance
_checkpointer: Optional[PostgresCheckpointer] = None


def get_postgres_checkpointer() -> PostgresCheckpointer:
    """Get or create the PostgreSQL checkpointer singleton."""
    global _checkpointer
    if _checkpointer is None:
        _checkpointer = PostgresCheckpointer()
    return _checkpointer


def get_checkpointer_saver() -> Optional[PostgresSaver]:
    """
    Get the PostgresSaver for use with LangGraph.
    
    Returns:
        PostgresSaver instance or None if not available
    """
    try:
        checkpointer = get_postgres_checkpointer()
        return checkpointer.get_saver()
    except Exception as e:
        logger.warning(f"⚠️  Could not get PostgreSQL checkpointer: {e}")
        logger.warning("⚠️  Conversations will not be persisted!")
        return None
