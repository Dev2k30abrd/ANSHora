"""Integrations, email deliveries, monitors, notifications, and audit models."""
from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text

from app.models.base import Base, generate_uuid, utc_now


class GmailIntegration(Base):
    __tablename__ = "gmail_integrations"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    workspace_id = Column(String(64), ForeignKey("workspaces.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    email = Column(String(255), nullable=False)
    refresh_token = Column(Text, nullable=True)
    access_token = Column(Text, nullable=True)
    expires_at = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class OAuthState(Base):
    __tablename__ = "oauth_states"

    state = Column(String(255), primary_key=True)
    workspace_id = Column(String(64), nullable=True)
    user_id = Column(String(64), nullable=True)
    redirect_url = Column(Text, nullable=True)
    purpose = Column(String(32), default="gmail", nullable=False)  # 'gmail' or 'signin'
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)


class EmailDelivery(Base):
    __tablename__ = "email_deliveries"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    workspace_id = Column(String(64), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    recipient = Column(String(255), nullable=False)
    subject = Column(String(255), nullable=False)
    report_type = Column(String(64), default="executive", nullable=False)
    format = Column(String(32), default="pdf", nullable=False)
    status = Column(String(32), nullable=False)  # 'sent', 'failed'
    message_id = Column(String(255), nullable=True)
    error = Column(Text, nullable=True)
    signature = Column(String(255), nullable=True)
    action_id = Column(String(255), nullable=True)
    sent_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)


class EmailPreviewToken(Base):
    __tablename__ = "email_preview_tokens"

    token = Column(String(255), primary_key=True)
    workspace_id = Column(String(64), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    dataset_id = Column(String(64), nullable=True)
    recipient = Column(String(255), nullable=False)
    subject = Column(String(255), nullable=False)
    format = Column(String(32), default="pdf", nullable=False)
    action_id = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    expires_at = Column(String(64), nullable=True)


class Monitor(Base):
    __tablename__ = "monitors"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    workspace_id = Column(String(64), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    dataset_id = Column(String(64), ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    kind = Column(String(64), nullable=False)  # threshold, anomaly, profit_scan
    config = Column(Text, default="{}", nullable=False)  # JSON string
    interval_minutes = Column(Integer, default=60, nullable=False)
    channels = Column(Text, default="[]", nullable=False)  # JSON string
    enabled = Column(Integer, default=1, nullable=False)
    last_run = Column(String(64), nullable=True)
    last_status = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    workspace_id = Column(String(64), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    monitor_id = Column(String(64), ForeignKey("monitors.id", ondelete="SET NULL"), nullable=True)
    dataset_id = Column(String(64), ForeignKey("datasets.id", ondelete="SET NULL"), nullable=True)
    title = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)
    severity = Column(String(32), default="warning", nullable=False)
    impact = Column(Float, nullable=True)
    read = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    workspace_id = Column(String(64), nullable=True, index=True)
    user_id = Column(String(64), nullable=True, index=True)
    action = Column(String(128), nullable=False)
    detail = Column(Text, nullable=True)
    ts = Column(DateTime(timezone=True), default=utc_now, nullable=False)
