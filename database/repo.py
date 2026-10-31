"""Data access layer. Every statement is parameterised."""

from __future__ import annotations

import json
import re
from typing import Any

from database.db import session

TEMPLATES = ("classic", "modern", "minimal")

SECTION_LIBRARY: list[tuple[str, str]] = [
    ("summary", "Professional Summary"),
    ("skills", "Skills"),
    ("education", "Education"),
    ("projects", "Projects"),
    ("experience", "Experience"),
    ("certifications", "Certifications"),
    ("achievements", "Achievements"),
]
SECTION_LABELS = dict(SECTION_LIBRARY)

BASICS_FIELDS = (
    "full_name",
    "headline",
    "email",
    "phone",
    "location",
    "linkedin",
    "github",
)

EMPTY_PROFILE: dict[str, Any] = {
    "full_name": "",
    "headline": "",
    "email": "",
    "phone": "",
    "location": "",
    "linkedin": "",
    "github": "",
    "summary": "",
    "skills": [],
    "education": [],
    "projects": [],
    "experience": [],
    "certifications": [],
    "achievements": [],
}


def _rows(conn, sql: str, params: tuple = ()) -> list[dict]:
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------
def get_profile(db_path: str | None = None) -> dict:
    with session(db_path) as conn:
        row = conn.execute("SELECT * FROM profile WHERE id = 1").fetchone()
        profile = dict(EMPTY_PROFILE)
        if row:
            for key in ("full_name", "headline", "email", "phone", "location", "linkedin", "github", "summary"):
                profile[key] = row[key] or ""
            profile["updated_at"] = row["updated_at"] if "updated_at" in row.keys() else ""

        profile["skills"] = [
            r["name"]
            for r in _rows(
                conn,
                "SELECT name FROM skills WHERE profile_id = 1 ORDER BY position, id",
            )
        ]
        profile["education"] = _rows(
            conn,
            """SELECT id, institution, degree, field, start_date, end_date, score, location
               FROM education WHERE profile_id = 1 ORDER BY position, id""",
        )
        profile["projects"] = _rows(
            conn,
            """SELECT id, name, description, tech, link
               FROM projects WHERE profile_id = 1 ORDER BY position, id""",
        )
        profile["experience"] = _rows(
            conn,
            """SELECT id, role, company, start_date, end_date, location, description
               FROM experience WHERE profile_id = 1 ORDER BY position, id""",
        )
        profile["certifications"] = _rows(
            conn,
            """SELECT id, name, issuer, year
               FROM certifications WHERE profile_id = 1 ORDER BY position, id""",
        )
        profile["achievements"] = [
            r["text"]
            for r in _rows(
                conn,
                "SELECT text FROM achievements WHERE profile_id = 1 ORDER BY position, id",
            )
        ]
    return profile


def save_profile(db_path: str | None, data: dict) -> dict:
    """Replace the master profile inside a single transaction."""
    with session(db_path) as conn:
        conn.execute(
            """UPDATE profile SET full_name=?, headline=?, email=?, phone=?, location=?,
                   linkedin=?, github=?, summary=?, updated_at=CURRENT_TIMESTAMP
               WHERE id = 1""",
            tuple(str(data.get(key, "") or "") for key in BASICS_FIELDS) + (str(data.get("summary", "") or ""),),
        )
        for table in ("skills", "education", "projects", "experience", "certifications", "achievements"):
            conn.execute(f"DELETE FROM {table} WHERE profile_id = 1")  # table names are fixed

        for position, skill in enumerate(data.get("skills", [])):
            if str(skill).strip():
                conn.execute(
                    "INSERT INTO skills (profile_id, name, position) VALUES (1, ?, ?)",
                    (str(skill).strip(), position),
                )

        for position, item in enumerate(data.get("education", [])):
            conn.execute(
                """INSERT INTO education
                   (profile_id, institution, degree, field, start_date, end_date, score, location, position)
                   VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    item.get("institution", ""),
                    item.get("degree", ""),
                    item.get("field", ""),
                    item.get("start_date", ""),
                    item.get("end_date", ""),
                    item.get("score", ""),
                    item.get("location", ""),
                    position,
                ),
            )

        for position, item in enumerate(data.get("projects", [])):
            conn.execute(
                """INSERT INTO projects (profile_id, name, description, tech, link, position)
                   VALUES (1, ?, ?, ?, ?, ?)""",
                (
                    item.get("name", ""),
                    item.get("description", ""),
                    item.get("tech", ""),
                    item.get("link", ""),
                    position,
                ),
            )

        for position, item in enumerate(data.get("experience", [])):
            conn.execute(
                """INSERT INTO experience
                   (profile_id, role, company, start_date, end_date, location, description, position)
                   VALUES (1, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    item.get("role", ""),
                    item.get("company", ""),
                    item.get("start_date", ""),
                    item.get("end_date", ""),
                    item.get("location", ""),
                    item.get("description", ""),
                    position,
                ),
            )

        for position, item in enumerate(data.get("certifications", [])):
            conn.execute(
                """INSERT INTO certifications (profile_id, name, issuer, year, position)
                   VALUES (1, ?, ?, ?, ?)""",
                (item.get("name", ""), item.get("issuer", ""), item.get("year", ""), position),
            )

        for position, text in enumerate(data.get("achievements", [])):
            if str(text).strip():
                conn.execute(
                    "INSERT INTO achievements (profile_id, text, position) VALUES (1, ?, ?)",
                    (str(text).strip(), position),
                )
    return get_profile(db_path)


