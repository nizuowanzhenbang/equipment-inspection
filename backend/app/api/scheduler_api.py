"""调度器查看/手动触发 API（ADMIN/SUPERVISOR 可用）"""
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import require_write
from app.models.user import User
from app.scheduler import list_jobs, trigger
from app.utils.helpers import api_response

router = APIRouter(prefix="/api/scheduler", tags=["定时调度"])


@router.get("/jobs")
def get_jobs(_: User = Depends(require_write)):
    return api_response(data=list_jobs())


@router.post("/run/{job_id}")
def run_job(job_id: str, _: User = Depends(require_write)):
    try:
        result = trigger(job_id)
    except KeyError:
        raise HTTPException(404, f"未知 job: {job_id}")
    return api_response(message=f"{job_id} 已触发", data=result)
