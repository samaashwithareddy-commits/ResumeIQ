"""SQLite persistence, profile round-trips and resume section ordering."""

from __future__ import annotations

from database import repo
from database.seed import load_demo


def test_profile_round_trip(db_path, demo_profile):
    saved = repo.save_profile(db_path, demo_profile)
    assert saved["full_name"] == demo_profile["full_name"]
    assert saved["skills"] == demo_profile["skills"]

    reloaded = repo.get_profile(db_path)
    assert [item["institution"] for item in reloaded["education"]] == [
        item["institution"] for item in demo_profile["education"]
    ]
    assert [project["name"] for project in reloaded["projects"]] == [
        project["name"] for project in demo_profile["projects"]
    ]
    assert reloaded["experience"][0]["company"] == "Zeta Innovations"
    assert reloaded["certifications"][0]["name"] == "AWS Certified Cloud Practitioner"
    assert reloaded["achievements"][0].startswith("Finalist")


def test_profile_save_replaces_repeating_entries(db_path, demo_profile):
    repo.save_profile(db_path, demo_profile)
    demo_profile["education"] = demo_profile["education"][:1]
    demo_profile["skills"] = ["Python", "SQL"]
    demo_profile["projects"] = []
    repo.save_profile(db_path, demo_profile)

    profile = repo.get_profile(db_path)
    assert len(profile["education"]) == 1
    assert profile["skills"] == ["Python", "SQL"]
    assert profile["projects"] == []


def test_sql_injection_is_stored_as_text(db_path, demo_profile):
    demo_profile["full_name"] = "Robert'); DROP TABLE resumes;--"
    repo.save_profile(db_path, demo_profile)

    profile = repo.get_profile(db_path)
    assert profile["full_name"] == "Robert'); DROP TABLE resumes;--"
    # The resumes table must still exist and be usable.
    resume_id = repo.create_resume_from_profile(db_path, profile, "Draft")
    assert repo.get_resume(db_path, resume_id)["id"] == resume_id


def test_resume_creation_and_section_order(db_path, demo_profile):
    profile = repo.save_profile(db_path, demo_profile)
    resume_id = repo.create_resume_from_profile(db_path, profile, "Tailored draft", template="modern")

    resume = repo.get_resume(db_path, resume_id)
    assert resume["template"] == "modern"
    assert resume["content"]["basics"]["full_name"] == "Aarav Sharma"
    assert resume["content"]["projects"][0]["bullets"][0].startswith("Built a MERN application")
    keys = [section["section_key"] for section in resume["sections"]]
    assert keys == ["summary", "skills", "education", "projects", "experience", "certifications", "achievements"]

    # Move projects first, hide certifications, add a custom section.
    content = resume["content"]
    content["custom_sections"] = [{"id": "vol1", "title": "Volunteering", "bullets": ["Taught Python to first-years."]}]
    new_sections = [
        {"section_key": "projects", "label": "Projects", "visible": True},
        {"section_key": "education", "label": "Education", "visible": True},
        {"section_key": "summary", "label": "Professional Summary", "visible": True},
        {"section_key": "skills", "label": "Skills", "visible": True},
        {"section_key": "custom:vol1", "label": "Volunteering", "visible": True},
        {"section_key": "certifications", "label": "Certifications", "visible": False},
        {"section_key": "achievements", "label": "Achievements", "visible": True},
        {"section_key": "experience", "label": "Experience", "visible": True},
    ]
    assert repo.update_resume(
        db_path,
        resume_id,
        {"content": content, "sections": new_sections, "title": "Edited draft"},
    )

    reloaded = repo.get_resume(db_path, resume_id)
    assert [section["section_key"] for section in reloaded["sections"]] == [
        section["section_key"] for section in new_sections
    ]
    hidden = next(section for section in reloaded["sections"] if section["section_key"] == "certifications")
    assert hidden["visible"] is False
    assert reloaded["title"] == "Edited draft"
    assert reloaded["content"]["custom_sections"][0]["title"] == "Volunteering"


def test_jobs_matches_and_exports_persist(db_path, demo_profile, sample_analysis):
    profile = repo.save_profile(db_path, demo_profile)
    job_id = repo.save_job(db_path, "Backend Intern", "Northwind", "", "x" * 80, sample_analysis)
    repo.save_match(db_path, job_id, None, 72.5, {"score": 72.5, "label": "Strong alignment"})

    latest = repo.latest_match(db_path)
    assert latest["job_id"] == job_id
    assert latest["score"] == 72.5
    assert latest["breakdown"]["label"] == "Strong alignment"

    by_job = repo.latest_match_for_job(db_path, job_id)
    assert by_job["breakdown"]["score"] == 72.5

    resume_id = repo.create_resume_from_profile(db_path, profile)
    repo.record_export(db_path, resume_id, "aarav-classic.pdf", "pdf", "classic")
    exports = repo.list_exports(db_path)
    assert exports[0]["filename"] == "aarav-classic.pdf"
    assert exports[0]["resume_title"] == "Aarav Sharma — Resume"


def test_demo_loader_creates_full_workflow(db_path):
    result = load_demo(db_path)
    assert result["score"] > 0
    assert repo.get_setting(db_path, "demo_loaded") == "1"
    resume = repo.get_resume(db_path, result["resume_id"])
    assert resume["job_id"] == result["job_id"]
    assert resume["content"]["basics"]["full_name"] == "Aarav Sharma"
    assert repo.latest_match(db_path)["score"] == result["score"]


def test_reset_clears_user_data(db_path, demo_profile):
    repo.save_profile(db_path, demo_profile)
    load_demo(db_path)
    repo.reset_all(db_path)

    profile = repo.get_profile(db_path)
    assert profile["full_name"] == ""
    assert repo.list_resumes(db_path) == []
    assert repo.list_jobs(db_path) == []
    assert repo.list_exports(db_path) == []
