# backend/app/db/session.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from backend.app.core.config import DATABASE_URL # Adjust import path if needed

# Create the SQLAlchemy engine
# echo=True will log all SQL queries, useful for debugging
engine = create_engine(DATABASE_URL, echo=True)

# Create a SessionLocal class for database sessions
# autocommit=False ensures transactions are not automatically committed
# autoflush=False means objects are not automatically flushed to the database
# bind=engine links the session to our database engine
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for declarative models
# All SQLAlchemy models will inherit from this Base
Base = declarative_base()

# Dependency to get a database session (for FastAPI later)
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()