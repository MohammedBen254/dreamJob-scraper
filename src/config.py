from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    scraper_target_url: str = "https://www.dreamjob.ma"
    scraper_request_delay: float = 2.0
    scraper_page_limit: int = 5
    profile_path: str = "profile.yaml"
    database_url: str = "postgresql+asyncpg://dreamjob:dreamjob@localhost:5432/dreamjob"
    scraper_run_time: str = "08:00"
    web_port: int = 8080
    queries_path: str = "queries.yaml"
    email_smtp_host: str = "smtp.gmail.com"
    email_smtp_port: int = 587
    email_username: str = ""
    email_password: str = ""
    email_from: str = ""
    email_to: str = ""
    notification_threshold: float = 0.6
    ollama_host: str = "http://localhost:11434"
    reranker_model: str = "jinaai/jina-reranker-v2-base-multilingual"
    reranker_top_k: int = 20
    use_reranker: bool = True
    stage1_threshold: float = 0.3

    model_config = {"env_prefix": "", "case_sensitive": False}


settings = Settings()
