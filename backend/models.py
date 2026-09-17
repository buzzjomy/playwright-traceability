"""SQLAlchemy ORM models for the backend service."""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from backend.db import Base


class JiraConnection(Base):
    """A configured connection to one Jira Cloud site.

    Single-row-per-deployment for now (a solo builder's MVP, not yet
    multi-tenant) - see jira_client.py for the auth flow this backs.
    api_token is stored as given, not encrypted; this is a known gap to
    close before any multi-user or production deployment.
    """

    __tablename__ = "jira_connections"

    id: Mapped[int] = mapped_column(primary_key=True)
    site_url: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False)
    api_token: Mapped[str] = mapped_column(String, nullable=False)
