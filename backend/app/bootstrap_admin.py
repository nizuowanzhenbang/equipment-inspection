"""Initialize the first administrator without fixed credentials or password resets."""
import argparse
import getpass
import re
import sys

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import hash_password
from app.database import SessionLocal, engine
from app.migrate import check_database
from app.models.audit import AuditLog
from app.models.user import User, UserRole


def bootstrap_admin(db, username: str, password: str) -> bool:
    """Caller supplies a fresh session in a migrated database; user/audit commit together."""
    if not re.fullmatch(r'[A-Za-z0-9_.-]{3,50}', username):
        raise ValueError('Username must contain 3-50 ASCII letters, digits, dots, hyphens or underscores')
    if len(password) < 12 or len(password.encode('utf-8')) > 72:
        raise ValueError('Password must have at least 12 characters and at most 72 UTF-8 bytes')
    dialect = db.get_bind().dialect.name
    if dialect == 'sqlite':
        db.execute(text('BEGIN IMMEDIATE'))
    elif dialect == 'postgresql':
        # Bootstrap callers must serialize even when the users table is empty.
        db.execute(text('SELECT pg_advisory_xact_lock(1789324101)'))
    else:
        raise ValueError('Bootstrap supports SQLite and PostgreSQL only')
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        if existing.role == UserRole.ADMIN and existing.is_active:
            db.rollback()
            return False
        raise ValueError('Existing account is not an active administrator; no changes made')
    if db.query(User).filter(User.role == UserRole.ADMIN).first():
        raise ValueError('An administrator already exists; bootstrap is not an account recovery command')
    user = User(username=username, full_name='系统管理员', role=UserRole.ADMIN,
                hashed_password=hash_password(password), is_active=True)
    db.add(user)
    db.flush()
    # Do not use best-effort audit helper: bootstrap must fail if audit cannot persist.
    db.add(AuditLog(actor='bootstrap-cli', action='user.bootstrap', target_type='User',
                    target_id=user.id, target_no=username, summary='Initialized administrator via local CLI'))
    db.commit()
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--username', required=True)
    parser.add_argument('--password-stdin', action='store_true', help='Read one password line from a protected pipe')
    args = parser.parse_args()
    try:
        check_database(engine)
        if args.password_stdin:
            password = sys.stdin.readline().rstrip('\r\n')
        else:
            if not sys.stdin.isatty():
                raise ValueError('Use an interactive terminal or --password-stdin')
            password = getpass.getpass('Administrator password: ')
            if password != getpass.getpass('Confirm password: '):
                raise ValueError('Passwords do not match')
        with SessionLocal() as db:
            try:
                created = bootstrap_admin(db, args.username, password)
            except Exception:
                db.rollback()
                raise
        print('Administrator created; audit recorded.' if created else 'Administrator already exists; unchanged.')
    except (ValueError, RuntimeError) as error:
        parser.exit(1, f'{error}\n')
    except SQLAlchemyError:
        # Database exceptions can include bound password hashes or connection details.
        parser.exit(1, 'Database initialization failed; account transaction rolled back.\n')
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
