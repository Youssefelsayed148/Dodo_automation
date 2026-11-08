import pytest

from .conftest import needs_db

pytestmark = needs_db


def test_job_runs_to_done_with_progress(session):
    from app.jobs import runner
    from app.models import Job

    job = runner.enqueue(session, "noop", {"steps": 4})
    seen = []
    orig = runner.JobContext.progress

    def spy(self, value, message=None, **kw):
        seen.append(value)
        return orig(self, value, message, **kw)

    runner.JobContext.progress = spy
    try:
        assert runner.run_pending_sync() == 1
    finally:
        runner.JobContext.progress = orig
    session.expire_all()
    j = session.get(Job, job.id)
    assert j.status == "done" and j.progress == 1.0 and j.result["steps"] == 4
    assert seen == [0.25, 0.5, 0.75, 1.0]


def test_failure_and_retry(session):
    from app.jobs import runner
    from app.models import Job

    job = runner.enqueue(session, "noop", {"fail": True})
    runner.run_pending_sync()
    session.expire_all()
    j = session.get(Job, job.id)
    assert j.status == "failed" and "requested failure" in j.error
    j.payload = {"steps": 1}
    session.commit()
    runner.retry(session, job.id)
    runner.run_pending_sync()
    session.expire_all()
    j = session.get(Job, job.id)
    assert j.status == "done" and j.error is None and j.attempts == 2
    with pytest.raises(ValueError):
        runner.retry(session, job.id)


def test_resume_after_restart(session):
    from app.jobs import runner
    from app.models import Job

    job = runner.enqueue(session, "noop", {"steps": 2})
    assert runner.claim_next() == job.id  # worker took it ... then the process "died"
    session.expire_all()
    assert session.get(Job, job.id).status == "running"
    assert runner.recover_interrupted() == 1
    runner.run_pending_sync()
    session.expire_all()
    assert session.get(Job, job.id).status == "done"


def test_cancel_queued(session):
    from app.jobs import runner
    from app.models import Job

    job = runner.enqueue(session, "noop")
    runner.cancel(session, job.id)
    assert runner.run_pending_sync() == 0
    session.expire_all()
    assert session.get(Job, job.id).status == "cancelled"


def test_unknown_job_type(session):
    from app.jobs import runner

    with pytest.raises(KeyError):
        runner.enqueue(session, "does_not_exist")


def test_settings_defaults_and_validation(session):
    from app.services import settings_service as ss

    vals = ss.get_all(session)
    assert vals["batch_size"] == 10 and vals["default_trim_size"] == "8.5x11in" and vals["default_language"] == "en"
    ss.set_many(session, {"batch_size": 5, "default_language": "ar"})
    assert ss.get(session, "batch_size") == 5
    with pytest.raises(ValueError):
        ss.set_many(session, {"batch_size": 7})
    with pytest.raises(ValueError):
        ss.set_many(session, {"nope": 1})


def test_usage_log_written(session):
    from app.models import UsageLog
    from app.providers.base import usage_context
    from app.providers.mock import MockImageProvider

    with usage_context(book_id=42, purpose="page"):
        MockImageProvider().generate("x", (64, 64))
    rows = session.query(UsageLog).all()
    assert len(rows) == 1 and rows[0].book_id == 42 and rows[0].kind == "image"


def test_migration_matches_models(session):
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from app.db import Base, get_engine

    with get_engine().connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == [], diff
