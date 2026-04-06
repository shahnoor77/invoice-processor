"""
In-memory job queue for async invoice processing.
TODO: Replace with Celery + Redis for production scale.
"""
import threading
import uuid
from datetime import datetime
from typing import Optional

# job_id -> job dict
_jobs: dict = {}


def create_job(user_email: str, file_name: str) -> str:
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "job_id": job_id,
        "user_email": user_email,
        "file_name": file_name,
        "status": "queued",  # queued | processing | done | failed
        "created_at": datetime.utcnow().isoformat(),
        "completed_at": None,
        "result": None,
        "error": None,
    }
    return job_id


def get_job(job_id: str) -> Optional[dict]:
    return _jobs.get(job_id)


def update_job(job_id: str, **kwargs):
    if job_id in _jobs:
        _jobs[job_id].update(kwargs)


def list_jobs(user_email: str) -> list:
    return [j for j in _jobs.values() if j["user_email"] == user_email]


def run_in_background(fn, *args, **kwargs):
    t = threading.Thread(target=fn, args=args, kwargs=kwargs, daemon=True)
    t.start()
    return t
