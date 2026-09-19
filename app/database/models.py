import json
from datetime import datetime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import String, Float, Integer, Text, ForeignKey, DateTime

class Base(DeclarativeBase):
    pass

class ReelRecord(Base):
    __tablename__ = "reels"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    url: Mapped[str] = mapped_column(String(512), nullable=True)
    title: Mapped[str] = mapped_column(String(256), default="")
    author: Mapped[str] = mapped_column(String(128), default="")
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    video_path: Mapped[str] = mapped_column(String(512), default="")
    overall_trust_score: Mapped[int] = mapped_column(Integer, default=100)
    overall_verdict: Mapped[str] = mapped_column(String(32), default="TRUE")
    executive_summary: Mapped[str] = mapped_column(Text, default="")
    transcript_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    claims = relationship("ClaimRecord", back_populates="reel", cascade="all, delete-orphan")
    chat_messages = relationship("ChatMessageRecord", back_populates="reel", cascade="all, delete-orphan")

class ClaimRecord(Base):
    __tablename__ = "claims"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    reel_id: Mapped[str] = mapped_column(String(64), ForeignKey("reels.id"), nullable=False)
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp_start: Mapped[float] = mapped_column(Float, default=0.0)
    timestamp_end: Mapped[float] = mapped_column(Float, default=0.0)
    verdict: Mapped[str] = mapped_column(String(32), default="UNVERIFIABLE")
    confidence_score: Mapped[int] = mapped_column(Integer, default=50)
    summary_rationale: Mapped[str] = mapped_column(Text, default="")
    detailed_analysis: Mapped[str] = mapped_column(Text, default="")
    key_nuances: Mapped[str] = mapped_column(Text, nullable=True)
    sources_json: Mapped[str] = mapped_column(Text, default="[]")

    reel = relationship("ReelRecord", back_populates="claims")

class ChatMessageRecord(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reel_id: Mapped[str] = mapped_column(String(64), ForeignKey("reels.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    reel = relationship("ReelRecord", back_populates="chat_messages")
