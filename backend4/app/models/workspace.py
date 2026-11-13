"""Workspace, membership, and project models."""
from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import relationship

from app.models.base import Base, generate_uuid, utc_now


class Workspace(Base):
    __tablename__ = "workspaces"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False)
    currency = Column(String(8), default="₹", nullable=False)
    industry_pack = Column(String(64), default="general", nullable=False)
    created_by = Column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    members = relationship("WorkspaceMember", back_populates="workspace", cascade="all, delete-orphan")
    projects = relationship("Project", back_populates="workspace", cascade="all, delete-orphan")
    datasets = relationship("Dataset", back_populates="workspace", cascade="all, delete-orphan")
    chats = relationship("Conversation", back_populates="workspace", cascade="all, delete-orphan")
    decisions = relationship("Decision", back_populates="workspace", cascade="all, delete-orphan")
    reports = relationship("Report", back_populates="workspace", cascade="all, delete-orphan")


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    workspace_id = Column(String(64), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(32), default="owner", nullable=False)  # owner, admin, member, viewer
    joined_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    workspace = relationship("Workspace", back_populates="members")
    user = relationship("User", back_populates="workspace_memberships")

    __table_args__ = (
        Index("ix_workspace_members_ws_user", "workspace_id", "user_id", unique=True),
    )


class Project(Base):
    __tablename__ = "projects"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    workspace_id = Column(String(64), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by = Column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    name = Column(String(255), nullable=False)
    instructions = Column(Text, default="", nullable=False)
    industry_pack = Column(String(64), nullable=True)
    currency = Column(String(8), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    workspace = relationship("Workspace", back_populates="projects")
    datasets = relationship("Dataset", back_populates="project")