# ---------------------------------------------------------------------------
# Resumes
# ---------------------------------------------------------------------------
def split_bullets(text: str) -> list[str]:
    """Turn a free-text description into cleaned bullet lines."""
    if not text:
        return []
    parts = re.split(r"\r?\n", str(text))
    bullets: list[str] = []
    for part in parts:
        cleaned = re.sub(r"^\s*[•\-\*–]\s*", "", part).strip()
        if cleaned:
            bullets.append(cleaned)
    return bullets


def default_sections(content: dict) -> list[dict]:
    """Default section order; optional empty sections start hidden."""
    has = {
        "summary": bool(str(content.get("summary", "")).strip()),
        "skills": bool(content.get("skills")),
        "education": bool(content.get("education")),
        "projects": bool(content.get("projects")),
        "experience": bool(content.get("experience")),
        "certifications": bool(content.get("certifications")),
        "achievements": bool(content.get("achievements")),
    }
    sections = []
    for position, (key, label) in enumerate(SECTION_LIBRARY):
        sections.append(
            {
                "section_key": key,
                "label": label,
                "position": position,
                "visible": 1 if has.get(key, True) else 0,
            }
        )
    return sections


def content_from_profile(profile: dict) -> dict:
    return {
        "basics": {key: profile.get(key, "") or "" for key in BASICS_FIELDS},
        "summary": profile.get("summary", "") or "",
        "skills": [str(s) for s in profile.get("skills", [])],
        "education": [
            {
                "institution": item.get("institution", ""),
                "degree": item.get("degree", ""),
                "field": item.get("field", ""),
                "start_date": item.get("start_date", ""),
                "end_date": item.get("end_date", ""),
                "score": item.get("score", ""),
                "location": item.get("location", ""),
            }
            for item in profile.get("education", [])
        ],
        "projects": [
            {
                "name": item.get("name", ""),
                "tech": item.get("tech", ""),
                "link": item.get("link", ""),
                "bullets": split_bullets(item.get("description", "")),
            }
            for item in profile.get("projects", [])
        ],
        "experience": [
            {
                "role": item.get("role", ""),
                "company": item.get("company", ""),
                "start_date": item.get("start_date", ""),
                "end_date": item.get("end_date", ""),
                "location": item.get("location", ""),
                "bullets": split_bullets(item.get("description", "")),
            }
            for item in profile.get("experience", [])
        ],
        "certifications": [
            {
                "name": item.get("name", ""),
                "issuer": item.get("issuer", ""),
                "year": item.get("year", ""),
            }
            for item in profile.get("certifications", [])
        ],
        "achievements": [str(a) for a in profile.get("achievements", [])],
        "custom_sections": [],
    }


