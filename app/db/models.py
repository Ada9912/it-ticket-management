from datetime import datetime, UTC

from sqlalchemy import Column, Integer, String, ForeignKey, Date, DateTime

from .database import Base


def utc_now():
    return datetime.now(UTC)


class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    email = Column(String(150), unique=True, nullable=False, index=True)
    department = Column(String(100), nullable=False)


class Engineer(Base):
    __tablename__ = "engineers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    email = Column(String(150), unique=True, nullable=False, index=True)
    specialization = Column(String(100), nullable=False)


class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    engineer_id = Column(Integer, ForeignKey("engineers.id"), nullable=True)
    title = Column(String(200), nullable=False)
    description = Column(String(1000), nullable=False)
    category = Column(String(50), nullable=False)
    priority = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False, default="OPEN")
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)


class TicketUpdate(Base):
    __tablename__ = "ticket_updates"

    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(Integer, ForeignKey("tickets.id"), nullable=False)
    engineer_id = Column(Integer, ForeignKey("engineers.id"), nullable=False)
    comment = Column(String(1000), nullable=False)
    old_status = Column(String(20), nullable=True)
    new_status = Column(String(20), nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)


class ProjectTask(Base):
    __tablename__ = "project_tasks"

    id = Column(Integer, primary_key=True, index=True)
    project_name = Column(String(150), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    description = Column(String(1000), nullable=False, default="")
    owner = Column(String(100), nullable=False)
    due_date = Column(Date, nullable=False)
    status = Column(String(20), nullable=False, default="TODO")
    priority = Column(String(20), nullable=False, default="MEDIUM")
    depends_on_task_id = Column(Integer, ForeignKey("project_tasks.id"), nullable=True)
    is_milestone = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)


class ProjectTaskEvent(Base):
    __tablename__ = "project_task_events"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("project_tasks.id"), nullable=False, index=True)
    field_name = Column(String(50), nullable=False)
    old_value = Column(String(1000), nullable=True)
    new_value = Column(String(1000), nullable=False)
    actor = Column(String(100), nullable=False, default="项目协作成员")
    created_at = Column(DateTime, default=utc_now, nullable=False)


class ProjectRisk(Base):
    __tablename__ = "project_risks"

    id = Column(Integer, primary_key=True, index=True)
    project_name = Column(String(150), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    description = Column(String(1000), nullable=False, default="")
    impact = Column(String(20), nullable=False, default="MEDIUM")
    owner = Column(String(100), nullable=False)
    mitigation = Column(String(1000), nullable=False, default="")
    status = Column(String(20), nullable=False, default="OPEN")
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)


class AIFeedback(Base):
    __tablename__ = "ai_triage_feedback"

    id = Column(Integer, primary_key=True, index=True)
    issue_text = Column(String(2000), nullable=False)
    suggested_category = Column(String(50), nullable=False)
    selected_action = Column(String(20), nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
