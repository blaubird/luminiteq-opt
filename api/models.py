from sqlalchemy import (
    Column, String, Text, DateTime, Integer, Enum, ForeignKey
)
from sqlalchemy.orm import Mapped, mapped_column # Import Mapped and mapped_column for new syntax
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
from pgvector.sqlalchemy import Vector # Import Vector

Base = declarative_base()

class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    phone_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    wh_token: Mapped[str] = mapped_column(Text, nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, default="You are a helpful assistant.")

class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True)
    wa_msg_id: Mapped[str] = mapped_column(String, unique=True)
    role: Mapped[str] = mapped_column(Enum("user", "assistant", name="role_enum"))
    text: Mapped[str] = mapped_column(Text)
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class FAQ(Base):
    __tablename__ = "faqs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), nullable=False, index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    # Changed from JSON to Vector(1536) for pgvector compatibility
    embedding: Mapped[Vector] = mapped_column(Vector(1536), nullable=True) 
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