def create_resume(
    db_path: str | None,
    content: dict,
    title: str,
    template: str = "classic",
    job_id: int | None = None,
    sections: list[dict] | None = None,
) -> int:
    template = template if template in TEMPLATES else "classic"
    sections = sections or default_sections(content)
    with session(db_path) as conn:
        cursor = conn.execute(
            """INSERT INTO resumes (title, template, job_id, content_json)
               VALUES (?, ?, ?, ?)""",
            (title[:120] or "Untitled resume", template, job_id, json.dumps(content)),
        )
        resume_id = int(cursor.lastrowid)
        for position, section in enumerate(sections):
            conn.execute(
                """INSERT INTO resume_sections (resume_id, section_key, label, position, visible)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    resume_id,
                    section["section_key"],
                    section.get("label") or SECTION_LABELS.get(section["section_key"], section["section_key"]),
                    position,
                    1 if section.get("visible", 1) else 0,
                ),
            )
    return resume_id


def create_resume_from_profile(
    db_path: str | None,
    profile: dict,
    title: str | None = None,
    template: str = "classic",
    job_id: int | None = None,
) -> int:
    content = content_from_profile(profile)
    name = content["basics"].get("full_name") or "Resume"
    return create_resume(
        db_path,
        content,
        title or f"{name} — Resume",
        template=template,
        job_id=job_id,
    )


def _sections_for(conn, resume_id: int) -> list[dict]:
    rows = _rows(
        conn,
        """SELECT section_key, label, position, visible FROM resume_sections
           WHERE resume_id = ? ORDER BY position, id""",
        (resume_id,),
    )
    return [
        {
            "section_key": row["section_key"],
            "label": row["label"],
            "position": row["position"],
            "visible": bool(row["visible"]),
        }
        for row in rows
    ]


def get_resume(db_path: str | None, resume_id: int) -> dict | None:
    with session(db_path) as conn:
        row = conn.execute("SELECT * FROM resumes WHERE id = ?", (resume_id,)).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "title": row["title"],
            "template": row["template"],
            "job_id": row["job_id"],
            "content": json.loads(row["content_json"]),
            "sections": _sections_for(conn, resume_id),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }


def list_resumes(db_path: str | None = None, limit: int = 50) -> list[dict]:
    with session(db_path) as conn:
        rows = _rows(
            conn,
            """SELECT r.id, r.title, r.template, r.job_id, r.created_at, r.updated_at,
                      (SELECT COUNT(*) FROM resume_sections s WHERE s.resume_id = r.id) AS section_count,
                      j.title AS job_title, j.company AS job_company
               FROM resumes r LEFT JOIN jobs j ON j.id = r.job_id
               ORDER BY r.updated_at DESC, r.id DESC LIMIT ?""",
            (limit,),
        )
    return rows


def update_resume(db_path: str | None, resume_id: int, data: dict) -> bool:
    with session(db_path) as conn:
        row = conn.execute("SELECT id FROM resumes WHERE id = ?", (resume_id,)).fetchone()
        if not row:
            return False
        fields: list[str] = []
        params: list[Any] = []
        if "title" in data and data["title"] is not None:
            fields.append("title = ?")
            params.append(str(data["title"])[:120] or "Untitled resume")
        if "template" in data and data["template"] in TEMPLATES:
            fields.append("template = ?")
            params.append(data["template"])
        if "content" in data and isinstance(data["content"], dict):
            fields.append("content_json = ?")
            params.append(json.dumps(data["content"]))
        fields.append("updated_at = CURRENT_TIMESTAMP")
        params.append(resume_id)
        conn.execute(f"UPDATE resumes SET {', '.join(fields)} WHERE id = ?", tuple(params))

        sections = data.get("sections")
        if isinstance(sections, list) and sections:
            conn.execute("DELETE FROM resume_sections WHERE resume_id = ?", (resume_id,))
            for position, section in enumerate(sections):
                key = str(section.get("section_key", ""))[:60] or f"section_{position}"
                conn.execute(
                    """INSERT INTO resume_sections (resume_id, section_key, label, position, visible)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        resume_id,
                        key,
                        str(section.get("label") or SECTION_LABELS.get(key, key))[:80],
                        position,
                        1 if section.get("visible", 1) else 0,
                    ),
                )
    return True


def delete_resume(db_path: str | None, resume_id: int) -> bool:
    with session(db_path) as conn:
        cursor = conn.execute("DELETE FROM resumes WHERE id = ?", (resume_id,))
        return cursor.rowcount > 0


def count_resumes(db_path: str | None = None) -> int:
    with session(db_path) as conn:
        return int(conn.execute("SELECT COUNT(*) FROM resumes").fetchone()[0])


