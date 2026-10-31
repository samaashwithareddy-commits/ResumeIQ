"""Input validation and normalisation for resume/profile payloads."""

from __future__ import annotations

import re
from typing import Any

MAX_TEXT = 400
MAX_LONG_TEXT = 3000
MAX_SUMMARY = 2500
MAX_SKILLS = 80
MAX_EDUCATION = 15
MAX_PROJECTS = 30
MAX_EXPERIENCE = 30
MAX_CERTIFICATIONS = 20
MAX_ACHIEVEMENTS = 30
MAX_BULLETS = 25
MAX_BULLET_LEN = 600
MAX_CUSTOM_SECTIONS = 6
MAX_CONTENT_BYTES = 400_000

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
URL_RE = re.compile(r"^https?://[^\s]+$", re.I)
PHONE_RE = re.compile(r"^\+?[\d\s().-]{6,25}$")
SKILL_SPLIT_RE = re.compile(r"[,;\n|]+")

SECTION_KEYS = ("summary", "skills", "education", "projects", "experience", "certifications", "achievements")
SECTION_LABELS = {
    "summary": "Professional Summary",
    "skills": "Skills",
    "education": "Education",
    "projects": "Projects",
    "experience": "Experience",
    "certifications": "Certifications",
    "achievements": "Achievements",
}


def clean_str(value: Any, limit: int = MAX_TEXT) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        value = str(value)
    if not isinstance(value, str):
        return ""
    value = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    return value[:limit]


def clean_bullets(value: Any, limit: int = MAX_BULLETS) -> list[str]:
    if isinstance(value, str):
        items = re.split(r"\r?\n", value)
    elif isinstance(value, list):
        items = value
    else:
        items = []
    bullets: list[str] = []
    for item in items:
        text = clean_str(item, MAX_BULLET_LEN)
        text = re.sub(r"^\s*[•\-\*–]\s*", "", text).strip()
        if text:
            bullets.append(text)
        if len(bullets) >= limit:
            break
    return bullets


def clean_skills(value: Any) -> list[str]:
    if isinstance(value, str):
        parts = SKILL_SPLIT_RE.split(value)
    elif isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, str):
                parts.extend(SKILL_SPLIT_RE.split(item))
    else:
        parts = []
    skills: list[str] = []
    seen: set[str] = set()
    for part in parts:
        text = clean_str(part, 60)
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            skills.append(text)
        if len(skills) >= MAX_SKILLS:
            break
    return skills


def _check_contact(errors: list[str], label: str, value: str, regex: re.Pattern, message: str) -> None:
    if value and not regex.match(value):
        errors.append(f"{label}: {message}")


