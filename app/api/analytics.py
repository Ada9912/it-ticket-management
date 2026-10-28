from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Ticket

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/overview")
def get_service_overview(db: Session = Depends(get_db)):
    """Return an operational snapshot for the helpdesk dashboard."""
    open_statuses = ("OPEN", "ASSIGNED", "IN_PROGRESS")
    backlog = db.query(Ticket).filter(Ticket.status.in_(open_statuses))
    aging_cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=24)

    by_status = dict(
        db.query(Ticket.status, func.count(Ticket.id))
        .group_by(Ticket.status)
        .all()
    )
    by_category = dict(
        db.query(Ticket.category, func.count(Ticket.id))
        .group_by(Ticket.category)
        .all()
    )

    return {
        "total_tickets": db.query(func.count(Ticket.id)).scalar() or 0,
        "open_backlog": backlog.count(),
        "unassigned_backlog": backlog.filter(Ticket.engineer_id.is_(None)).count(),
        "high_priority_backlog": backlog.filter(Ticket.priority == "HIGH").count(),
        "aging_backlog_over_24h": backlog.filter(Ticket.created_at < aging_cutoff).count(),
        "tickets_by_status": by_status,
        "tickets_by_category": by_category,
        "aging_threshold_hours": 24,
        "generated_at": datetime.now(UTC).isoformat(),
    }
