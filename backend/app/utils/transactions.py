"""Serialize shared equipment and inventory mutations inside their transaction."""
from sqlalchemy.orm import Session

from app.models.equipment import Equipment
from app.models.spare_part import SparePart


def lock_equipment(db: Session, equipment_id: int) -> Equipment | None:
    """Call before mutating equipment ORM fields; refreshing discards cached values."""
    # UPDATE also works on SQLite; PostgreSQL holds the row lock until transaction end.
    # Acquire before defect INSERT to avoid upgrading foreign-key locks concurrently.
    db.query(Equipment).filter(Equipment.id == equipment_id).update(
        {Equipment.updated_at: Equipment.updated_at}, synchronize_session=False,
    )
    # A joined read may already have cached an older score/status before the wait.
    return db.query(Equipment).filter(Equipment.id == equipment_id).populate_existing().first()


def lock_spare_part(db: Session, spare_part_id: int) -> SparePart | None:
    """Lock before stock/ledger changes and reload values cached before the wait."""
    # A no-op UPDATE locks the row on PostgreSQL and the writer on SQLite.
    # Acquire before inserting a referencing movement to avoid FK lock upgrades.
    db.query(SparePart).filter(SparePart.id == spare_part_id).update(
        {SparePart.updated_at: SparePart.updated_at}, synchronize_session=False,
    )
    return db.query(SparePart).filter(SparePart.id == spare_part_id).populate_existing().first()
