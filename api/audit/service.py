from sqlalchemy.ext.asyncio import AsyncSession
from db.models import AuditLog


async def log_event(
    session: AsyncSession,
    actor_email: str,
    action: str,
    target: str | None = None,
    detail: str | None = None,
    ip: str | None = None,
) -> None:
    """Write a single audit event to the AuditLog table."""
    entry = AuditLog(
        actor_email=actor_email,
        action=action,
        target=target,
        detail=detail,
        ip_address=ip,
    )
    session.add(entry)
    await session.commit()
