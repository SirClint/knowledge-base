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


class DocVersion(Base):
    __tablename__ = "doc_versions"

    id = Column(Integer, primary_key=True)
    doc_path = Column(String, nullable=False, index=True)
    body = Column(String, nullable=False)
    saved_by = Column(String, nullable=False, default="")
    saved_at = Column(DateTime, server_default=func.now())


class Comment(Base):
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True)
    doc_path = Column(String, nullable=False, index=True)
    body = Column(String, nullable=False)
    author_email = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class Setting(Base):
    __tablename__ = "settings"

    key = Column(String, primary_key=True)
    value = Column(String, nullable=False)
