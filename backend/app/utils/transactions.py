"""Serialize equipment changes before inserting defects or deciding recovery."""
from sqlalchemy.orm import Session

from app.models.equipment import Equipment


def lock_equipment(db: Session, equipment_id: int) -> Equipment | None:
    """Call before mutating equipment ORM fields; refreshing discards cached values."""
    # UPDATE also works on SQLite; PostgreSQL holds the row lock until transaction end.
    # Acquire before defect INSERT to avoid upgrading foreign-key locks concurrently.
    db.query(Equipment).filter(Equipment.id == equipment_id).update(
        {Equipment.updated_at: Equipment.updated_at}, synchronize_session=False,
    )
    # A joined read may already have cached an older score/status before the wait.
    return db.query(Equipment).filter(Equipment.id == equipment_id).populate_existing().first()
