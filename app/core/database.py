from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os

# Use DATABASE_URL from environment if set, otherwise use SQLite in data directory
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "sqlite:///./data/marketing.db"
)

# For SQLite, ensure data directory exists
if DATABASE_URL.startswith("sqlite"):
    # No directory/database creation at import time.
    # Convert relative path to absolute for SQLite
    if DATABASE_URL == "sqlite:///./data/marketing.db":
        DATABASE_URL = f"sqlite:///{os.path.abspath('./data/marketing.db')}"

engine = create_engine(
    DATABASE_URL,
    hide_parameters=True,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
