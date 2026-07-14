from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from src.embedding.engine import embed_query, rank_jobs
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
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "queries": queries,
            "last_run": last_run,
            "total_jobs": total_jobs,
        },
    )


@app.get("/query/{query_id}", response_class=HTMLResponse)
async def query_results(request: Request, query_id: int):
    async with async_session_factory() as session:
        repo = JobRepository(session)
        from src.storage.database import QueryRecord
        from sqlalchemy import select

        result = await session.execute(select(QueryRecord).where(QueryRecord.id == query_id))
        query_record = result.scalar_one_or_none()
        if not query_record:
            return HTMLResponse("Query not found", status_code=404)

        jobs = await repo.get_all_jobs_with_embeddings()
        job_embeddings = [j.embedding for j in jobs if j.embedding]

        if not job_embeddings:
            return templates.TemplateResponse(
                request,
                "results.html",
                {
                    "query": query_record,
                    "results": [],
                },
            )

        query_vec = await embed_query(query_record.query_text)
        ranked = rank_jobs(query_vec, job_embeddings, top_k=len(jobs))

        results = []
        for r in ranked:
            job = jobs[r["corpus_id"]]
            results.append(
                {
                    "score": round(r["score"] * 100, 1),
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
        from src.storage.database import JobRecord

        result = await session.execute(select(JobRecord).where(JobRecord.id == job_id))
        job = result.scalar_one_or_none()
        if not job:
            return HTMLResponse("Job not found", status_code=404)

    return templates.TemplateResponse(
        request,
        "detail.html",
        {
            "job": job,
        },
    )
