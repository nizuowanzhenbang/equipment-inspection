# PostgreSQL Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Verify inspection writes on PostgreSQL and prevent duplicate defect numbers and lost inspection health deductions.

**Architecture:** Keep the existing API and transaction boundary. Replace runtime count-based defect numbers with UUID-backed numbers and perform inspection health deduction in the database. Use isolated PostgreSQL schemas for API regression tests.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2, pytest, PostgreSQL 16, SQLite, GitHub Actions.

**Spec:** docs/superpowers/specs/2026-09-21-postgresql-reliability.md

## Global Constraints

- No new application tables or rewriting existing rows.
- Runtime defect numbers remain within the existing 50-character column.
- Explicit sequence arguments for seed data remain supported.
- PostgreSQL tests use TEST_POSTGRESQL_URL and exclusively clean their generated schema.
- User mastery is not an acceptance gate.

## Review Focus

- Health 0 must not become 97: parameterized SQLite and PostgreSQL boundary cases.
- Two requests with old equipment snapshots must both deduct: synchronize real inserts in PostgreSQL.
- Manual and inspection writes must not allocate the same number: mixed-source concurrent requests.
- A failed defect insert must roll back its inspection record: real database CHECK failure then successful retry.
- An existing duplicated record must survive rejected index initialization: duplicate-data PostgreSQL test.

## Task 1: Database regressions and minimal fixes

**Files:**
- Modify: backend/tests/test_record_replay.py
- Create: backend/tests/postgresql/conftest.py
- Create: backend/tests/postgresql/test_inspection_transactions.py
- Modify: backend/app/utils/helpers.py
- Modify: backend/app/api/tasks.py
- Modify: backend/app/api/defects.py

**Interfaces:** Existing record/defect API request and response bodies remain unchanged. generate_defect_no(seq: int | None = None) retains explicit-sequence seed behavior.

- [ ] Add real API tests for health bounds, legacy-number collision, concurrent replay/conflict, shared-equipment deductions, mixed-source numbering, rollback, and index initialization.
- [ ] Run against baseline. Expected: boundary and concurrent distinct-write tests fail; baseline replay contract stays passing. Record the actual failures.
- [ ] Change number generation and both API allocation callers:

```python
def generate_defect_no(seq: int | None = None) -> str:
    suffix = f"{seq:04d}" if seq is not None else uuid4().hex
    return f"DF-{datetime.now().strftime('%Y%m%d')}-{suffix}"
```

- [ ] Replace the inspection ORM read/modify/write health assignment with:

```python
score = func.coalesce(Equipment.health_score, 100)
db.query(Equipment).filter(Equipment.id == eq.id).update(
    {Equipment.health_score: case((score >= decay, score - decay), else_=0)},
    synchronize_session=False,
)
```

- [ ] Run full backend suite with PostgreSQL URL configured. Expected: all SQLite and PostgreSQL regressions pass.
- [ ] Commit the tested change.

## Task 2: Repeatable CI and technical handoff

**Files:**
- Create: backend/requirements-postgres.txt
- Modify: .github/workflows/quality.yml
- Modify: docs/INTERVIEW.md, docs/MAINTENANCE.md, README.md
- Create: docs/POSTGRESQL.md

**Interfaces:** The PostgreSQL fixture consumes TEST_POSTGRESQL_URL; CI provides an ephemeral PostgreSQL 16 service, runs the integration directory, and uploads JUnit results.

- [ ] Put psycopg2-binary>=2.9,<3 in the optional PostgreSQL requirements file.
- [ ] Add a CI service with a health check, a fixed job timeout, isolated test credentials, and the command `cd backend && python -m pytest tests/postgresql -q --junitxml=postgresql-results.xml`.
- [ ] Document schema isolation, actual tests and limits, new number format, and how to run locally.
- [ ] Run backend lint/full tests, frontend tests/build, and the isolated interview demo. Expected: all pass; retain warnings separately.
- [ ] Obtain an independent whole-branch review and address important findings with regression tests.
- [ ] Push the feature branch, create a draft PR, and verify GitHub Actions for its latest commit. Do not merge as part of this slice.
