from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.job import JobPosting
from src.storage.database import JobRecord, QueryRecord, ScrapeRunRecord


class JobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def is_new_job(self, url: str, content_hash: str) -> bool:
        result = await self._session.execute(
            select(JobRecord)
            .where((JobRecord.url == url) | (JobRecord.content_hash == content_hash))
            .limit(1)
        )
        return result.scalar_one_or_none() is None

    async def store_jobs(self, jobs: list[JobPosting]) -> int:
        new_count = 0
        for job in jobs:
            existing = await self._session.execute(
                select(JobRecord).where(JobRecord.url == str(job.url)).limit(1)
            )
            if existing.scalar_one_or_none() is not None:
                continue
            record = JobRecord(
                url=str(job.url),
                title=job.title,
                company=job.company,
                location=job.location,
                category=job.category,
                date_posted=job.date_posted,
                description=job.description,
                salary=job.salary,
                content_hash=job.content_hash,
                match_score=job.match_score,
            )
            self._session.add(record)
            new_count += 1
        await self._session.commit()
        return new_count

    async def get_unnotified_jobs(self, threshold: float) -> list[JobRecord]:
        result = await self._session.execute(
            select(JobRecord)
            .where((JobRecord.match_score >= threshold) & (not JobRecord.notified))
            .order_by(JobRecord.match_score.desc())
        )
        return list(result.scalars().all())

    async def mark_notified(self, job_ids: list[int]) -> None:
        if not job_ids:
            return
        from sqlalchemy import update

        stmt = update(JobRecord).where(JobRecord.id.in_(job_ids)).values(notified=True)
        await self._session.execute(stmt)
        await self._session.commit()

    async def store_embedding(self, job_id: int, embedding: list[float]) -> None:
        from sqlalchemy import update

        stmt = update(JobRecord).where(JobRecord.id == job_id).values(embedding=embedding)
        await self._session.execute(stmt)
        await self._session.commit()

    async def get_all_jobs_with_embeddings(self) -> list[JobRecord]:
        result = await self._session.execute(
            select(JobRecord).where(JobRecord.embedding.isnot(None))
        )
        return list(result.scalars().all())

    async def get_queries(self) -> list[QueryRecord]:
        result = await self._session.execute(select(QueryRecord))
        return list(result.scalars().all())

    async def has_any_runs(self) -> bool:
        result = await self._session.execute(select(ScrapeRunRecord).limit(1))
        return result.scalar_one_or_none() is not None

    async def get_last_run_time(self) -> datetime | None:
        result = await self._session.execute(select(func.max(ScrapeRunRecord.finished_at)))
        return result.scalar()

    async def create_run(self) -> ScrapeRunRecord:
        run = ScrapeRunRecord(
            started_at=datetime.now(timezone.utc),
            status="running",
        )
        self._session.add(run)
        await self._session.commit()
        await self._session.refresh(run)
        return run

    async def finish_run(
        self, run_id: int, jobs_found: int, jobs_new: int, status: str = "completed"
    ) -> None:
        from sqlalchemy import update

        stmt = (
            update(ScrapeRunRecord)
            .where(ScrapeRunRecord.id == run_id)
            .values(
                finished_at=datetime.now(timezone.utc),
                jobs_found=jobs_found,
                jobs_new=jobs_new,
                status=status,
            )
        )
        await self._session.execute(stmt)
        await self._session.commit()
