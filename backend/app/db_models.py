from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Float
from sqlalchemy.orm import relationship

from backend.app.database import Base


class Account(Base):
    __tablename__ = "accounts"

    client_id = Column(String, primary_key=True)
    available = Column(Integer, default=0, nullable=False)
    reserved = Column(Integer, default=0, nullable=False)


class Wallet(Base):
    __tablename__ = "wallets"

    client_id = Column(String, primary_key=True)
    onchain_address = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Transaction(Base):
    __tablename__ = "transactions"

    idempotency_key = Column(String, primary_key=True)
    operation_type = Column(String, nullable=False)
    status = Column(String, nullable=False)
    client_id = Column(String, nullable=True)
    to_client_id = Column(String, nullable=True)
    amount = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    error_message = Column(String, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event = Column(String, nullable=False)
    client_id = Column(String, nullable=False)
    amount = Column(Integer, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    snapshot_json = Column(String, nullable=True)
