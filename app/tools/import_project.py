"""Import a real project's task breakdown and risk register into the app database.

This tool exists so the project-coordination dashboard is not limited to the
demo seed data: you can load the actual division of work of a real
(or coursework) project and every number on the dashboard then comes from
that real data.

Usage
-----
    python -m app.tools.import_project data/input/my_project.json --dry-run
    python -m app.tools.import_project data/input/my_project.json --replace
    python -m app.tools.import_project data/input/my_project.json --replace --purge-demo

The input file is described in data/input/my_project.example.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

from app.db.database import SessionLocal
from app.db.models import ProjectRisk, ProjectTask, ProjectTaskEvent

TASK_STATUSES = {"TODO", "IN_PROGRESS", "DONE", "BLOCKED"}
TASK_PRIORITIES = {"HIGH", "MEDIUM", "LOW"}
RISK_STATUSES = {"OPEN", "MITIGATING", "CLOSED"}
DEMO_MARKERS = ("演示", "demo", "Demo", "DEMO")


def _text(value) -> str:
    return str(value).strip() if value is not None else ""


def validate(payload: dict) -> list[str]:
    """Return a list of human-readable problems. Empty list means valid."""
    problems: list[str] = []

    project = _text(payload.get("project_name"))
    if not project:
        problems.append("project_name 不能为空")

    tasks = payload.get("tasks") or []
    if not tasks:
        problems.append("tasks 不能为空：至少要有一个任务")

    titles = [_text(task.get("title")) for task in tasks if isinstance(task, dict)]
    duplicated = [title for title, count in Counter(titles).items() if count > 1 and title]
    if duplicated:
        problems.append(f"任务标题重复：{duplicated}（依赖用标题定位，标题必须唯一）")

    known_titles = set(titles)

    for index, task in enumerate(tasks, 1):
        if not isinstance(task, dict):
            problems.append(f"第 {index} 个任务不是对象")
            continue
        label = f"第 {index} 个任务（{_text(task.get('title')) or '<无标题>'}）"
        title = _text(task.get("title"))
        if not title:
            problems.append(f"{label} 缺少 title")
        if not _text(task.get("owner")):
            problems.append(f"{label} 缺少 owner（负责人，也就是分工）")
        status = _text(task.get("status")) or "TODO"
        if status not in TASK_STATUSES:
            problems.append(f"{label} status 必须是 {sorted(TASK_STATUSES)}")
        priority = _text(task.get("priority")) or "MEDIUM"
        if priority not in TASK_PRIORITIES:
            problems.append(f"{label} priority 必须是 {sorted(TASK_PRIORITIES)}")
        try:
            date.fromisoformat(_text(task.get("due_date")))
        except ValueError:
            problems.append(f"{label} due_date 必须是 YYYY-MM-DD")

        depends_on = _text(task.get("depends_on"))
        if depends_on:
            if depends_on == title:
                problems.append(f"{label} 不能依赖自己")
            elif depends_on not in known_titles:
                problems.append(f"{label} 的前置任务「{depends_on}」不存在")

    # Cycle detection: walk each dependency chain upwards.
    graph = {
        _text(task.get("title")): _text(task.get("depends_on"))
        for task in tasks
        if isinstance(task, dict) and _text(task.get("title"))
    }
    reported: set[str] = set()
    for start in graph:
        seen: set[str] = set()
        cursor = start
        while cursor in graph and graph[cursor]:
            cursor = graph[cursor]
            if cursor == start or cursor in seen:
                if start not in reported:
                    problems.append(f"依赖关系存在环，涉及任务：{start}")
                    reported.add(start)
                break
            seen.add(cursor)

    # A task that has advanced must have a finished prerequisite.
    by_title = {
        _text(task.get("title")): task
        for task in tasks
        if isinstance(task, dict) and _text(task.get("title"))
    }
    for task in tasks:
        if not isinstance(task, dict):
            continue
        depends_on = _text(task.get("depends_on"))
        status = _text(task.get("status")) or "TODO"
        if depends_on and status in {"IN_PROGRESS", "DONE"}:
            parent = by_title.get(depends_on)
            if parent is not None and (_text(parent.get("status")) or "TODO") != "DONE":
                problems.append(
                    f"「{_text(task.get('title'))}」已是 {status}，"
                    f"但前置「{depends_on}」未完成"
                )

    for index, risk in enumerate(payload.get("risks") or [], 1):
        if not isinstance(risk, dict):
            problems.append(f"第 {index} 条风险不是对象")
            continue
        label = f"第 {index} 条风险（{_text(risk.get('title')) or '<无标题>'}）"
        if not _text(risk.get("title")):
            problems.append(f"{label} 缺少 title")
        if not _text(risk.get("owner")):
            problems.append(f"{label} 缺少 owner（风险责任人）")
        impact = _text(risk.get("impact")) or "MEDIUM"
        if impact not in TASK_PRIORITIES:
            problems.append(f"{label} impact 必须是 {sorted(TASK_PRIORITIES)}")
        status = _text(risk.get("status")) or "OPEN"
        if status not in RISK_STATUSES:
            problems.append(f"{label} status 必须是 {sorted(RISK_STATUSES)}")

    return problems


def summarise(payload: dict) -> str:
    tasks = [task for task in payload.get("tasks") or [] if isinstance(task, dict)]
    risks = [risk for risk in payload.get("risks") or [] if isinstance(risk, dict)]
    today = date.today()

    by_status = Counter((_text(task.get("status")) or "TODO") for task in tasks)
    owners = {_text(task.get("owner")) for task in tasks if _text(task.get("owner"))}
    milestones = sum(1 for task in tasks if task.get("is_milestone"))
    edges = sum(1 for task in tasks if _text(task.get("depends_on")))
    overdue = 0
    for task in tasks:
        try:
            due = date.fromisoformat(_text(task.get("due_date")))
        except ValueError:
            continue
        if (_text(task.get("status")) or "TODO") != "DONE" and due < today:
            overdue += 1
    risk_status = Counter((_text(risk.get("status")) or "OPEN") for risk in risks)

    lines = [
        "",
        "=" * 58,
        f"项目：{_text(payload.get('project_name'))}",
        f"性质：{_text(payload.get('source')) or '未填写'}",
        "-" * 58,
        f"任务 {len(tasks)} 个：待办 {by_status['TODO']} / 进行中 {by_status['IN_PROGRESS']}"
        f" / 阻塞 {by_status['BLOCKED']} / 已完成 {by_status['DONE']}",
        f"里程碑 {milestones} 个；依赖关系 {edges} 条；逾期未完成 {overdue} 个",
        f"任务负责人 {len(owners)} 人：{'、'.join(sorted(owners)) or '—'}",
        f"风险 {len(risks)} 条：开放 {risk_status['OPEN']} / 缓解中 {risk_status['MITIGATING']}"
        f" / 已关闭 {risk_status['CLOSED']}",
        "=" * 58,
    ]
    completed = by_status["DONE"]
    if tasks:
        lines.append(f"完成率：{round(completed * 100 / len(tasks))}%")
    lines.append("以上数字全部来自你导入的真实数据，可以直接写进简历并被追问。")
    return "\n".join(lines)


def import_payload(payload: dict, replace: bool, purge_demo: bool) -> None:
    project = _text(payload["project_name"])
    db = SessionLocal()
    try:
        if purge_demo:
            demo_tasks = [
                task for task in db.query(ProjectTask).all()
                if any(marker in task.project_name for marker in DEMO_MARKERS)
            ]
            demo_ids = [task.id for task in demo_tasks]
            if demo_ids:
                db.query(ProjectTaskEvent).filter(
                    ProjectTaskEvent.task_id.in_(demo_ids)
                ).delete(synchronize_session=False)
                db.query(ProjectTask).filter(ProjectTask.id.in_(demo_ids)).delete(
                    synchronize_session=False
                )
            db.query(ProjectRisk).filter(
                ProjectRisk.project_name.like("%演示%")
            ).delete(synchronize_session=False)
            print(f"已清除演示数据：任务 {len(demo_tasks)} 条")

        if replace:
            existing = db.query(ProjectTask).filter(ProjectTask.project_name == project).all()
            existing_ids = [task.id for task in existing]
            if existing_ids:
                db.query(ProjectTaskEvent).filter(
                    ProjectTaskEvent.task_id.in_(existing_ids)
                ).delete(synchronize_session=False)
                db.query(ProjectTask).filter(ProjectTask.id.in_(existing_ids)).delete(
                    synchronize_session=False
                )
            db.query(ProjectRisk).filter(ProjectRisk.project_name == project).delete(
                synchronize_session=False
            )
            if existing_ids:
                print(f"已覆盖同名项目的旧数据：任务 {len(existing_ids)} 条")

        created: dict[str, ProjectTask] = {}
        for task in payload["tasks"]:
            record = ProjectTask(
                project_name=project,
                title=_text(task["title"]),
                description=_text(task.get("description")),
                owner=_text(task["owner"]),
                due_date=date.fromisoformat(_text(task["due_date"])),
                status=_text(task.get("status")) or "TODO",
                priority=_text(task.get("priority")) or "MEDIUM",
                is_milestone=1 if task.get("is_milestone") else 0,
            )
            db.add(record)
            created[record.title] = record
        db.flush()

        for task in payload["tasks"]:
            depends_on = _text(task.get("depends_on"))
            if depends_on:
                created[_text(task["title"])].depends_on_task_id = created[depends_on].id

        for risk in payload.get("risks") or []:
            db.add(
                ProjectRisk(
                    project_name=project,
                    title=_text(risk["title"]),
                    description=_text(risk.get("description")),
                    impact=_text(risk.get("impact")) or "MEDIUM",
                    owner=_text(risk["owner"]),
                    mitigation=_text(risk.get("mitigation")),
                    status=_text(risk.get("status")) or "OPEN",
                )
            )

        db.commit()
        print(f"已写入：任务 {len(payload['tasks'])} 条，风险 {len(payload.get('risks') or [])} 条")
        print("提示：变更历史从本次导入开始记录，之前的进展不会回填。")
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="把真实项目的任务分工与风险导入项目协作数据表"
    )
    parser.add_argument("source", type=Path, help="JSON 文件路径")
    parser.add_argument("--replace", action="store_true", help="覆盖同名项目的已有任务与风险")
    parser.add_argument("--purge-demo", action="store_true", help="先删除项目名包含「演示」的示例数据")
    parser.add_argument("--dry-run", action="store_true", help="只校验并打印统计，不写数据库")
    args = parser.parse_args()

    if not args.source.exists():
        print(f"找不到文件：{args.source}", file=sys.stderr)
        return 2

    payload = json.loads(args.source.read_text(encoding="utf-8"))
    problems = validate(payload)
    if problems:
        print("数据有问题，未写入：", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    print(summarise(payload))

    if args.dry_run:
        print("\n--dry-run：校验通过，未写入数据库。")
        return 0

    import_payload(payload, replace=args.replace, purge_demo=args.purge_demo)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
