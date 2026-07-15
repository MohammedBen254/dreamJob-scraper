from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from structlog import get_logger

from src.models.job import JobPosting
from src.storage.database import JobRecord, JobMatch, QueryRecord, ScrapeRunRecord

logger = get_logger()


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

    async def get_job_by_url(self, url: str) -> JobRecord | None:
        result = await self._session.execute(select(JobRecord).where(JobRecord.url == url).limit(1))
        return result.scalar_one_or_none()

    async def store_jobs(self, jobs: list[JobPosting]) -> int:
        new_count = 0
        dup_count = 0
        for job in jobs:
            existing = await self._session.execute(
                select(JobRecord).where(JobRecord.url == str(job.url)).limit(1)
            )
            if existing.scalar_one_or_none() is not None:
                dup_count += 1
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
        logger.info("store_jobs_done", total=len(jobs), new=new_count, duplicates=dup_count)
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

        logger.info("store_embedding", job_id=job_id, dim=len(embedding))
        stmt = update(JobRecord).where(JobRecord.id == job_id).values(embedding=embedding)
        await self._session.execute(stmt)
        await self._session.commit()

    async def get_all_jobs_with_embeddings(self) -> list[JobRecord]:
        result = await self._session.execute(
            select(JobRecord).where(JobRecord.embedding.isnot(None))
        )
        jobs = list(result.scalars().all())
        logger.info("get_jobs_with_embeddings", count=len(jobs))
        return jobs

    async def get_queries(self) -> list[QueryRecord]:
        result = await self._session.execute(select(QueryRecord))
        return list(result.scalars().all())

    async def seed_queries(self, queries: list[dict]) -> None:
        existing = await self.get_queries()
        existing_names = {q.name for q in existing}
        added = 0
        for q in queries:
            if q["name"] not in existing_names:
                self._session.add(QueryRecord(name=q["name"], query_text=q["query"]))
                added += 1
        await self._session.commit()
        logger.info(
            "seed_queries_done",
            total=len(queries),
            added=added,
            already_existing=len(queries) - added,
        )

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
        logger.info("scrape_run_created", run_id=run.id)
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
        logger.info(
            "scrape_run_finished",
            run_id=run_id,
            jobs_found=jobs_found,
            jobs_new=jobs_new,
            status=status,
        )

    async def store_job(self, job: JobPosting, scrape_run_id: int) -> JobRecord | None:
        existing = await self._session.execute(
            select(JobRecord).where(JobRecord.url == str(job.url)).limit(1)
        )
        if existing.scalar_one_or_none() is not None:
            logger.debug("job_already_exists", url=str(job.url))
            return None
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
            status="parsed",
            scrape_run_id=scrape_run_id,
            ocr_results=job.ocr_results,
        )
        self._session.add(record)
        await self._session.commit()
        await self._session.refresh(record)
        logger.info("job_stored", job_id=record.id, url=str(job.url), run_id=scrape_run_id)
        return record

    async def update_job_status(self, job_ids: list[int], status: str) -> None:
        if not job_ids:
            return
        from sqlalchemy import update

        stmt = update(JobRecord).where(JobRecord.id.in_(job_ids)).values(status=status)
        await self._session.execute(stmt)
        await self._session.commit()
        logger.info("jobs_status_updated", count=len(job_ids), status=status)

    async def get_jobs_by_status(self, status: str) -> list[JobRecord]:
        result = await self._session.execute(select(JobRecord).where(JobRecord.status == status))
        return list(result.scalars().all())

    async def update_run_categories(self, run_id: int, categories: dict) -> None:
        from sqlalchemy import update

        stmt = (
            update(ScrapeRunRecord)
            .where(ScrapeRunRecord.id == run_id)
            .values(categories=categories)
        )
        await self._session.execute(stmt)
        await self._session.commit()

    async def increment_run_counter(self, run_id: int, field: str, amount: int = 1) -> None:
        from sqlalchemy import update

        column = getattr(ScrapeRunRecord, field)
        stmt = (
            update(ScrapeRunRecord)
            .where(ScrapeRunRecord.id == run_id)
            .values({column: column + amount})
        )
        await self._session.execute(stmt)
        await self._session.commit()

    async def add_run_error(self, run_id: int, url: str, error: str) -> None:
        from sqlalchemy import select, update

        result = await self._session.execute(
            select(ScrapeRunRecord).where(ScrapeRunRecord.id == run_id)
        )
        run = result.scalar_one()
        errors = run.errors or []
        errors.append({"url": url, "error": error})
        stmt = update(ScrapeRunRecord).where(ScrapeRunRecord.id == run_id).values(errors=errors)
        await self._session.execute(stmt)
        await self._session.commit()

    async def store_match(self, job_id: int, query_id: int, score: float) -> JobMatch:
        existing = await self._session.execute(
            select(JobMatch).where((JobMatch.job_id == job_id) & (JobMatch.query_id == query_id))
        )
        match = existing.scalar_one_or_none()
        if match:
            match.score = score
            await self._session.commit()
            return match
        match = JobMatch(job_id=job_id, query_id=query_id, score=score)
        self._session.add(match)
        await self._session.commit()
        await self._session.refresh(match)
        return match

    async def get_matches_for_query(self, query_id: int, threshold: float = 0.0) -> list[JobMatch]:
        result = await self._session.execute(
            select(JobMatch)
            .where((JobMatch.query_id == query_id) & (JobMatch.score >= threshold))
            .order_by(JobMatch.score.desc())
        )
        return list(result.scalars().all())

    async def get_matches_for_job(self, job_id: int) -> list[JobMatch]:
        result = await self._session.execute(
            select(JobMatch).where(JobMatch.job_id == job_id).order_by(JobMatch.score.desc())
        )
        return list(result.scalars().all())
