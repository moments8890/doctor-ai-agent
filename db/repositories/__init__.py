from __future__ import annotations

from db.repositories.patients import PatientRepository
from db.repositories.records import RecordRepository
from db.repositories.tasks import TaskRepository

__all__ = ["PatientRepository", "RecordRepository", "TaskRepository"]
