from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import AIFeedback

router = APIRouter(prefix="/ai", tags=["AI Product Prototype"])

# Local, illustrative knowledge articles. This prototype uses transparent
# keyword matching; it does not call an LLM or an external knowledge service.
ARTICLES = [
    {"id": "KB-NET-01", "title": "办公 Wi-Fi / VPN 连接排查", "category": "Network", "keywords": ["wifi", "wi-fi", "无线", "网络", "vpn", "连接", "断网", "dns"], "steps": ["确认是否仅单个设备受影响", "检查 VPN 客户端与网络配置", "记录错误时间、网络位置和错误码", "仍无法恢复时转网络支持组"]},
    {"id": "KB-ACC-02", "title": "账号登录与访问权限申请", "category": "Access", "keywords": ["登录", "账号", "账户", "权限", "访问", "密码", "mfa", "二次验证"], "steps": ["确认员工账号及目标系统", "核对是否已完成多因素验证", "权限申请需由直属主管审批", "账号锁定转身份与权限支持组"]},
    {"id": "KB-SW-03", "title": "企业软件故障基础排查", "category": "Software", "keywords": ["软件", "应用", "崩溃", "报错", "打不开", "安装", "office", "浏览器"], "steps": ["记录软件名称、版本和错误截图", "重启应用并检查更新", "确认是否影响多个用户", "持续报错时转应用支持组"]},
    {"id": "KB-HW-04", "title": "电脑与外设故障检查", "category": "Hardware", "keywords": ["电脑", "笔记本", "屏幕", "键盘", "鼠标", "打印机", "硬件", "laptop"], "steps": ["确认设备资产编号及使用位置", "检查电源、线缆和外设连接", "记录故障现象及是否可复现", "设备无法使用时转桌面支持组"]},
]


class TriageRequest(BaseModel):
    issue_text: str = Field(min_length=4, max_length=2000)


class FeedbackRequest(BaseModel):
    issue_text: str = Field(min_length=4, max_length=2000)
    suggested_category: str = Field(min_length=1, max_length=50)
    selected_action: str


@router.post("/triage")
def triage_issue(request: TriageRequest):
    text = request.issue_text.casefold()
    scores = {
        article["category"]: sum(keyword.casefold() in text for keyword in article["keywords"])
        for article in ARTICLES
    }
    category = max(scores, key=scores.get)
    matched = scores[category]
    if matched == 0:
        category = "Other"
        sources = []
        confidence = 0.35
        rationale = "未命中分类关键词，建议由服务台人工分诊。"
    else:
        sources = [article for article in ARTICLES if article["category"] == category]
        confidence = min(0.55 + 0.12 * matched, 0.91)
        rationale = f"描述中命中 {matched} 个与 {category} 类别相关的关键词；建议人工确认分类。"

    high_signals = ["全员", "全部用户", "很多同事", "很多人", "生产中断", "无法办公", "安全事件", "数据泄露", "宕机"]
    low_signals = ["咨询", "如何", "使用方法", "建议"]
    if any(signal in text for signal in high_signals):
        priority, priority_reason = "HIGH", "描述中出现较大范围影响或安全相关信号，请人工核实影响范围。"
    elif any(signal in text for signal in low_signals):
        priority, priority_reason = "LOW", "描述更接近咨询类请求，建议确认是否影响日常工作。"
    else:
        priority, priority_reason = "MEDIUM", "按一般影响范围建议为中优先级，请人工确认。"

    teams = {"Network": "网络支持组", "Access": "身份与权限组", "Software": "应用支持组", "Hardware": "桌面支持组", "Other": "服务台人工分诊"}
    return {
        "category": category,
        "priority": priority,
        "suggested_team": teams[category],
        "confidence": confidence,
        "rationale": rationale,
        "priority_rationale": priority_reason,
        "method": "本地规则 + 关键词匹配原型，不调用大模型",
        "human_review_required": True,
        "knowledge_articles": [
            {"id": article["id"], "title": article["title"], "steps": article["steps"]}
            for article in sources
        ],
    }


@router.post("/feedback")
def record_feedback(request: FeedbackRequest, db: Session = Depends(get_db)):
    if request.selected_action not in {"ACCEPTED", "EDITED", "REJECTED"}:
        raise HTTPException(422, "selected_action must be ACCEPTED, EDITED, or REJECTED")
    record = AIFeedback(**request.model_dump())
    db.add(record)
    db.commit()
    return {"recorded": True, "feedback_id": record.id}


@router.get("/metrics")
def feedback_metrics(db: Session = Depends(get_db)):
    rows = dict(db.query(AIFeedback.selected_action, func.count(AIFeedback.id)).group_by(AIFeedback.selected_action).all())
    total = sum(rows.values())
    return {
        "total_feedback": total,
        "accepted": rows.get("ACCEPTED", 0),
        "edited": rows.get("EDITED", 0),
        "rejected": rows.get("REJECTED", 0),
        "acceptance_rate": round(rows.get("ACCEPTED", 0) / total * 100) if total else 0,
        "note": "仅统计本地原型中的人工反馈，不能代表模型准确率或生产效果。",
    }
