import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import inspect, text

from datetime import date, timedelta

from .db.database import engine, Base, SessionLocal
from .db import models
from .api import employees
from .api import engineers
from .api import tickets
from .api import analytics
from .api import projects
from .api import ai_assistant
from .core.exceptions import (
    DuplicateEmailException,
    EmployeeNotFoundException,
    EngineerNotFoundException,
    TicketNotFoundException
)
from .core.logging import setup_logging

setup_logging()

logger = logging.getLogger(__name__)

Base.metadata.create_all(bind=engine)


def ensure_local_schema_compatibility():
    """Add fields introduced after the first SQLite demo database was created."""
    columns = {column["name"] for column in inspect(engine).get_columns("project_tasks")}
    with engine.begin() as connection:
        if "depends_on_task_id" not in columns:
            connection.execute(text("ALTER TABLE project_tasks ADD COLUMN depends_on_task_id INTEGER"))
        if "is_milestone" not in columns:
            connection.execute(text("ALTER TABLE project_tasks ADD COLUMN is_milestone INTEGER NOT NULL DEFAULT 0"))


ensure_local_schema_compatibility()


def seed_demo_project():
    """Add clearly labeled portfolio data to a fresh local SQLite database."""
    if not str(engine.url).startswith("sqlite"):
        return
    db = SessionLocal()
    try:
        if db.query(models.ProjectTask).first():
            tasks = {task.title: task for task in db.query(models.ProjectTask).all()}
            if "准备 UAT 验收用例" in tasks and "搭建工单 API 与数据模型" in tasks:
                tasks["准备 UAT 验收用例"].depends_on_task_id = tasks["搭建工单 API 与数据模型"].id
            if "安排试点部门上线培训" in tasks and "准备 UAT 验收用例" in tasks:
                tasks["安排试点部门上线培训"].depends_on_task_id = tasks["准备 UAT 验收用例"].id
            for milestone_title in ("完成项目启动会与范围确认", "完成需求评审与原型确认", "准备 UAT 验收用例", "安排试点部门上线培训"):
                if milestone_title in tasks:
                    tasks[milestone_title].is_milestone = 1
            if not db.query(models.ProjectRisk).first():
                db.add_all([
                    models.ProjectRisk(project_name=tasks[next(iter(tasks))].project_name, title="需求范围确认依赖业务部门评审", description="首期优先级和范围尚待业务负责人确认。", impact="HIGH", owner="李明", mitigation="安排 30 分钟范围评审；会后记录决策与未纳入项。"),
                    models.ProjectRisk(project_name=tasks[next(iter(tasks))].project_name, title="邮件通知接口联调环境未就绪", description="外部邮箱团队尚未提供联调环境。", impact="MEDIUM", owner="王凯", mitigation="确认环境交付日期，并准备站内通知作为降级方案。"),
                    models.ProjectRisk(project_name=tasks[next(iter(tasks))].project_name, title="UAT 测试窗口与试点部门排期冲突", description="试点团队排期可能影响验收和培训节点。", impact="MEDIUM", owner="张琳", mitigation="预留替代验收时段，提前确认试点代表。"),
                ])
            db.commit()
            return
        today = date.today()
        project = "IT 服务台升级项目（演示）"
        examples = [
            ("完成项目启动会与范围确认", "同步目标、范围、干系人和验收口径。", "张琳", -4, "DONE", "HIGH"),
            ("梳理现有工单流程与角色权限", "确认员工、工程师、管理员的使用流程。", "李明", -1, "IN_PROGRESS", "HIGH"),
            ("完成需求评审与原型确认", "需业务部门确认优先级和首期范围。", "王凯", 1, "BLOCKED", "HIGH"),
            ("搭建工单 API 与数据模型", "完成工单基础接口及数据表。", "陈晨", 3, "IN_PROGRESS", "MEDIUM"),
            ("准备 UAT 验收用例", "覆盖提单、分派、处理、关闭主流程。", "赵敏", 6, "TODO", "MEDIUM"),
            ("安排试点部门上线培训", "准备操作手册并收集试点反馈。", "张琳", 10, "TODO", "LOW"),
            ("确认邮件通知服务商接口", "等待企业邮箱团队提供联调环境和凭证。", "王凯", -2, "BLOCKED", "MEDIUM"),
        ]
        db.add_all([
            models.ProjectTask(
                project_name=project, title=title, description=description,
                owner=owner, due_date=today + timedelta(days=offset),
                status=status, priority=priority,
            )
            for title, description, owner, offset, status, priority in examples
        ])
        db.commit()
        tasks = {task.title: task for task in db.query(models.ProjectTask).all()}
        if "准备 UAT 验收用例" in tasks and "搭建工单 API 与数据模型" in tasks:
            tasks["准备 UAT 验收用例"].depends_on_task_id = tasks["搭建工单 API 与数据模型"].id
        if "安排试点部门上线培训" in tasks and "准备 UAT 验收用例" in tasks:
            tasks["安排试点部门上线培训"].depends_on_task_id = tasks["准备 UAT 验收用例"].id
        for milestone_title in ("完成项目启动会与范围确认", "完成需求评审与原型确认", "准备 UAT 验收用例", "安排试点部门上线培训"):
            if milestone_title in tasks:
                tasks[milestone_title].is_milestone = 1
        db.add_all([
            models.ProjectRisk(project_name=project, title="需求范围确认依赖业务部门评审", description="首期优先级和范围尚待业务负责人确认。", impact="HIGH", owner="李明", mitigation="安排 30 分钟范围评审；会后记录决策与未纳入项。"),
            models.ProjectRisk(project_name=project, title="邮件通知接口联调环境未就绪", description="外部邮箱团队尚未提供联调环境。", impact="MEDIUM", owner="王凯", mitigation="确认环境交付日期，并准备站内通知作为降级方案。"),
            models.ProjectRisk(project_name=project, title="UAT 测试窗口与试点部门排期冲突", description="试点团队排期可能影响验收和培训节点。", impact="MEDIUM", owner="张琳", mitigation="预留替代验收时段，提前确认试点代表。"),
        ])
        db.commit()
    finally:
        db.close()


