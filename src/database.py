from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SQLALCHEMY_DATABASE_URL = "sqlite:///./website_monitor.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base  = declarative_base()


def init_db():
    """Initialize the database by creating all tables"""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Successfully initialized database tables")
    except Exception as e:
        logger.error(f"Failed to initialize database: {str(e)}")
        raise
    
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()