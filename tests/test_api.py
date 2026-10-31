"""Flask API integration tests: profile, analysis, autosave, exports and SSRF."""

from __future__ import annotations

import json


def _profile_payload():
    return {
        "full_name": "Riya Verma",
        "headline": "Final-year IT student",
        "email": "riya.verma@example.com",
        "phone": "+91 98888 77777",
        "location": "Pune, India",
        "linkedin": "https://www.linkedin.com/in/riya-demo",
        "github": "https://github.com/riya-demo",
        "summary": "IT student who builds Flask tools and enjoys testing.",
        "skills": "Python, Flask, SQL, Git, Docker",
        "education": [
            {
                "institution": "Pune Institute of Technology",
                "degree": "B.E.",
                "field": "Information Technology",
                "start_date": "2021",
                "end_date": "2025",
                "score": "CGPA 8.4/10",
                "location": "Pune",
            }
        ],
        "projects": [
            {
                "name": "Library Desk",
                "tech": "Flask, SQLite",
                "link": "https://github.com/riya-demo/library-desk",
                "description": "Built a Flask app for library issue and return tracking.\nWrote unit tests for the fine calculation.",
            }
        ],
        "experience": [],
        "certifications": [],
        "achievements": ["Runner-up, inter-college coding contest 2024"],
    }


JOB_TEXT = """Software Engineer Intern — Backend
Requirements
- Strong Python and SQL skills
- Experience building REST APIs with Flask
- Familiarity with Docker and Git
- Understanding of unit testing
Preferred
- Exposure to Kubernetes
- Experience with TypeScript
- Bachelor's degree in Computer Science or related field
"""