# ---------------------------------------------------------------------------
# Jobs and match results
# ---------------------------------------------------------------------------
def save_job(
    db_path: str | None,
    title: str,
    company: str,
    url: str,
    description: str,
    analysis: dict,
) -> int:
    with session(db_path) as conn:
        cursor = conn.execute(
            """INSERT INTO jobs (title, company, url, description, analysis_json)
               VALUES (?, ?, ?, ?, ?)""",
            (
                (title or "")[:160],
                (company or "")[:160],
                (url or "")[:500],
                description,
                json.dumps(analysis),
            ),
        )
        return int(cursor.lastrowid)


def get_job(db_path: str | None, job_id: int) -> dict | None:
    with session(db_path) as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if not row:
            return None
        job = dict(row)
        job["analysis"] = json.loads(job.pop("analysis_json"))
        return job


def list_jobs(db_path: str | None = None, limit: int = 20) -> list[dict]:
    with session(db_path) as conn:
        rows = _rows(
            conn,
            """SELECT id, title, company, url, created_at,
                      (SELECT score FROM match_results m WHERE m.job_id = jobs.id
                       ORDER BY m.id DESC LIMIT 1) AS score
               FROM jobs ORDER BY id DESC LIMIT ?""",
            (limit,),
        )
    return rows


def save_match(
    db_path: str | None,
    job_id: int,
    resume_id: int | None,
    score: float,
    breakdown: dict,
) -> int:
    with session(db_path) as conn:
        cursor = conn.execute(
            """INSERT INTO match_results (job_id, resume_id, score, breakdown_json)
               VALUES (?, ?, ?, ?)""",
            (job_id, resume_id, float(score), json.dumps(breakdown)),
        )
        return int(cursor.lastrowid)


def latest_match_for_job(db_path: str | None, job_id: int) -> dict | None:
    with session(db_path) as conn:
        row = conn.execute(
            """SELECT m.*, j.title AS job_title, j.company AS job_company, j.id AS job_id
               FROM match_results m JOIN jobs j ON j.id = m.job_id
               WHERE m.job_id = ? ORDER BY m.id DESC LIMIT 1""",
            (job_id,),
        ).fetchone()
        if not row:
            return None
        result = dict(row)
        result["breakdown"] = json.loads(result.pop("breakdown_json"))
        return result


def latest_match(db_path: str | None = None) -> dict | None:
    with session(db_path) as conn:
        row = conn.execute(
            """SELECT m.*, j.title AS job_title, j.company AS job_company, j.id AS job_id
               FROM match_results m JOIN jobs j ON j.id = m.job_id
               ORDER BY m.id DESC LIMIT 1"""
        ).fetchone()
        if not row:
            return None
        result = dict(row)
        result["breakdown"] = json.loads(result.pop("breakdown_json"))
        return result


# ---------------------------------------------------------------------------
# Exports and settings
# ---------------------------------------------------------------------------
def record_export(db_path: str | None, resume_id: int, filename: str, fmt: str, template: str) -> int:
    with session(db_path) as conn:
        cursor = conn.execute(
            """INSERT INTO exports (resume_id, filename, fmt, template)
               VALUES (?, ?, ?, ?)""",
            (resume_id, filename, fmt, template),
        )
        return int(cursor.lastrowid)


def list_exports(db_path: str | None = None, limit: int = 100) -> list[dict]:
    with session(db_path) as conn:
        return _rows(
            conn,
            """SELECT e.id, e.resume_id, e.filename, e.fmt, e.template, e.created_at,
                      r.title AS resume_title
               FROM exports e JOIN resumes r ON r.id = e.resume_id
               ORDER BY e.id DESC LIMIT ?""",
            (limit,),
        )


def get_setting(db_path: str | None, key: str, default: str = "") -> str:
    with session(db_path) as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(db_path: str | None, key: str, value: str) -> None:
    with session(db_path) as conn:
        conn.execute(
            """INSERT INTO settings (key, value) VALUES (?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
            (key, value),
        )


def reset_all(db_path: str | None = None) -> None:
    """Delete every user record but keep the schema (used by Settings)."""
    with session(db_path) as conn:
        for table in (
            "exports",
            "match_results",
            "resume_sections",
            "resumes",
            "jobs",
            "achievements",
            "certifications",
            "experience",
            "projects",
            "education",
            "skills",
        ):
            conn.execute(f"DELETE FROM {table}")
        conn.execute(
            """UPDATE profile SET full_name='', headline='', email='', phone='', location='',
                   linkedin='', github='', summary='', updated_at=CURRENT_TIMESTAMP WHERE id = 1"""
        )