def clean_profile_payload(payload: Any) -> tuple[dict, list[str]]:
    """Validate and normalise the master-profile document."""
    errors: list[str] = []
    if not isinstance(payload, dict):
        return {}, ["Invalid profile payload."]

    data = {
        "full_name": clean_str(payload.get("full_name"), 120),
        "headline": clean_str(payload.get("headline"), 160),
        "email": clean_str(payload.get("email"), 160),
        "phone": clean_str(payload.get("phone"), 40),
        "location": clean_str(payload.get("location"), 120),
        "linkedin": clean_str(payload.get("linkedin"), 300),
        "github": clean_str(payload.get("github"), 300),
        "summary": clean_str(payload.get("summary"), MAX_SUMMARY),
    }
    _check_contact(errors, "Email", data["email"], EMAIL_RE, "enter a valid email address, e.g. you@example.com")
    _check_contact(errors, "Phone", data["phone"], PHONE_RE, "use digits, spaces, +, -, or parentheses only")
    _check_contact(
        errors, "LinkedIn URL", data["linkedin"], URL_RE, "must start with http:// or https://"
    )
    _check_contact(errors, "GitHub URL", data["github"], URL_RE, "must start with http:// or https://")

    data["skills"] = clean_skills(payload.get("skills"))

    education: list[dict] = []
    for index, item in enumerate(payload.get("education") or []):
        if not isinstance(item, dict):
            continue
        entry = {
            "institution": clean_str(item.get("institution"), 160),
            "degree": clean_str(item.get("degree"), 120),
            "field": clean_str(item.get("field"), 120),
            "start_date": clean_str(item.get("start_date"), 40),
            "end_date": clean_str(item.get("end_date"), 40),
            "score": clean_str(item.get("score"), 60),
            "location": clean_str(item.get("location"), 120),
        }
        if not any(entry.values()):
            continue
        if not entry["institution"]:
            errors.append(f"Education entry {index + 1}: institution name is required.")
        education.append(entry)
        if len(education) >= MAX_EDUCATION:
            break
    data["education"] = education

    projects: list[dict] = []
    for index, item in enumerate(payload.get("projects") or []):
        if not isinstance(item, dict):
            continue
        entry = {
            "name": clean_str(item.get("name"), 160),
            "tech": clean_str(item.get("tech"), 220),
            "link": clean_str(item.get("link"), 300),
            "description": clean_str(item.get("description"), MAX_LONG_TEXT),
        }
        if not any(entry.values()):
            continue
        if not entry["name"]:
            errors.append(f"Project entry {index + 1}: project name is required.")
        if entry["link"] and not URL_RE.match(entry["link"]):
            errors.append(f"Project entry {index + 1}: link must start with http:// or https://")
        projects.append(entry)
        if len(projects) >= MAX_PROJECTS:
            break
    data["projects"] = projects

    experience: list[dict] = []
    for index, item in enumerate(payload.get("experience") or []):
        if not isinstance(item, dict):
            continue
        entry = {
            "role": clean_str(item.get("role"), 160),
            "company": clean_str(item.get("company"), 160),
            "start_date": clean_str(item.get("start_date"), 40),
            "end_date": clean_str(item.get("end_date"), 40),
            "location": clean_str(item.get("location"), 120),
            "description": clean_str(item.get("description"), MAX_LONG_TEXT),
        }
        if not any(entry.values()):
            continue
        if not entry["role"] and not entry["company"]:
            errors.append(f"Experience entry {index + 1}: add a role or a company.")
        experience.append(entry)
        if len(experience) >= MAX_EXPERIENCE:
            break
    data["experience"] = experience

    certifications: list[dict] = []
    for index, item in enumerate(payload.get("certifications") or []):
        if not isinstance(item, dict):
            continue
        entry = {
            "name": clean_str(item.get("name"), 180),
            "issuer": clean_str(item.get("issuer"), 160),
            "year": clean_str(item.get("year"), 20),
        }
        if not any(entry.values()):
            continue
        if not entry["name"]:
            errors.append(f"Certification entry {index + 1}: certification name is required.")
        certifications.append(entry)
        if len(certifications) >= MAX_CERTIFICATIONS:
            break
    data["certifications"] = certifications

    achievements: list[str] = []
    for item in payload.get("achievements") or []:
        text = clean_str(item, 400)
        if text:
            achievements.append(text)
        if len(achievements) >= MAX_ACHIEVEMENTS:
            break
    data["achievements"] = achievements

    if not data["full_name"] and any(
        [data["email"], data["phone"], data["summary"], data["skills"], education, projects, experience]
    ):
        errors.append("Full name is required when the profile contains other details.")

    return data, errors


