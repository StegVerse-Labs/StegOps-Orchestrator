from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import String, Text, DateTime, ForeignKey, Integer, Boolean, Numeric, UniqueConstraint
from datetime import datetime

class Base(DeclarativeBase):
    pass

class Lead(Base):
    __tablename__ = "leads"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    company: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="new")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    deals: Mapped[list["Deal"]] = relationship(back_populates="lead")

class Deal(Base):
    __tablename__ = "deals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"), index=True)
    tier: Mapped[str] = mapped_column(String(10), default="2")
    stage: Mapped[str] = mapped_column(String(50), default="scoping")
    value_usd: Mapped[float | None] = mapped_column(Numeric(12,2), nullable=True)
    probability: Mapped[int] = mapped_column(Integer, default=50)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    lead: Mapped["Lead"] = relationship(back_populates="deals")
    messages: Mapped[list["Message"]] = relationship(back_populates="deal")

class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (UniqueConstraint("message_id", name="uq_messages_message_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    deal_id: Mapped[int | None] = mapped_column(ForeignKey("deals.id"), nullable=True, index=True)

    direction: Mapped[str] = mapped_column(String(10))  # inbound/outbound
    channel: Mapped[str] = mapped_column(String(20), default="email")

    thread_id: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    message_id: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)

    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    from_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    to_email: Mapped[str | None] = mapped_column(String(320), nullable=True)

    content: Mapped[str] = mapped_column(Text)
    confidence_score: Mapped[float | None] = mapped_column(Numeric(4,3), nullable=True)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=True)

    gmail_draft_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    deal: Mapped["Deal"] = relationship(back_populates="messages")

class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor: Mapped[str] = mapped_column(String(20))
    action: Mapped[str] = mapped_column(String(200))
    object_type: Mapped[str] = mapped_column(String(50))
    object_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    detail_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class GoogleToken(Base):
    __tablename__ = "google_tokens"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    token_json: Mapped[str] = mapped_column(Text)  # serialized Credentials
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class GmailState(Base):
    __tablename__ = "gmail_state"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    last_history_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
