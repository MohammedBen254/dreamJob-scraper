import pytest

from src.models.job import JobPosting
from src.storage.database import Base, async_session_factory, engine
from src.storage.repository import JobRepository
from pydantic import HttpUrl


@pytest.fixture(autouse=True)
async def setup_database():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


def _job(url: str = "https://www.dreamjob.ma/emploi/test/", title: str = "Test") -> JobPosting:
    j = JobPosting(title=title, url=HttpUrl(url))
    j.compute_hash()
    return j


class TestStoreAndDedup:
    async def test_store_new_job(self):
        async with async_session_factory() as session:
            repo = JobRepository(session)
            job = _job()
            count = await repo.store_jobs([job])
            assert count == 1

    async def test_duplicate_url_not_stored(self):
        async with async_session_factory() as session:
            repo = JobRepository(session)
            job = _job()
            await repo.store_jobs([job])
            count = await repo.store_jobs([job])
            assert count == 0


class TestGetUnnotified:
    async def test_filters_by_threshold(self):
        async with async_session_factory() as session:
            repo = JobRepository(session)
            j1 = _job("https://www.dreamjob.ma/emploi/a/", "High Score")
            j1.match_score = 80
            j2 = _job("https://www.dreamjob.ma/emploi/b/", "Low Score")
            j2.match_score = 30
            await repo.store_jobs([j1, j2])

            from sqlalchemy import update
            from src.storage.database import JobRecord

            stmt = update(JobRecord).where(JobRecord.title == "High Score").values(match_score=80)
            await session.execute(stmt)
            await session.commit()

            results = await repo.get_unnotified_jobs(threshold=50)
            titles = [r.title for r in results]
            assert "High Score" in titles
            assert "Low Score" not in titles


class TestMarkNotified:
    async def test_mark_notified_updates_flag(self):
        async with async_session_factory() as session:
            repo = JobRepository(session)
            job = _job()
            await repo.store_jobs([job])

            from sqlalchemy import select
            from src.storage.database import JobRecord

            result = await session.execute(select(JobRecord).limit(1))
            record = result.scalar_one()

            await repo.mark_notified([record.id])
            await session.refresh(record)
            assert record.notified is True


class TestStoreJob:
    async def test_store_single_job_with_run(self):
        async with async_session_factory() as session:
            repo = JobRepository(session)
            run = await repo.create_run()
            job = _job()
            record = await repo.store_job(job, run.id)
            assert record is not None
            assert record.status == "parsed"
            assert record.scrape_run_id == run.id

    async def test_store_duplicate_returns_none(self):
        async with async_session_factory() as session:
            repo = JobRepository(session)
            run = await repo.create_run()
            job = _job()
            await repo.store_job(job, run.id)
            result = await repo.store_job(job, run.id)
            assert result is None


class TestJobStatus:
    async def test_update_job_status(self):
        async with async_session_factory() as session:
            repo = JobRepository(session)
            run = await repo.create_run()
            job = _job()
            record = await repo.store_job(job, run.id)
            await repo.update_job_status([record.id], "embedded")
            embedded = await repo.get_jobs_by_status("embedded")
            assert len(embedded) == 1
            assert embedded[0].id == record.id

    async def test_get_jobs_by_status_filters(self):
        async with async_session_factory() as session:
            repo = JobRepository(session)
            run = await repo.create_run()
            j1 = _job("https://www.dreamjob.ma/emploi/a/", "A")
            j2 = _job("https://www.dreamjob.ma/emploi/b/", "B")
            r1 = await repo.store_job(j1, run.id)
            r2 = await repo.store_job(j2, run.id)
            await repo.update_job_status([r1.id], "embedded")
            parsed = await repo.get_jobs_by_status("parsed")
            assert len(parsed) == 1
            assert parsed[0].id == r2.id


class TestRunCategories:
    async def test_update_run_categories(self):
        async with async_session_factory() as session:
            repo = JobRepository(session)
            run = await repo.create_run()
            cats = {"emploi": {"pages": 2, "found": 30, "parsed": 28}}
            await repo.update_run_categories(run.id, cats)
            from sqlalchemy import select
            from src.storage.database import ScrapeRunRecord

            result = await session.execute(
                select(ScrapeRunRecord).where(ScrapeRunRecord.id == run.id)
            )
            updated = result.scalar_one()
            assert updated.categories == cats
