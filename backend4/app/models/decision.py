"""Decision intelligence, outcomes, and business memory models."""
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.models.base import Base, generate_uuid, utc_now


class Decision(Base):
    __tablename__ = "decisions"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    workspace_id = Column(String(64), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    dataset_id = Column(String(64), ForeignKey("datasets.id", ondelete="SET NULL"), nullable=True, index=True)
    project_id = Column(String(64), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    created_by = Column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    title = Column(String(255), nullable=False)
    action = Column(Text, default="", nullable=False)
    problem = Column(Text, default="", nullable=False)
    evidence = Column(Text, default="", nullable=False)  # JSON or string
    assumptions = Column(Text, default="", nullable=False)
    risks = Column(Text, default="", nullable=False)
    confidence = Column(String(32), default="medium", nullable=False)
    justification = Column(Text, default="", nullable=False)
    priority = Column(String(32), default="medium", nullable=False)
    owner = Column(String(255), default="", nullable=False)
    metric_column = Column(String(128), nullable=True)
    aggregation = Column(String(32), default="sum", nullable=False)
    direction = Column(String(16), default="up", nullable=False)
    baseline_value = Column(Float, default=0.0, nullable=False)
    expected_impact = Column(Float, nullable=True)
    review_date = Column(String(64), nullable=True)
    status = Column(String(32), default="Proposed", nullable=False)
    latest_value = Column(Float, nullable=True)
    realized_impact = Column(Float, nullable=True)
    actual_outcome = Column(Text, nullable=True)
    measured_impact = Column(Float, nullable=True)
    followed_recommendation = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    evaluated_at = Column(DateTime(timezone=True), nullable=True)

    workspace = relationship("Workspace", back_populates="decisions")
    dataset = relationship("Dataset", back_populates="decisions")
    outcomes = relationship("DecisionOutcome", back_populates="decision", cascade="all, delete-orphan")


class DecisionOutcome(Base):
    __tablename__ = "decision_outcomes"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    decision_id = Column(String(64), ForeignKey("decisions.id", ondelete="CASCADE"), nullable=False, index=True)
    evaluated_by = Column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    actual_outcome = Column(Text, nullable=False)
    measured_impact = Column(Float, nullable=True)
    followed_recommendation = Column(Boolean, nullable=True)
    evaluated_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    decision = relationship("Decision", back_populates="outcomes")


class BusinessMemory(Base):
    __tablename__ = "business_memory"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    workspace_id = Column(String(64), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    category = Column(String(64), nullable=False)  # 'decision', 'finding', 'context', 'guideline'
    key = Column(String(255), nullable=False, index=True)
    summary = Column(Text, nullable=False)
    evidence_ref = Column(Text, nullable=True)  # JSON string
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
