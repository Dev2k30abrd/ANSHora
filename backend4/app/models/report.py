"""Report metadata and persistence model."""
from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import relationship

from app.models.base import Base, generate_uuid, utc_now


class Report(Base):
    __tablename__ = "reports"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    workspace_id = Column(String(64), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    dataset_id = Column(String(64), ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by = Column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    title = Column(String(255), nullable=False)
    report_type = Column(String(64), default="executive", nullable=False)
    source = Column(String(32), default="ai_narrated", nullable=False)  # 'ai_narrated' or 'deterministic'
    narrative = Column(Text, nullable=False)
    data_block = Column(Text, nullable=False)  # JSON string
    charts = Column(Text, nullable=False)  # JSON string
    ai_warning = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    workspace = relationship("Workspace", back_populates="reports")
    dataset = relationship("Dataset", back_populates="reports")
