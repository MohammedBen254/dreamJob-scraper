from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from src.storage.database import async_session_factory
from src.storage.repository import JobRepository

app = FastAPI(title="DreamJob Scraper")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    async with async_session_factory() as session:
        repo = JobRepository(session)
        queries = await repo.get_queries()
        last_run = await repo.get_last_run_time()
        total_jobs = len(await repo.get_all_jobs_with_embeddings())

        from sqlalchemy import select, func
        from src.storage.database import JobRecord as JR, ScrapeRunRecord

        parsed_count = (
            await session.execute(select(func.count()).select_from(JR).where(JR.status == "parsed"))
        ).scalar() or 0
        embedded_count = (
            await session.execute(
                select(func.count()).select_from(JR).where(JR.status == "embedded")
            )
        ).scalar() or 0
        notified_count = (
            await session.execute(
                select(func.count()).select_from(JR).where(JR.status == "notified")
            )
        ).scalar() or 0

        runs_result = await session.execute(
            select(ScrapeRunRecord).order_by(ScrapeRunRecord.id.desc()).limit(20)
        )
        scrape_runs = list(runs_result.scalars().all())

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "queries": queries,
            "last_run": last_run,
            "total_jobs": total_jobs,
            "parsed_count": parsed_count,
            "embedded_count": embedded_count,
            "notified_count": notified_count,
            "scrape_runs": scrape_runs,
        },
    )


@app.get("/jobs/", response_class=HTMLResponse)
async def jobs_list(
    request: Request,
    page: int = 1,
    status: str = "",
    category: str = "",
    run_id: Optional[int] = None,
    min_score: Optional[float] = None,
):
    per_page = 30
    async with async_session_factory() as session:
        from sqlalchemy import select, func
        from src.storage.database import JobRecord as JR, JobMatch, ScrapeRunRecord

        query = select(JR).order_by(JR.created_at.desc())
        count_query = select(func.count()).select_from(JR)

        if status:
            query = query.where(JR.status == status)
            count_query = count_query.where(JR.status == status)
        if category:
            query = query.where(JR.category == category)
            count_query = count_query.where(JR.category == category)
        if run_id:
            query = query.where(JR.scrape_run_id == run_id)
            count_query = count_query.where(JR.scrape_run_id == run_id)

        if min_score is not None and min_score > 0:
            score_sub = (
                select(JobMatch.job_id, func.max(JobMatch.score).label("max_score"))
                .group_by(JobMatch.job_id)
                .subquery()
            )
            query = query.join(score_sub, JR.id == score_sub.c.job_id).where(
                score_sub.c.max_score >= min_score
            )
            count_query = count_query.join(score_sub, JR.id == score_sub.c.job_id).where(
                score_sub.c.max_score >= min_score
            )

        total = (await session.execute(count_query)).scalar() or 0
        results = await session.execute(query.offset((page - 1) * per_page).limit(per_page))
        jobs = list(results.scalars().all())

        job_ids = [j.id for j in jobs]
        best_scores: dict[int, float] = {}
        if job_ids:
            match_rows = await session.execute(
                select(JobMatch.job_id, func.max(JobMatch.score))
                .where(JobMatch.job_id.in_(job_ids))
                .group_by(JobMatch.job_id)
            )
            best_scores = {row[0]: row[1] for row in match_rows}

        categories = list(
            await session.execute(select(JR.category).distinct().order_by(JR.category))
        )
        categories = [c[0] for c in categories if c[0]]

        runs_result = await session.execute(
            select(ScrapeRunRecord).order_by(ScrapeRunRecord.id.desc()).limit(20)
        )
        scrape_runs = list(runs_result.scalars().all())

        total_pages = max(1, (total + per_page - 1) // per_page)

    return templates.TemplateResponse(
        request,
        "jobs.html",
        {
            "jobs": jobs,
            "best_scores": best_scores,
            "page": page,
            "total_pages": total_pages,
            "total": total,
            "status": status,
            "category": category,
            "run_id": run_id,
            "min_score": min_score,
            "categories": categories,
            "scrape_runs": scrape_runs,
        },
    )


@app.get("/query/{query_id}", response_class=HTMLResponse)
async def query_results(
    request: Request,
    query_id: int,
    category: str = "",
    min_score: Optional[float] = None,
):
    async with async_session_factory() as session:
        repo = JobRepository(session)
        from src.storage.database import QueryRecord, JobRecord, JobMatch
        from sqlalchemy import select, func

        result = await session.execute(select(QueryRecord).where(QueryRecord.id == query_id))
        query_record = result.scalar_one_or_none()
        if not query_record:
            return HTMLResponse("Query not found", status_code=404)

        match_query = select(JobMatch).where(JobMatch.query_id == query_id)

        if min_score is not None and min_score > 0:
            match_query = match_query.where(JobMatch.score >= min_score)

        matches_result = await session.execute(
            match_query.order_by(JobMatch.score.desc())
        )
        matches = list(matches_result.scalars().all())

        if not matches:
            categories = list(
                await session.execute(select(JobRecord.category).distinct().order_by(JobRecord.category))
            )
            categories = [c[0] for c in categories if c[0]]
            return templates.TemplateResponse(
                request,
                "results.html",
                {
                    "query": query_record,
                    "results": [],
                    "category": category,
                    "min_score": min_score,
                    "categories": categories,
                    "total_results": 0,
                    "shown_results": 0,
                },
            )

        job_ids = [m.job_id for m in matches]
        jobs_query = select(JobRecord).where(JobRecord.id.in_(job_ids))
        if category:
            jobs_query = jobs_query.where(JobRecord.category == category)
        jobs_result = await session.execute(jobs_query)
        jobs_by_id = {j.id: j for j in jobs_result.scalars().all()}

        results = []
        for match in sorted(matches, key=lambda m: m.score, reverse=True):
            job = jobs_by_id.get(match.job_id)
            if job:
                if category and job.category != category:
                    continue
                results.append(
                    {
                        "score": match.score,
                        "title": job.title,
                        "company": job.company,
                        "location": job.location,
                        "date_posted": job.date_posted,
                        "url": job.url,
                        "id": job.id,
                        "category": job.category,
                    }
                )

        categories = list(
            await session.execute(select(JobRecord.category).distinct().order_by(JobRecord.category))
        )
        categories = [c[0] for c in categories if c[0]]

        total_results = len(matches)

    return templates.TemplateResponse(
        request,
        "results.html",
        {
            "query": query_record,
            "results": results,
            "category": category,
            "min_score": min_score,
            "categories": categories,
            "total_results": total_results,
            "shown_results": len(results),
        },
    )


@app.get("/job/{job_id}", response_class=HTMLResponse)
async def job_detail(request: Request, job_id: int):
    async with async_session_factory() as session:
        from sqlalchemy import select
        from src.storage.database import JobRecord, JobMatch, QueryRecord

        result = await session.execute(select(JobRecord).where(JobRecord.id == job_id))
        job = result.scalar_one_or_none()
        if not job:
            return HTMLResponse("Job not found", status_code=404)

        match_rows = await session.execute(
            select(JobMatch, QueryRecord.id, QueryRecord.name, QueryRecord.query_text)
            .join(QueryRecord, JobMatch.query_id == QueryRecord.id)
            .where(JobMatch.job_id == job_id)
            .order_by(JobMatch.score.desc())
        )
        query_matches = [
            {
                "query_id": row.id,
                "name": row.name,
                "query_text": row.query_text,
                "score": row[0].score,
            }
            for row in match_rows
        ]

    return templates.TemplateResponse(
        request,
        "detail.html",
        {
            "job": job,
            "query_matches": query_matches,
        },
    )