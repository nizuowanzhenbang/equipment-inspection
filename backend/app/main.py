"""FastAPI 应用入口"""
from contextlib import asynccontextmanager
from datetime import datetime

import asyncio
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import engine, SessionLocal, Base

# 注册所有模型（建表用，顺序不可缺）
from app.models.user import User, UserRole
from app.models.equipment import Equipment
from app.models.route import InspectionRoute, InspectionPoint
from app.models.task import InspectionTask, InspectionRecord
from app.models.defect import Defect
from app.models.ticket import WorkTicket, OperationTicket, OperationTemplate
from app.models.spare_part import SparePart, StockMovement
from app.models.audit import AuditLog
from app.models.purchase_request import PurchaseRequest

from app.api import (
    auth, equipments, routes_api, tasks, defects, dashboard,
    scheduler_api, reports, uploads, work_tickets, operation_tickets, predictive,
    spare_parts, users, audit, purchase_requests,
)
from app.api.deps import hash_password
from app.record_schema import ensure_record_uniqueness
from app.scheduler import start_scheduler, shutdown_scheduler
from app.realtime import manager as ws_manager, ws_endpoint

_ = (User, Equipment, InspectionRoute, InspectionPoint, InspectionTask, InspectionRecord,
     Defect, WorkTicket, OperationTicket, OperationTemplate, SparePart, StockMovement, AuditLog,
     PurchaseRequest)


def _create_default_users(db) -> None:
    defaults = [
        ("admin",      "admin123",      UserRole.ADMIN,      "系统管理员"),
        ("inspector",  "inspector123",  UserRole.INSPECTOR,  "点检员"),
        ("repairman",  "repairman123",  UserRole.REPAIRMAN,  "维修工"),
        ("supervisor", "supervisor123", UserRole.SUPERVISOR, "设备主管"),
        ("viewer",     "viewer123",     UserRole.VIEWER,     "只读账户"),
    ]
    created = []
    for username, pwd, role, full in defaults:
        if db.query(User).filter(User.username == username).first():
            continue
        db.add(User(
            username=username, full_name=full,
            hashed_password=hash_password(pwd),
            role=role, is_active=True,
            created_at=datetime.utcnow(),
        ))
        created.append(username)
    if created:
        db.commit()
        print(f"[启动] 已创建默认账户：{', '.join(created)}")


def _auto_migrate(db) -> None:
    """SQLite 启动时 ALTER TABLE 补齐 v3.0 新增字段（生产环境请走 Alembic）"""
    if not settings.DATABASE_URL.startswith("sqlite"):
        return
    from sqlalchemy import text
    statements = [
        "ALTER TABLE work_tickets ADD COLUMN signatures JSON",
        "ALTER TABLE operation_tickets ADD COLUMN signatures JSON",
    ]
    for sql in statements:
        try:
            db.execute(text(sql))
            db.commit()
            print(f"[迁移] {sql}")
        except Exception:
            db.rollback()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    ensure_record_uniqueness(engine)
    db = SessionLocal()
    try:
        _auto_migrate(db)
        _create_default_users(db)
    finally:
        db.close()
    start_scheduler()
    drain_task = asyncio.create_task(ws_manager.drain_loop())
    print(f"[启动] {settings.APP_NAME} v{settings.APP_VERSION} 已就绪")
    yield
    drain_task.cancel()
    shutdown_scheduler()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="发电厂设备点检与缺陷管理：设备台账 + 点检路线 + 缺陷闭环",
    lifespan=lifespan,
)

allowed = settings.ALLOWED_ORIGINS or [
    "http://localhost:5173",
    "http://localhost:5174",
    "http://localhost:5175",
    "http://127.0.0.1:5175",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(equipments.router)
app.include_router(routes_api.router)
app.include_router(tasks.router)
app.include_router(defects.router)
app.include_router(dashboard.router)
app.include_router(scheduler_api.router)
app.include_router(reports.router)
app.include_router(uploads.router)
app.include_router(work_tickets.router)
app.include_router(operation_tickets.router)
app.include_router(predictive.router)
app.include_router(spare_parts.router)
app.include_router(users.router)
app.include_router(audit.router)
app.include_router(purchase_requests.router)


@app.websocket("/ws")
async def websocket_route(websocket: WebSocket):
    await ws_endpoint(websocket)


# 静态文件：上传目录
_upload_path = Path(settings.UPLOAD_DIR)
_upload_path.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(_upload_path)), name="uploads")


@app.get("/health", tags=["系统"])
def health():
    return {"status": "ok", "app": settings.APP_NAME, "version": settings.APP_VERSION}


@app.get("/", tags=["系统"])
def root():
    return {"message": f"欢迎使用 {settings.APP_NAME}", "docs": "/docs"}
