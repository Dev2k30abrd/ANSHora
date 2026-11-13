"""Dataset metadata model."""
from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.models.base import Base, generate_uuid, utc_now


class Dataset(Base):
    __tablename__ = "datasets"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    workspace_id = Column(String(64), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)  # owner
    project_id = Column(String(64), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    filename = Column(String(255), nullable=False)
    path = Column(Text, nullable=False)
    file_size_bytes = Column(BigInteger, default=0, nullable=False)
    mime_type = Column(String(64), default="text/csv", nullable=False)
    rows = Column(Integer, default=0, nullable=False)
    cols = Column(Integer, default=0, nullable=False)
    pack_id = Column(String(64), default="general", nullable=False)
    source = Column(String(64), default="upload", nullable=False)
    processing_status = Column(String(32), default="ready", nullable=False)  # ready, processing, error
    business_context = Column(Text, nullable=True)  # JSON string
    alert_rules = Column(Text, nullable=True)  # JSON string
    alert_history = Column(Text, nullable=True)  # JSON string
    settings = Column(Text, nullable=True)  # JSON string
    uploaded_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    workspace = relationship("Workspace", back_populates="datasets")
    project = relationship("Project", back_populates="datasets")
    chats = relationship("Conversation", back_populates="dataset")
    reports = relationship("Report", back_populates="dataset")
    decisions = relationship("Decision", back_populates="dataset")
