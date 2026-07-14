from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from src.config import settings
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
        from src.storage.database import JobRecord as JR

        parsed_count = (await session.execute(
            select(func.count()).select_from(JR).where(JR.status == "parsed")
        )).scalar() or 0
        embedded_count = (await session.execute(
            select(func.count()).select_from(JR).where(JR.status == "embedded")
        )).scalar() or 0
        notified_count = (await session.execute(
            select(func.count()).select_from(JR).where(JR.status == "notified")
        )).scalar() or 0

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
        },
    )


@app.get("/jobs/", response_class=HTMLResponse)
async def jobs_list(request: Request, page: int = 1, status: str = "", category: str = ""):
    per_page = 30
    async with async_session_factory() as session:
        from sqlalchemy import select, func
        from src.storage.database import JobRecord as JR

        query = select(JR).order_by(JR.created_at.desc())
        count_query = select(func.count()).select_from(JR)

        if status:
            query = query.where(JR.status == status)
            count_query = count_query.where(JR.status == status)
        if category:
            query = query.where(JR.category == category)
            count_query = count_query.where(JR.category == category)

        total = (await session.execute(count_query)).scalar() or 0
        results = await session.execute(query.offset((page - 1) * per_page).limit(per_page))
        jobs = list(results.scalars().all())

        categories = list(await session.execute(
            select(JR.category).distinct().order_by(JR.category)
        ))
        categories = [c[0] for c in categories if c[0]]

        total_pages = max(1, (total + per_page - 1) // per_page)

    return templates.TemplateResponse(
        request,
        "jobs.html",
        {
            "jobs": jobs,
            "page": page,
            "total_pages": total_pages,
            "total": total,
            "status": status,
            "category": category,
            "categories": categories,
        },
    )


@app.get("/query/{query_id}", response_class=HTMLResponse)
async def query_results(request: Request, query_id: int):
    async with async_session_factory() as session:
        repo = JobRepository(session)
        from src.storage.database import QueryRecord, JobRecord
        from sqlalchemy import select

        result = await session.execute(select(QueryRecord).where(QueryRecord.id == query_id))
        query_record = result.scalar_one_or_none()
        if not query_record:
            return HTMLResponse("Query not found", status_code=404)

        matches = await repo.get_matches_for_query(query_id, threshold=settings.notification_threshold * 100)
        if not matches:
            return templates.TemplateResponse(
                request,
                "results.html",
                {
                    "query": query_record,
                    "results": [],
                },
            )

        job_ids = [m.job_id for m in matches]
        jobs_result = await session.execute(select(JobRecord).where(JobRecord.id.in_(job_ids)))
        jobs_by_id = {j.id: j for j in jobs_result.scalars().all()}

        results = []
        for match in sorted(matches, key=lambda m: m.score, reverse=True):
            job = jobs_by_id.get(match.job_id)
            if job:
                results.append(
                    {
                        "score": match.score,
                        "title": job.title,
                        "company": job.company,
                        "location": job.location,
                        "date_posted": job.date_posted,
                        "url": job.url,
                        "id": job.id,
                    }
                )

    return templates.TemplateResponse(
        request,
        "results.html",
        {
            "query": query_record,
            "results": results,
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
            {"query_id": row.id, "name": row.name, "query_text": row.query_text, "score": row[0].score}
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