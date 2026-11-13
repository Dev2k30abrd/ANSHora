"""Conversations (chats) and Messages models."""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import relationship

from app.models.base import Base, generate_uuid, utc_now


class Conversation(Base):
    __tablename__ = "chats"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    workspace_id = Column(String(64), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(String(64), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    dataset_id = Column(String(64), ForeignKey("datasets.id", ondelete="SET NULL"), nullable=True, index=True)
    title = Column(String(255), default="New chat", nullable=False)
    is_guest = Column(Boolean, default=False, nullable=False)
    pending_action = Column(Text, nullable=True)  # JSON string
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    workspace = relationship("Workspace", back_populates="chats")
    dataset = relationship("Dataset", back_populates="chats")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at")


class Message(Base):
    __tablename__ = "messages"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    chat_id = Column(String(64), ForeignKey("chats.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(32), nullable=False)  # 'user', 'assistant', 'system'
    content = Column(Text, nullable=False)
    meta = Column(Text, default="{}", nullable=False)  # JSON string: tool_runs, verification, confidence, etc.
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    conversation = relationship("Conversation", back_populates="messages")

    __table_args__ = (
        Index("ix_messages_chat_created", "chat_id", "created_at"),
    )
