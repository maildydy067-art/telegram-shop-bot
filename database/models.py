from sqlalchemy import Column, Integer, String, BigInteger, Boolean, DateTime, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(BigInteger, primary_key=True, unique=True)
    username = Column(String, nullable=True)
    balance = Column(Integer, default=0)
    is_banned = Column(Boolean, default=False)

class Order(Base):
    __tablename__ = 'orders'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger)
    account_id = Column(String)
    account_title = Column(String)
    amount = Column(Integer)
    quantity = Column(Integer, default=1)  # NEW: Quantity column
    payment_method = Column(String, default="balance")  # NEW: Payment method column
    status = Column(String, default="pending")
    created_at = Column(DateTime, server_default=func.now())