def test_health_and_ai_status(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.get_json()
    assert body["ok"] is True
    assert body["ai_configured"] is False
    assert client.get("/api/ai/status").get_json()["ai"]["configured"] is False


def test_pages_render(client):
    for path in ("/", "/dashboard", "/profile", "/builder", "/matcher", "/templates", "/history", "/settings"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert b"ResumeIQ" in response.data


def test_save_and_read_profile(client):
    response = client.post("/api/profile", json=_profile_payload())
    assert response.status_code == 200
    body = response.get_json()
    assert body["profile"]["full_name"] == "Riya Verma"
    assert body["profile"]["skills"] == ["Python", "Flask", "SQL", "Git", "Docker"]
    assert body["completeness"] > 0

    fetched = client.get("/api/profile").get_json()
    assert fetched["profile"]["projects"][0]["name"] == "Library Desk"
    assert fetched["profile"]["education"][0]["institution"] == "Pune Institute of Technology"


def test_profile_validation_rejects_bad_email(client):
    payload = _profile_payload()
    payload["email"] = "not-an-email"
    response = client.post("/api/profile", json=payload)
    assert response.status_code == 400
    body = response.get_json()
    assert body["ok"] is False
    assert "Email" in body["error"]


def test_profile_validation_rejects_bad_url(client):
    payload = _profile_payload()
    payload["linkedin"] = "javascript:alert(1)"
    response = client.post("/api/profile", json=payload)
    assert response.status_code == 400


def test_analyze_job_and_persist_match(client):
    client.post("/api/profile", json=_profile_payload())
    response = client.post(
        "/api/jobs/analyze",
        json={"title": "Backend Intern", "company": "Acme", "description": JOB_TEXT},
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["ok"] is True
    assert 0 <= body["match"]["score"] <= 100
    assert "Python" in body["analysis"]["required_skills"]
    assert "Kubernetes" in body["analysis"]["preferred_skills"]
    assert "description" not in body["analysis"]
    assert body["job_id"]

    # The analysis can be reloaded by id.
    reloaded = client.get("/api/jobs/%s" % body["job_id"]).get_json()
    assert reloaded["match"]["score"] == body["match"]["score"]
    assert reloaded["job"]["description"].startswith("Software Engineer Intern")


def test_analyze_requires_description(client):
    response = client.post("/api/jobs/analyze", json={"description": "too short"})
    assert response.status_code == 400
    assert response.get_json()["ok"] is False


def test_resume_creation_and_autosave(client):
    client.post("/api/profile", json=_profile_payload())
    created = client.post("/api/resumes", json={}).get_json()
    resume_id = created["resume_id"]

    resume = client.get("/api/resumes/%s" % resume_id).get_json()["resume"]
    content = resume["content"]
    content["summary"] = "Edited inside the builder."
    content["skills"] = ["Python", "Flask"]
    sections = list(reversed(resume["sections"]))
    sections[0]["visible"] = False

    saved = client.put(
        "/api/resumes/%s" % resume_id,
        json={"title": "Backend version", "template": "modern", "content": content, "sections": sections},
    )
    assert saved.status_code == 200
    body = saved.get_json()
    assert body["ok"] is True

    reloaded = client.get("/api/resumes/%s" % resume_id).get_json()["resume"]
    assert reloaded["title"] == "Backend version"
    assert reloaded["template"] == "modern"
    assert reloaded["content"]["summary"] == "Edited inside the builder."
    assert [section["section_key"] for section in reloaded["sections"]] == [
        section["section_key"] for section in sections
    ]
    assert reloaded["sections"][0]["visible"] is False


def test_autosave_validates_content(client):
    client.post("/api/profile", json=_profile_payload())
    resume_id = client.post("/api/resumes", json={}).get_json()["resume_id"]
    resume = client.get("/api/resumes/%s" % resume_id).get_json()["resume"]
    resume["content"]["basics"]["email"] = "broken-email"

    response = client.put(
        "/api/resumes/%s" % resume_id,
        json={"content": resume["content"], "sections": resume["sections"]},
    )
    assert response.status_code == 400
    assert "Email" in response.get_json()["error"]


def test_tailor_requires_analysed_job(client):
    client.post("/api/profile", json=_profile_payload())
    resume_id = client.post("/api/resumes", json={}).get_json()["resume_id"]
    response = client.post("/api/resumes/%s/tailor" % resume_id, json={})
    assert response.status_code == 400
    assert response.get_json()["needs_job"] is True


def test_tailor_returns_labelled_fallback(client):
    client.post("/api/profile", json=_profile_payload())
    job = client.post(
        "/api/jobs/analyze",
        json={"title": "Backend Intern", "company": "Acme", "description": JOB_TEXT},
    ).get_json()
    created = client.post("/api/resumes", json={"job_id": job["job_id"]}).get_json()
    response = client.post("/api/resumes/%s/tailor" % created["resume_id"], json={})

    assert response.status_code == 200
    body = response.get_json()
    assert body["ok"] is True
    assert body["tailoring"]["live"] is False
    assert body["tailoring"]["mode"] == "fallback"
    assert body["job"]["id"] == job["job_id"]


def test_exports_are_real_files(client):
    client.post("/api/profile", json=_profile_payload())
    resume_id = client.post("/api/resumes", json={}).get_json()["resume_id"]

    pdf = client.get("/export/%s/pdf" % resume_id)
    assert pdf.status_code == 200
    assert pdf.mimetype == "application/pdf"
    assert pdf.data.startswith(b"%PDF")
    assert "attachment" in pdf.headers.get("Content-Disposition", "")

    docx = client.get("/export/%s/docx" % resume_id)
    assert docx.status_code == 200
    assert docx.data.startswith(b"PK")
    assert "wordprocessingml" in docx.mimetype

    history = client.get("/history")
    assert b"wordprocessingml" not in history.data  # page renders, not binary
    assert b"aarav" not in history.data.lower()
    assert b"riya-verma" in history.data.lower()

    missing = client.get("/export/9999/pdf")
    assert missing.status_code == 302


def test_ssrf_and_scheme_guards(client):
    loopback = client.post("/api/jobs/fetch", json={"url": "http://127.0.0.1/health"})
    assert loopback.status_code == 400
    assert "private or internal" in loopback.get_json()["error"]

    unusual_port = client.post("/api/jobs/fetch", json={"url": "http://example.com:8080/jobs"})
    assert unusual_port.status_code == 400
    assert "port" in unusual_port.get_json()["error"].lower()

    file_scheme = client.post("/api/jobs/fetch", json={"url": "file:///etc/passwd"})
    assert file_scheme.status_code == 400
    assert "http" in file_scheme.get_json()["error"].lower()

    localhost = client.post("/api/jobs/fetch", json={"url": "http://localhost:22/"})
    assert localhost.status_code == 400


def test_demo_load_and_reset(client):
    demo = client.post("/api/demo/load", json={})
    assert demo.status_code == 200
    body = demo.get_json()
    assert body["score"] > 0
    assert body["resume_id"]

    profile = client.get("/api/profile").get_json()["profile"]
    assert profile["full_name"] == "Aarav Sharma"

    reset = client.post("/api/data/reset", json={})
    assert reset.status_code == 200
    assert client.get("/api/profile").get_json()["profile"]["full_name"] == ""
    assert client.get("/api/resumes").get_json()["resumes"] == []


def test_404_api_and_page(client):
    api_response = client.get("/api/nope")
    assert api_response.status_code == 404
    assert api_response.get_json()["ok"] is False
    page = client.get("/nope")
    assert page.status_code == 404


def test_api_responses_are_not_cached(client):
    response = client.get("/api/profile")
    assert response.headers.get("Cache-Control") == "no-store"
