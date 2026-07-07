"""内置定时任务（APScheduler）

注册四个 job：
1. sweep_overdue_defects     —— 缺陷超期扫描
2. sweep_missed_tasks         —— 漏检任务扫描
3. auto_generate_tasks        —— 按路线 frequency 自动生成下一次点检任务
4. retry_safety_sync          —— 重试 plant-safety 联动
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models.defect import Defect, DefectStatus
from app.models.route import InspectionRoute, RouteFrequency
from app.models.task import InspectionTask, TaskStatus
from app.models.spare_part import SparePart
from app.models.purchase_request import PurchaseRequest, PRStatus, PRSource
from app.utils.helpers import generate_task_no, generate_pr_no
from app.integration.safety_client import retry_pending
from app.realtime import emit_overdue_swept, emit_missed_swept

logger = logging.getLogger("equipment_inspection.scheduler")

_scheduler: Optional[BackgroundScheduler] = None
_last_run: dict[str, dict] = {}   # job_id -> {"at": iso, "result": dict|str}


def _record(job_id: str, result) -> None:
    _last_run[job_id] = {
        "at": datetime.utcnow().isoformat(),
        "result": result,
    }


# ---- 频率 → 间隔 ----
_FREQ_INTERVAL = {
    RouteFrequency.SHIFT: timedelta(hours=8),
    RouteFrequency.DAILY: timedelta(days=1),
    RouteFrequency.WEEKLY: timedelta(weeks=1),
    RouteFrequency.MONTHLY: timedelta(days=30),
}


def _with_db(fn):
    """job 包装：自动开关 session、捕获异常。"""
    def wrapper():
        db: Session = SessionLocal()
        try:
            result = fn(db)
            _record(fn.__name__, result)
            return result
        except Exception as e:  # noqa: BLE001
            logger.exception("[scheduler] %s 失败: %s", fn.__name__, e)
            _record(fn.__name__, f"ERROR: {type(e).__name__}: {e}")
        finally:
            db.close()
    wrapper.__name__ = fn.__name__
    return wrapper


@_with_db
def sweep_overdue_defects(db: Session) -> dict:
    now = datetime.utcnow()
    rows = (
        db.query(Defect)
        .filter(
            Defect.sla_deadline.isnot(None),
            Defect.sla_deadline < now,
            Defect.status.in_([DefectStatus.NEW, DefectStatus.ASSIGNED, DefectStatus.IN_REPAIR]),
        )
        .all()
    )
    nos = []
    for d in rows:
        d.status = DefectStatus.OVERDUE
        nos.append(d.defect_no)
    db.commit()
    emit_overdue_swept(len(rows), nos)
    return {"overdue": len(rows)}


@_with_db
def sweep_missed_tasks(db: Session) -> dict:
    cutoff = datetime.utcnow() - timedelta(hours=settings.TASK_MISSED_AFTER_HOURS)
    rows = (
        db.query(InspectionTask)
        .filter(
            InspectionTask.status.in_([TaskStatus.PENDING, TaskStatus.IN_PROGRESS]),
            InspectionTask.scheduled_at < cutoff,
        )
        .all()
    )
    nos = []
    for t in rows:
        t.status = TaskStatus.MISSED
        nos.append(t.task_no)
    db.commit()
    emit_missed_swept(len(rows), nos)
    return {"missed": len(rows)}


@_with_db
def auto_generate_tasks(db: Session) -> dict:
    """对每条启用的路线，判断"距上次任务是否已超过 frequency 间隔"，是则生成下一条。"""
    now = datetime.utcnow()
    routes = db.query(InspectionRoute).filter(InspectionRoute.is_active.is_(True)).all()
    created: list[str] = []
    for r in routes:
        interval = _FREQ_INTERVAL.get(r.frequency, timedelta(days=1))
        last = (
            db.query(InspectionTask)
            .filter(InspectionTask.route_id == r.id)
            .order_by(InspectionTask.scheduled_at.desc())
            .first()
        )
        # 没有任何任务，或上次计划时间 + 间隔 ≤ now → 生成下一次
        if last is None:
            next_scheduled = now
        elif last.scheduled_at + interval <= now:
            next_scheduled = last.scheduled_at + interval
            # 防止积压一年——一次最多前补 1 个周期
            if next_scheduled + interval <= now:
                next_scheduled = now
        else:
            continue

        next_seq = (
            db.query(func.count(InspectionTask.id))
            .filter(func.date(InspectionTask.created_at) == now.date())
            .scalar() or 0
        ) + 1
        task = InspectionTask(
            task_no=generate_task_no(next_seq),
            route_id=r.id,
            scheduled_at=next_scheduled,
            status=TaskStatus.PENDING,
        )
        db.add(task)
        db.flush()
        created.append(task.task_no)
    db.commit()
    return {"created": created, "total": len(created)}


@_with_db
def retry_safety_sync(db: Session) -> dict:
    return retry_pending(db, limit=50)


@_with_db
def auto_generate_purchase_requests(db: Session) -> dict:
    """扫描低库存备件，为没有 in-flight 申请的自动建草稿（每日一次）"""
    in_flight = (PRStatus.DRAFT, PRStatus.SUBMITTED, PRStatus.APPROVED, PRStatus.SENT)
    candidates = db.query(SparePart).filter(SparePart.stock_qty < SparePart.min_qty).all()
    today = datetime.utcnow().date()
    next_seq = (
        db.query(func.count(PurchaseRequest.id))
        .filter(func.date(PurchaseRequest.created_at) == today)
        .scalar() or 0
    )
    created: list[str] = []
    for sp in candidates:
        exists = (
            db.query(PurchaseRequest)
            .filter(PurchaseRequest.spare_part_id == sp.id, PurchaseRequest.status.in_(in_flight))
            .first()
        )
        if exists:
            continue
        next_seq += 1
        suggested_qty = max(float(sp.min_qty or 0) * 2 - float(sp.stock_qty or 0), float(sp.min_qty or 0))
        pr = PurchaseRequest(
            pr_no=generate_pr_no(next_seq),
            spare_part_id=sp.id,
            qty=suggested_qty,
            estimated_amount=suggested_qty * float(sp.unit_price or 0),
            urgency="URGENT" if float(sp.stock_qty or 0) <= 0 else "NORMAL",
            reason=f"低库存自动触发：当前 {sp.stock_qty}，安全 {sp.min_qty}",
            source=PRSource.AUTO_LOW_STOCK,
            status=PRStatus.SUBMITTED,
            applicant="scheduler",
            submitted_at=datetime.utcnow(),
        )
        db.add(pr)
        created.append(pr.pr_no)
    db.commit()
    return {"created": created, "total": len(created)}


def start_scheduler() -> None:
    global _scheduler
    if not settings.SCHEDULER_ENABLED:
        logger.info("[scheduler] SCHEDULER_ENABLED=False 跳过启动")
        return
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    _scheduler.add_job(
        sweep_overdue_defects, "interval",
        minutes=settings.SCHEDULER_OVERDUE_SWEEP_MINUTES,
        id="sweep_overdue_defects", replace_existing=True,
    )
    _scheduler.add_job(
        sweep_missed_tasks, "interval",
        minutes=settings.SCHEDULER_MISSED_SWEEP_MINUTES,
        id="sweep_missed_tasks", replace_existing=True,
    )
    _scheduler.add_job(
        auto_generate_tasks, "interval",
        minutes=settings.SCHEDULER_TASK_GEN_MINUTES,
        id="auto_generate_tasks", replace_existing=True,
    )
    _scheduler.add_job(
        retry_safety_sync, "interval",
        minutes=settings.SCHEDULER_INTEGRATION_RETRY_MINUTES,
        id="retry_safety_sync", replace_existing=True,
    )
    _scheduler.add_job(
        auto_generate_purchase_requests, "interval",
        hours=settings.SCHEDULER_PR_AUTO_HOURS,
        id="auto_generate_purchase_requests", replace_existing=True,
    )
    _scheduler.start()
    logger.info("[scheduler] 已启动，注册 5 个 job")


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("[scheduler] 已关闭")


def list_jobs() -> list[dict]:
    if _scheduler is None:
        return []
    out = []
    for job in _scheduler.get_jobs():
        last = _last_run.get(job.id, {})
        out.append({
            "id": job.id,
            "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            "trigger": str(job.trigger),
            "last_run_at": last.get("at"),
            "last_result": last.get("result"),
        })
    return out


# 手动触发：用于 API /api/scheduler/run/{job_id}
_JOBS = {
    "sweep_overdue_defects": sweep_overdue_defects,
    "sweep_missed_tasks": sweep_missed_tasks,
    "auto_generate_tasks": auto_generate_tasks,
    "retry_safety_sync": retry_safety_sync,
    "auto_generate_purchase_requests": auto_generate_purchase_requests,
}


def trigger(job_id: str) -> dict:
    fn = _JOBS.get(job_id)
    if not fn:
        raise KeyError(job_id)
    fn()
    return _last_run.get(job_id, {})