seed_demo_project()

app = FastAPI(title="IT Ticket Management System")

app.include_router(employees.router)
app.include_router(engineers.router)
app.include_router(tickets.router)
app.include_router(analytics.router)
app.include_router(projects.router)
app.include_router(ai_assistant.router)


@app.exception_handler(EmployeeNotFoundException)
async def employee_not_found_handler(
    request: Request,
    exc: EmployeeNotFoundException
):
    logger.warning(
        "Employee not found: %s",
        str(exc)
    )

    return JSONResponse(
        status_code=404,
        content={"detail": str(exc)}
    )

@app.exception_handler(EngineerNotFoundException)
async def engineer_not_found_handler(
    request: Request,
    exc: EngineerNotFoundException
):
    logger.warning(
        "Engineer not found: %s",
        str(exc)
    )

    return JSONResponse(
        status_code=404,
        content={"detail": str(exc)}
    )

@app.exception_handler(DuplicateEmailException)
async def duplicate_email_handler(
    request: Request,
    exc: DuplicateEmailException
):
    logger.warning(
        "Duplicate email: %s",
        str(exc)
    )

    return JSONResponse(
        status_code=409,
        content={"detail": str(exc)}
    )

@app.exception_handler(TicketNotFoundException)
async def ticket_not_found_handler(
    request: Request,
    exc: TicketNotFoundException
):
    logger.warning(
        "Ticket not found: %s",
        str(exc)
    )

    return JSONResponse(
        status_code=404,
        content={"detail": str(exc)}
    )


@app.exception_handler(ValueError)
async def value_error_handler(
    request: Request,
    exc: ValueError
):
    logger.warning(
        "Validation error: %s",
        str(exc)
    )

    return JSONResponse(
        status_code=400,
        content={"detail": str(exc)}
    )


@app.get("/")
def root():
    logger.info("Root endpoint accessed")
    return FileResponse(Path(__file__).parent / "static" / "project.html")


@app.get("/tickets-ui")
def tickets_ui():
    return FileResponse(Path(__file__).parent / "static" / "tickets.html")


@app.get("/ai-assistant")
def ai_assistant_ui():
    return FileResponse(Path(__file__).parent / "static" / "ai-assistant.html")


@app.get("/health")
def health():
    return {"message": "IT Ticket Management System API is running"}
