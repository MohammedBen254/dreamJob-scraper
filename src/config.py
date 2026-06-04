from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    scraper_target_url: str = "https://www.dreamjob.ma"
    scraper_request_delay: float = 2.0
    scraper_page_limit: int = 5
    matching_threshold: int = 60
    profile_path: str = "profile.yaml"
    database_url: str = "postgresql+asyncpg://dreamjob:dreamjob@localhost:5432/dreamjob"
    redis_url: str = "redis://localhost:6379/0"
    email_smtp_host: str = "smtp.gmail.com"
    email_smtp_port: int = 587
    email_username: str = ""
    email_password: str = ""
    email_from: str = ""
    email_to: str = ""
    scraper_run_time: str = "08:00"
    health_port: int = 8080

    model_config = {"env_prefix": "", "case_sensitive": False}


settings = Settings()