def clean_resume_content(payload: Any, existing: dict | None = None) -> tuple[dict, list[str], list[dict]]:
    """Validate a resume document plus its section ordering."""
    errors: list[str] = []
    if not isinstance(payload, dict):
        return {}, ["Invalid resume payload."], []

    content = payload.get("content") if isinstance(payload.get("content"), dict) else payload
    basics_in = content.get("basics") if isinstance(content.get("basics"), dict) else {}

    basics = {
        "full_name": clean_str(basics_in.get("full_name"), 120),
        "headline": clean_str(basics_in.get("headline"), 160),
        "email": clean_str(basics_in.get("email"), 160),
        "phone": clean_str(basics_in.get("phone"), 40),
        "location": clean_str(basics_in.get("location"), 120),
        "linkedin": clean_str(basics_in.get("linkedin"), 300),
        "github": clean_str(basics_in.get("github"), 300),
    }
    _check_contact(errors, "Email", basics["email"], EMAIL_RE, "enter a valid email address")
    _check_contact(errors, "Phone", basics["phone"], PHONE_RE, "use digits, spaces, +, -, or parentheses only")
    _check_contact(errors, "LinkedIn URL", basics["linkedin"], URL_RE, "must start with http:// or https://")
    _check_contact(errors, "GitHub URL", basics["github"], URL_RE, "must start with http:// or https://")

    doc: dict[str, Any] = {
        "basics": basics,
        "summary": clean_str(content.get("summary"), MAX_SUMMARY),
        "skills": clean_skills(content.get("skills")),
        "education": [],
        "projects": [],
        "experience": [],
        "certifications": [],
        "achievements": [],
        "custom_sections": [],
    }

    for item in content.get("education") or []:
        if not isinstance(item, dict):
            continue
        entry = {
            "institution": clean_str(item.get("institution"), 160),
            "degree": clean_str(item.get("degree"), 120),
            "field": clean_str(item.get("field"), 120),
            "start_date": clean_str(item.get("start_date"), 40),
            "end_date": clean_str(item.get("end_date"), 40),
            "score": clean_str(item.get("score"), 60),
            "location": clean_str(item.get("location"), 120),
        }
        if any(entry.values()):
            doc["education"].append(entry)
        if len(doc["education"]) >= MAX_EDUCATION:
            break

    for item in content.get("projects") or []:
        if not isinstance(item, dict):
            continue
        entry = {
            "name": clean_str(item.get("name"), 160),
            "tech": clean_str(item.get("tech"), 220),
            "link": clean_str(item.get("link"), 300),
            "bullets": clean_bullets(item.get("bullets")),
        }
        if any([entry["name"], entry["tech"], entry["link"], entry["bullets"]]):
            doc["projects"].append(entry)
        if len(doc["projects"]) >= MAX_PROJECTS:
            break

    for item in content.get("experience") or []:
        if not isinstance(item, dict):
            continue
        entry = {
            "role": clean_str(item.get("role"), 160),
            "company": clean_str(item.get("company"), 160),
            "start_date": clean_str(item.get("start_date"), 40),
            "end_date": clean_str(item.get("end_date"), 40),
            "location": clean_str(item.get("location"), 120),
            "bullets": clean_bullets(item.get("bullets")),
        }
        if any([entry["role"], entry["company"], entry["bullets"]]):
            doc["experience"].append(entry)
        if len(doc["experience"]) >= MAX_EXPERIENCE:
            break

    for item in content.get("certifications") or []:
        if not isinstance(item, dict):
            continue
        entry = {
            "name": clean_str(item.get("name"), 180),
            "issuer": clean_str(item.get("issuer"), 160),
            "year": clean_str(item.get("year"), 20),
        }
        if any(entry.values()):
            doc["certifications"].append(entry)
        if len(doc["certifications"]) >= MAX_CERTIFICATIONS:
            break

    doc["achievements"] = clean_bullets(content.get("achievements"), MAX_ACHIEVEMENTS)

    for item in content.get("custom_sections") or []:
        if not isinstance(item, dict):
            continue
        section_id = re.sub(r"[^a-z0-9_-]", "", str(item.get("id", "")).lower())[:24]
        title = clean_str(item.get("title"), 80)
        if not section_id or not title:
            continue
        doc["custom_sections"].append(
            {"id": section_id, "title": title, "bullets": clean_bullets(item.get("bullets"), 12)}
        )
        if len(doc["custom_sections"]) >= MAX_CUSTOM_SECTIONS:
            break

    sections_in = payload.get("sections") if isinstance(payload, dict) else None
    sections: list[dict] = []
    seen: set[str] = set()
    custom_ids = {f"custom:{item['id']}" for item in doc["custom_sections"]}
    if isinstance(sections_in, list):
        for item in sections_in:
            if not isinstance(item, dict):
                continue
            key = str(item.get("section_key", "")).strip()
            if key not in SECTION_KEYS and key not in custom_ids:
                continue
            if key in seen:
                continue
            seen.add(key)
            label = clean_str(item.get("label"), 80) or SECTION_LABELS.get(key)
            if key.startswith("custom:"):
                custom_id = key.split(":", 1)[1]
                label = next(
                    (s["title"] for s in doc["custom_sections"] if s["id"] == custom_id),
                    "Custom section",
                )
            sections.append({"section_key": key, "label": label, "visible": bool(item.get("visible", True))})
    if not sections:
        sections = [
            {"section_key": key, "label": SECTION_LABELS[key], "visible": True} for key in SECTION_KEYS
        ]
    for key in SECTION_KEYS:
        if key not in seen:
            sections.append({"section_key": key, "label": SECTION_LABELS[key], "visible": False})

    import json

    if len(json.dumps(doc)) > MAX_CONTENT_BYTES:
        errors.append("Resume content is too large to save. Remove some sections or shorten text.")

    return doc, errors, sections


def safe_template(value: Any) -> str:
    from database.repo import TEMPLATES

    value = str(value or "").strip().lower()
    return value if value in TEMPLATES else "classic"


def clean_job_payload(payload: Any) -> tuple[dict, list[str]]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return {}, ["Invalid job payload."]
    data = {
        "title": clean_str(payload.get("title"), 160),
        "company": clean_str(payload.get("company"), 160),
        "url": clean_str(payload.get("url"), 500),
        "description": clean_str(payload.get("description"), 20_000),
    }
    if data["url"] and not URL_RE.match(data["url"]):
        errors.append("Job URL must start with http:// or https://")
    if len(data["description"]) < 40:
        errors.append("Paste at least a few lines of the job description (40+ characters).")
    return data, errors
