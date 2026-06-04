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
