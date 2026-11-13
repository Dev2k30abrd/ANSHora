"""User and OAuth identity models."""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import relationship

from app.models.base import Base, generate_uuid, utc_now


class User(Base):
    __tablename__ = "users"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    password_hash = Column(String(255), nullable=True)  # Nullable for Google-only users
    google_subject_id = Column(String(255), unique=True, nullable=True, index=True)
    email_verified = Column(Boolean, default=False, nullable=False)
    profile_image_url = Column(Text, nullable=True)
    workspace_id = Column(String(64), nullable=True, index=True)
    role = Column(String(32), default="admin", nullable=False)
    account_status = Column(String(32), default="active", nullable=False)  # active, suspended
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    last_login_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    oauth_identities = relationship("OAuthIdentity", back_populates="user", cascade="all, delete-orphan")
    workspace_memberships = relationship("WorkspaceMember", back_populates="user", cascade="all, delete-orphan")


class OAuthIdentity(Base):
    __tablename__ = "oauth_identities"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    user_id = Column(String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String(32), default="google", nullable=False)  # 'google'
    provider_user_id = Column(String(255), nullable=False)  # google 'sub' claim
    email = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    user = relationship("User", back_populates="oauth_identities")

    __table_args__ = (
        Index("ix_oauth_identities_provider_sub", "provider", "provider_user_id", unique=True),
    )
