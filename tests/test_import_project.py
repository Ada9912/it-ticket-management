from app.tools.import_project import summarise, validate


def payload():
    return {
        "project_name": "课程项目：图书管理系统",
        "source": "课程项目（个人独立完成）",
        "tasks": [
            {
                "title": "需求分析",
                "owner": "我",
                "due_date": "2025-01-01",
                "status": "DONE",
                "priority": "HIGH",
            },
            {
                "title": "接口设计",
                "owner": "我",
                "due_date": "2025-01-05",
                "status": "IN_PROGRESS",
                "priority": "MEDIUM",
                "depends_on": "需求分析",
            },
        ],
        "risks": [
            {
                "title": "测试环境不足",
                "owner": "我",
                "impact": "MEDIUM",
                "mitigation": "本地搭建",
                "status": "OPEN",
            },
        ],
    }


def test_valid_payload_has_no_problems():
    assert validate(payload()) == []


def test_duplicate_titles_are_rejected():
    data = payload()
    data["tasks"].append(dict(data["tasks"][0]))
    assert any("重复" in problem for problem in validate(data))


def test_dependency_cycle_is_rejected():
    data = payload()
    data["tasks"] = [
        {"title": "A", "owner": "我", "due_date": "2025-01-01", "depends_on": "B"},
        {"title": "B", "owner": "我", "due_date": "2025-01-02", "depends_on": "A"},
    ]
    assert any("环" in problem for problem in validate(data))


def test_advanced_task_with_unfinished_prerequisite_is_rejected():
    data = payload()
    data["tasks"][0]["status"] = "TODO"
    assert any("未完成" in problem for problem in validate(data))


def test_missing_owner_and_bad_date_are_rejected():
    data = payload()
    data["tasks"][0].pop("owner")
    data["tasks"][1]["due_date"] = "2025/01/05"
    problems = validate(data)
    assert any("owner" in problem for problem in problems)
    assert any("YYYY-MM-DD" in problem for problem in problems)


def test_summary_counts_come_from_the_payload():
    summary = summarise(payload())
    assert "任务 2 个" in summary
    assert "完成率：50%" in summary
    assert "风险 1 条" in summary
