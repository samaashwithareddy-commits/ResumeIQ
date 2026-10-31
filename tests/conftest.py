"""Shared pytest fixtures. Every test uses its own temporary SQLite database."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# Keep the module-level app created by app.py away from the real project database.
os.environ.setdefault("RESUMEIQ_DB", str(Path(tempfile.mkdtemp(prefix="resumeiq-import-")) / "import.db"))
os.environ.pop("FEATHERLESS_API_KEY", None)

import pytest  # noqa: E402

from app import create_app  # noqa: E402
from database.db import init_db  # noqa: E402
from database.seed import DEMO_PROFILE, SAMPLE_JOB  # noqa: E402
from services.matcher import parse_job_description, score_match  # noqa: E402


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "resumeiq.db"
    init_db(path)
    return path


@pytest.fixture()
def demo_profile() -> dict:
    return {key: (value[:] if isinstance(value, list) else value) for key, value in DEMO_PROFILE.items()}


@pytest.fixture()
def sample_job() -> dict:
    return dict(SAMPLE_JOB)


@pytest.fixture()
def sample_analysis(sample_job: dict) -> dict:
    analysis = parse_job_description(
        sample_job["description"], sample_job["title"], sample_job["company"]
    )
    analysis.pop("description", None)
    return analysis


@pytest.fixture()
def sample_match(demo_profile: dict, sample_analysis: dict) -> dict:
    return score_match(demo_profile, sample_analysis)


@pytest.fixture()
def app(db_path: Path):
    application = create_app(db_path)
    application.config.update(TESTING=True)
    return application


@pytest.fixture()
def client(app):
    with app.test_client() as test_client:
        yield test_client
