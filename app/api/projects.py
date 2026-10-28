from datetime import date, datetime, UTC

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import ProjectTask, ProjectTaskEvent, ProjectRisk

router = APIRouter(prefix="/projects", tags=["Project Management"])
TASK_STATUSES = {"TODO", "IN_PROGRESS", "DONE", "BLOCKED"}
TASK_PRIORITIES = {"HIGH", "MEDIUM", "LOW"}


class TaskCreate(BaseModel):
    project_name: str = Field(min_length=1, max_length=150)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=1000)
    owner: str = Field(min_length=1, max_length=100)
    due_date: date
    status: str = "TODO"
    priority: str = "MEDIUM"
    depends_on_task_id: int | None = None
    is_milestone: bool = False


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    owner: str | None = Field(default=None, min_length=1, max_length=100)
    due_date: date | None = None
    status: str | None = None
    priority: str | None = None
    depends_on_task_id: int | None = None
    is_milestone: bool | None = None


class TaskResponse(BaseModel):
    id: int
    project_name: str
    title: str
    description: str
    owner: str
    due_date: date
    status: str
    priority: str
    depends_on_task_id: int | None
    is_milestone: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


def validate_values(status: str | None, priority: str | None):
    if status is not None and status not in TASK_STATUSES:
        raise HTTPException(422, "status must be TODO, IN_PROGRESS, DONE, or BLOCKED")
    if priority is not None and priority not in TASK_PRIORITIES:
        raise HTTPException(422, "priority must be HIGH, MEDIUM, or LOW")


@router.get("/tasks", response_model=list[TaskResponse])
def list_tasks(project_name: str | None = None, db: Session = Depends(get_db)):
    query = db.query(ProjectTask)
    if project_name:
        query = query.filter(ProjectTask.project_name == project_name)
    return query.order_by(ProjectTask.due_date, ProjectTask.id).all()


@router.post("/tasks", response_model=TaskResponse)
def create_task(task: TaskCreate, db: Session = Depends(get_db)):
    validate_values(task.status, task.priority)
    if task.depends_on_task_id is not None:
        dependency = db.query(ProjectTask).filter(ProjectTask.id == task.depends_on_task_id).first()
        if dependency is None or dependency.project_name != task.project_name:
            raise HTTPException(422, "Dependency must be a task in the same project")
        if dependency.status != "DONE" and task.status in {"IN_PROGRESS", "DONE"}:
            raise HTTPException(409, "Complete the dependency before advancing this task")
    record = ProjectTask(**task.model_dump())
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.patch("/tasks/{task_id}", response_model=TaskResponse)
def update_task(task_id: int, updates: TaskUpdate, db: Session = Depends(get_db)):
    task = db.query(ProjectTask).filter(ProjectTask.id == task_id).first()
    if task is None:
        raise HTTPException(404, "Project task not found")
    values = updates.model_dump(exclude_unset=True)
    validate_values(values.get("status"), values.get("priority"))
    dependency_id = values.get("depends_on_task_id", task.depends_on_task_id)
    if dependency_id == task.id:
        raise HTTPException(422, "A task cannot depend on itself")
    if dependency_id is not None:
        dependency = db.query(ProjectTask).filter(ProjectTask.id == dependency_id).first()
        if dependency is None or dependency.project_name != task.project_name:
            raise HTTPException(422, "Dependency must be a task in the same project")
        cursor = dependency
        visited = set()
        while cursor is not None and cursor.id not in visited:
            if cursor.id == task.id:
                raise HTTPException(422, "Task dependencies cannot contain a cycle")
            visited.add(cursor.id)
            cursor = db.query(ProjectTask).filter(ProjectTask.id == cursor.depends_on_task_id).first() if cursor.depends_on_task_id else None
        if dependency.status != "DONE" and values.get("status", task.status) in {"IN_PROGRESS", "DONE"}:
            raise HTTPException(409, "Complete the dependency before advancing this task")
    tracked_fields = {"owner", "due_date", "status", "priority", "depends_on_task_id"}
    for key, value in values.items():
        if key in tracked_fields and getattr(task, key) != value:
            db.add(ProjectTaskEvent(
                task_id=task.id, field_name=key,
                old_value=str(getattr(task, key)) if getattr(task, key) is not None else None,
                new_value=str(value) if value is not None else "未设置",
            ))
        setattr(task, key, value)
    task.updated_at = datetime.now(UTC).replace(tzinfo=None)
    db.commit()
    db.refresh(task)
    return task


