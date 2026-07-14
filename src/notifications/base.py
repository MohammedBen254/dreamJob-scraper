from abc import ABC, abstractmethod

from src.models.job import JobPosting


class Notifier(ABC):
    @abstractmethod
    async def send(self, jobs: list[JobPosting]) -> bool: ...
