"""Database models and configuration for user management."""

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Float, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from typing import Optional
import bcrypt
import os

# Database configuration — store in data/ directory for security
_db_dir = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(_db_dir, exist_ok=True)
_default_db = f"sqlite:///{os.path.join(_db_dir, 'users.db')}"
DATABASE_URL = os.getenv("DATABASE_URL", _default_db)
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class User(Base):
    """User model for authentication."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password_hash = Column(String(128), nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_login = Column(DateTime, nullable=True)

    def set_password(self, password: str):
        """Hash and set the user's password."""
        self.password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    def check_password(self, password: str) -> bool:
        """Verify the user's password."""
        return bcrypt.checkpw(password.encode('utf-8'), self.password_hash.encode('utf-8'))

    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}', active={self.is_active})>"


class Article(Base):
    """News article model."""
    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, index=True)
    url_hash = Column(String(16), unique=True, index=True, nullable=False)
    title = Column(String(500), nullable=False)
    summary = Column(Text, nullable=True)
    source = Column(String(50), nullable=False)
    url = Column(String(1000), nullable=True)
    published = Column(String(100), nullable=True)
    geo_region = Column(String(100), nullable=True)
    geo_lat = Column(Float, nullable=True)
    geo_lon = Column(Float, nullable=True)
    threat_score = Column(Float, default=0)
    collected_at = Column(DateTime, default=datetime.utcnow)


class ThreatEvent(Base):
    """Cyber threat event model."""
    __tablename__ = "threat_events"

    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(String(50), nullable=False)
    title = Column(String(500), nullable=False)
    severity = Column(String(20), nullable=False)
    source = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    ioc_count = Column(Integer, default=0)
    collected_at = Column(DateTime, default=datetime.utcnow)


def init_db():
    """Initialize the database and create tables."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """Get database session (dependency injection for FastAPI)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_user_by_username(db, username: str) -> Optional[User]:
    """Get user by username."""
    return db.query(User).filter(User.username == username).first()


def get_user_by_id(db, user_id: int) -> Optional[User]:
    """Get user by ID."""
    return db.query(User).filter(User.id == user_id).first()


def create_user(db, username: str, password: str, email: str = None) -> User:
    """Create a new user."""
    user = User(username=username, email=email)
    user.set_password(password)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db, username: str, password: str) -> Optional[User]:
    """Authenticate user with username and password."""
    user = get_user_by_username(db, username)
    if not user:
        return None
    if not user.is_active:
        return None
    if not user.check_password(password):
        return None

    # Update last login
    user.last_login = datetime.utcnow()
    db.commit()

    return user


def list_users(db):
    """List all users."""
    return db.query(User).all()


def deactivate_user(db, username: str) -> bool:
    """Deactivate a user account."""
    user = get_user_by_username(db, username)
    if user:
        user.is_active = False
        db.commit()
        return True
    return False


def activate_user(db, username: str) -> bool:
    """Activate a user account."""
    user = get_user_by_username(db, username)
    if user:
        user.is_active = True
        db.commit()
        return True
    return False


def delete_user(db, username: str) -> bool:
    """Delete a user account."""
    user = get_user_by_username(db, username)
    if user:
        db.delete(user)
        db.commit()
        return True
    return False


def change_password(db, username: str, new_password: str) -> bool:
    """Change user password."""
    user = get_user_by_username(db, username)
    if user:
        user.set_password(new_password)
        db.commit()
        return True
    return False
