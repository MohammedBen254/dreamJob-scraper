import yaml
from pathlib import Path

from pydantic import BaseModel


SYNONYM_MAP: dict[str, list[str]] = {
    "python": ["python"],
    "sql": ["sql", "sql server", "mysql", "postgresql"],
    "tableau": ["tableau"],
    "power bi": ["power bi", "powerbi"],
    "analyse de données": ["analyse de données", "analyse de donnees", "data analysis"],
    "data visualization": ["data visualization", "visualisation de données", "dataviz"],
    "machine learning": ["machine learning", "ml"],
    "deep learning": ["deep learning", "dl"],
    "tensorflow": ["tensorflow", "tf"],
    "pytorch": ["pytorch"],
    "nlp": ["nlp", "natural language processing"],
    "intelligence artificielle": [
        "intelligence artificielle", "artificial intelligence", "ia", "ai"
    ],
    "react": ["react", "react.js", "reactjs"],
    "angular": ["angular", "angular.js", "angularjs"],
    "vue": ["vue", "vue.js", "vuejs"],
    "javascript": ["javascript", "js"],
    "typescript": ["typescript", "ts"],
    "php": ["php"],
    "node.js": ["node.js", "nodejs", "node"],
    "django": ["django"],
    "full stack": ["full stack", "fullstack"],
    "développeur web": ["développeur web", "developpeur web", "web developer"],
    "réseau": ["réseau", "reseau", "network"],
    "cybersécurité": ["cybersécurité", "cybersecurite", "cybersecurity"],
    "devops": ["devops"],
    "cloud": ["cloud"],
    "linux": ["linux"],
    "etl": ["etl"],
    "big data": ["big data"],
    "statistiques": ["statistiques", "statistics"],
    "computer vision": ["computer vision", "vision par ordinateur"],
    "next.js": ["next.js", "nextjs", "next js"],
    "nest.js": ["nest.js", "nestjs", "nest js"],
    "express.js": ["express.js", "expressjs", "express js", "express"],
    "fastapi": ["fastapi", "fast api", "fast-api"],
    "redux": ["redux", "react redux", "redux toolkit"],
    "tailwindcss": ["tailwindcss", "tailwind", "tailwind css", "tailwind-css"],
    "rest api": ["rest api", "restful", "rest", "api rest"],
    "api": ["api", "apis"],
    "postgresql": ["postgresql", "postgres", "psql"],
    "mongodb": ["mongodb", "mongo"],
    "mysql": ["mysql"],
    "redis": ["redis"],
    "celery": ["celery", "celery worker"],
    "docker": ["docker", "dockerfile", "docker-compose", "docker compose", "container"],
    "ci/cd": ["ci/cd", "cicd", "ci cd", "continuous integration", "continuous deployment"],
    "github actions": ["github actions", "gh actions"],
    "aws": ["aws", "amazon web services"],
    "gcp": ["gcp", "google cloud", "google cloud platform"],
    "google cloud": ["google cloud", "gcp", "google cloud platform"],
    "nginx": ["nginx", "nginx reverse proxy"],
    "supabase": ["supabase"],
    "hls": ["hls", "http live streaming"],
    "video streaming": ["video streaming", "streaming video", "video stream", "hls"],
    "streaming": ["streaming", "stream"],
    "socket.io": ["socket.io", "socketio", "socket io", "websocket", "websockets"],
    "n8n": ["n8n", "n8n.io", "n 8n"],
    "automation": ["automation", "automatisation", "automate", "automated"],
    "workflow": ["workflow", "workflows", "work flow"],
    "integration": ["integration", "integrations", "integrate"],
    "webhooks": ["webhooks", "webhook"],
    "wordpress": ["wordpress", "wp", "word press"],
    "google api": ["google api", "google apis", "google sheets api", "google sheets"],
    "saas": ["saas", "software as a service"],
    "erp": ["erp", "enterprise resource planning", "pgi"],
    "lms": ["lms", "learning management system"],
    "crm": ["crm", "customer relationship management"],
    "microservices": ["microservices", "micro-services", "micro services", "microservice"],
    "backend": ["backend", "back-end", "back end", "back end developer"],
    "frontend": ["frontend", "front-end", "front end", "front end developer"],
    "data science": ["data science", "data sciences", "data scientist"],
    "data scientist": ["data scientist", "data scientists", "data science"],
    "database": ["database", "databases", "db", "base de données"],
    "pytest": ["pytest", "py.test"],
    "jest": ["jest", "jest testing"],
    "unit testing": ["unit testing", "unit test", "tests unitaires"],
    "integration testing": ["integration testing", "integration test", "test d'intégration"],
    "test": ["test", "tests", "testing"],
}


class UserProfile(BaseModel):
    target_keywords: dict[str, list[str]]
    excluded_terms: list[str] = []
    threshold: int = 60

    @classmethod
    def load(cls, path: str) -> "UserProfile":
        p = Path(path)
        if not p.exists():
            return cls(target_keywords={})
        with open(p, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls(**data)

    def get_all_keywords(self) -> list[str]:
        return [
            kw
            for kws in self.target_keywords.values()
            for kw in kws
        ]

    def get_expanded_keywords(self) -> set[str]:
        expanded: set[str] = set()
        for kw in self.get_all_keywords():
            expanded.add(kw.lower())
            expanded.update(
                s.lower() for s in SYNONYM_MAP.get(kw.lower(), [])
            )
        return expanded
