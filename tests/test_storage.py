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
