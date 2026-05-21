"""应用配置"""
from typing import List, Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./equipment_inspection.db"
    SECRET_KEY: str = "equipment-inspection-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24
    APP_NAME: str = "发电厂设备点检与缺陷管理系统"
    APP_VERSION: str = "2.5.0"
    DEBUG: bool = False
    ALLOWED_ORIGINS: Optional[List[str]] = None

    # 缺陷处理时限（小时），超期自动 OVERDUE
    DEFECT_SLA_MINOR: int = 72       # 一般缺陷 3 天
    DEFECT_SLA_MAJOR: int = 24       # 重要缺陷 1 天
    DEFECT_SLA_CRITICAL: int = 4     # 紧急缺陷 4 小时

    # 点检任务超期阈值（小时），过了计划时间多久仍未完成视为 MISSED
    TASK_MISSED_AFTER_HOURS: int = 12

    # 与 plant-safety 集成（v2 启用）
    SAFETY_SYSTEM_URL: str = ""    # 形如 http://localhost:8002，留空则跳过推送
    INTEGRATION_SECRET: str = "coal-integration-shared-secret"
    INTEGRATION_TIMEOUT_SEC: int = 5

    # 上传存储（v2.1）
    UPLOAD_DIR: str = "uploads"           # 相对项目根的本地目录
    UPLOAD_MAX_MB: int = 5

    # 内置调度器（v2 启用）
    SCHEDULER_ENABLED: bool = True
    SCHEDULER_OVERDUE_SWEEP_MINUTES: int = 10   # 缺陷超期扫描间隔
    SCHEDULER_MISSED_SWEEP_MINUTES: int = 30    # 漏检扫描间隔
    SCHEDULER_TASK_GEN_MINUTES: int = 60        # 任务自动生成检查间隔
    SCHEDULER_INTEGRATION_RETRY_MINUTES: int = 5  # plant-safety 推送重试

    model_config = {"env_file": ".env", "case_sensitive": True}


settings = Settings()
