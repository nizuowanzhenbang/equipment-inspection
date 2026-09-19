"""为既有 SQLite/PostgreSQL 安全补齐点检唯一索引，不删除历史数据。"""
from sqlalchemy import func, select
from app.models.task import InspectionRecord


def ensure_record_uniqueness(engine):
    table = InspectionRecord.__table__
    index = next(i for i in table.indexes if i.name == 'uq_inspection_record_task_point')
    with engine.begin() as conn:
        duplicate = conn.execute(
            select(table.c.task_id, table.c.point_id)
            .group_by(table.c.task_id, table.c.point_id)
            .having(func.count() > 1).limit(1)
        ).first()
        if duplicate:
            raise RuntimeError(
                f'点检历史数据存在重复 task_id={duplicate.task_id}, point_id={duplicate.point_id}；'
                '请先备份并人工核对，系统不会自动删除记录。'
            )
        index.create(conn, checkfirst=True)