@router.get("/tasks/{task_id}/history")
def task_history(task_id: int, db: Session = Depends(get_db)):
    if db.query(ProjectTask).filter(ProjectTask.id == task_id).first() is None:
        raise HTTPException(404, "Project task not found")
    return db.query(ProjectTaskEvent).filter(
        ProjectTaskEvent.task_id == task_id
    ).order_by(ProjectTaskEvent.created_at.desc()).all()


@router.get("/activity")
def project_activity(project_name: str | None = None, db: Session = Depends(get_db)):
    query = db.query(ProjectTaskEvent, ProjectTask).join(
        ProjectTask, ProjectTask.id == ProjectTaskEvent.task_id
    )
    if project_name:
        query = query.filter(ProjectTask.project_name == project_name)
    return [
        {"id": event.id, "task_id": task.id, "task_title": task.title,
         "field_name": event.field_name, "old_value": event.old_value,
         "new_value": event.new_value, "actor": event.actor,
         "created_at": event.created_at}
        for event, task in query.order_by(ProjectTaskEvent.created_at.desc()).limit(12).all()
    ]


class RiskCreate(BaseModel):
    project_name: str = Field(min_length=1, max_length=150)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=1000)
    impact: str = "MEDIUM"
    owner: str = Field(min_length=1, max_length=100)
    mitigation: str = Field(default="", max_length=1000)


@router.get("/risks")
def list_risks(project_name: str | None = None, db: Session = Depends(get_db)):
    query = db.query(ProjectRisk)
    if project_name:
        query = query.filter(ProjectRisk.project_name == project_name)
    return query.order_by(ProjectRisk.status, ProjectRisk.id).all()


@router.post("/risks")
def create_risk(risk: RiskCreate, db: Session = Depends(get_db)):
    if risk.impact not in TASK_PRIORITIES:
        raise HTTPException(422, "impact must be HIGH, MEDIUM, or LOW")
    record = ProjectRisk(**risk.model_dump())
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.patch("/risks/{risk_id}")
def update_risk(risk_id: int, status: str, db: Session = Depends(get_db)):
    if status not in {"OPEN", "MITIGATING", "CLOSED"}:
        raise HTTPException(422, "status must be OPEN, MITIGATING, or CLOSED")
    risk = db.query(ProjectRisk).filter(ProjectRisk.id == risk_id).first()
    if risk is None:
        raise HTTPException(404, "Project risk not found")
    risk.status = status
    risk.updated_at = datetime.now(UTC).replace(tzinfo=None)
    db.commit()
    db.refresh(risk)
    return risk


@router.get("/overview")
def project_overview(project_name: str | None = None, db: Session = Depends(get_db)):
    query = db.query(ProjectTask)
    if project_name:
        query = query.filter(ProjectTask.project_name == project_name)
    tasks = query.all()
    today = date.today()
    total = len(tasks)
    done = sum(task.status == "DONE" for task in tasks)
    active = sum(task.status == "IN_PROGRESS" for task in tasks)
    blocked = sum(task.status == "BLOCKED" for task in tasks)
    at_risk = sum(
        task.status != "DONE" and task.depends_on_task_id is not None
        and db.query(ProjectTask).filter(ProjectTask.id == task.depends_on_task_id, ProjectTask.status != "DONE").first() is not None
        for task in tasks
    )
    overdue = sum(task.status != "DONE" and task.due_date < today for task in tasks)
    due_soon = sum(
        task.status != "DONE" and today <= task.due_date <= date.fromordinal(today.toordinal() + 7)
        for task in tasks
    )
    risk_query = db.query(ProjectRisk).filter(ProjectRisk.status != "CLOSED")
    if project_name:
        risk_query = risk_query.filter(ProjectRisk.project_name == project_name)
    open_risks = risk_query.count()
    return {
        "project_name": project_name or (tasks[0].project_name if tasks else "IT 服务台升级项目"),
        "total_tasks": total,
        "done_tasks": done,
        "in_progress_tasks": active,
        "blocked_tasks": blocked,
        "dependency_risk_tasks": at_risk,
        "open_risks": open_risks,
        "overdue_tasks": overdue,
        "due_soon_tasks": due_soon,
        "completion_percent": round(done * 100 / total) if total else 0,
        "generated_at": datetime.now(UTC).isoformat(),
    }
