import asyncio
import json
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import asyncpg
from redis.asyncio import Redis as AsyncRedis

from src.config import settings


def _build_dsn() -> str:
    url = settings.database_url
    if url.startswith("postgresql+asyncpg://"):
        url = url.replace("postgresql+asyncpg://", "postgresql://")
    return url


async def check_postgres() -> dict[str, Any]:
    try:
        conn = await asyncpg.connect(_build_dsn(), timeout=3)
        version = await conn.fetchval("SELECT version()")
        await conn.close()
        return {"status": "ok", "version": version.split(",")[0] if version else "unknown"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


async def check_redis() -> dict[str, Any]:
    try:
        r = AsyncRedis.from_url(settings.redis_url)
        pong = await r.ping()
        info = await r.info("server")
        redis_version = info.get("redis_version", "unknown")
        await r.aclose()
        return {"status": "ok" if pong else "error", "version": redis_version}
    except Exception as e:
        return {"status": "error", "error": str(e)}


async def check_all() -> dict[str, Any]:
    pg_result, redis_result = await asyncio.gather(check_postgres(), check_redis())
    all_ok = pg_result["status"] == "ok" and redis_result["status"] == "ok"
    return {
        "status": "ok" if all_ok else "degraded",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "services": {
            "postgres": pg_result,
            "redis": redis_result,
        },
    }


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(check_all())
        finally:
            loop.close()

        status_code = 200 if result["status"] == "ok" else 503
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(result, indent=2).encode())


def run_health_server() -> None:
    server = HTTPServer(("0.0.0.0", settings.health_port), HealthHandler)
    print(f"Health server running on port {settings.health_port}")
    server.serve_forever()


if __name__ == "__main__":
    run_health_server()
