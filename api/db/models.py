from sqlalchemy import Column, Integer, String, DateTime, func
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True)
    path = Column(String, unique=True, nullable=False, index=True)
    title = Column(String, default="")
    tags = Column(String, default="[]")      # JSON-encoded list
    owner = Column(String, default="")
    status = Column(String, default="current")
    created = Column(String, nullable=True)
    last_reviewed = Column(String, nullable=True)
    review_interval = Column(String, default="90d")
    body_preview = Column(String, default="")  # first 500 chars for list views
    indexed_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
