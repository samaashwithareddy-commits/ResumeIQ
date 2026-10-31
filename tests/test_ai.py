"""AI failure handling and anti-fabrication guarantees."""

from __future__ import annotations

import pytest

from services import ai_service
from services.ai_service import (
    AIUnavailable,
    deterministic_tailoring,
    tailor_resume,
    validate_ai_output,
)
from services.matcher import build_candidate


def _payload(**overrides):
    payload = {
        "summary": {
            "text": "Backend-focused final-year student with hands-on Flask and SQL experience.",
            "rationale": "Emphasised backend work.",
        },
        "bullet_improvements": [
            {
                "target": "experience",
                "index": 0,
                "original": "Built three Flask endpoints for an internal reporting tool and documented them for the analytics team.",
                "improved": "Built three Flask endpoints for an internal reporting tool and documented them for the analytics team, improving clarity for analysts.",
                "rationale": "Clarifies the outcome without adding new facts.",
            }
        ],
        "keywords": [
            {"keyword": "Python", "present_in_profile": True},
            {"keyword": "Kubernetes", "present_in_profile": False},
        ],
        "action_verbs": ["Built", "Designed", "Optimised"],
        "notes": ["Kept all facts unchanged."],
    }
    payload.update(overrides)
    return payload


def test_valid_rewrite_is_accepted_but_requires_confirmation(demo_profile, sample_analysis):
    result = validate_ai_output(demo_profile, sample_analysis, _payload())
    assert len(result["bullet_improvements"]) == 1
    suggestion = result["bullet_improvements"][0]
    assert suggestion["requires_confirmation"] is True
    assert suggestion["status"] == "ready"
    assert "Flask" in suggestion["improved"]
    assert result["rejected"] == []
    assert result["summary"]["status"] == "ready"


def test_fabricated_metric_is_rejected(demo_profile, sample_analysis):
    payload = _payload()
    payload["bullet_improvements"][0]["improved"] = (
        "Built three Flask endpoints for an internal reporting tool and cut page load by 45%."
    )
    result = validate_ai_output(demo_profile, sample_analysis, payload)

    assert result["bullet_improvements"] == []
    assert len(result["rejected"]) == 1
    assert "number" in result["rejected"][0]["reason"].lower()


def test_fabricated_skill_is_rejected(demo_profile, sample_analysis):
    payload = _payload()
    payload["bullet_improvements"][0]["improved"] = (
        "Built three Flask endpoints and deployed them to Kubernetes for the analytics team."
    )
    result = validate_ai_output(demo_profile, sample_analysis, payload)

    assert result["bullet_improvements"] == []
    assert "kubernetes" in result["rejected"][0]["reason"].lower()


def test_unknown_original_bullet_is_rejected(demo_profile, sample_analysis):
    payload = _payload()
    payload["bullet_improvements"][0]["original"] = "Led a team of nine engineers across three continents."
    result = validate_ai_output(demo_profile, sample_analysis, payload)

    assert result["bullet_improvements"] == []
    assert "not found" in result["rejected"][0]["reason"].lower()


def test_summary_with_new_skill_is_flagged(demo_profile, sample_analysis):
    payload = _payload()
    payload["summary"]["text"] = (
        "Backend student experienced in Python, Flask, Kubernetes and Terraform."
    )
    result = validate_ai_output(demo_profile, sample_analysis, payload)

    summary = result["summary"]
    assert summary["status"] == "needs_confirmation"
    assert "Kubernetes" in summary["fabricated_terms"]
    assert "Terraform" in summary["fabricated_terms"]
    assert summary["text"]  # shown to the user, but never auto-applied


def test_model_cannot_dictate_skills_to_add(demo_profile, sample_analysis):
    payload = _payload(skills_to_add=["Kubernetes", "Terraform"])
    result = validate_ai_output(demo_profile, sample_analysis, payload)
    assert any("adding skills is never allowed" in item["reason"].lower() for item in result["rejected"])
    assert "Kubernetes" not in result["bullet_improvements"][0]["improved"]


def test_missing_key_returns_labelled_fallback(demo_profile, sample_analysis, monkeypatch):
    monkeypatch.delenv("FEATHERLESS_API_KEY", raising=False)
    result = tailor_resume(demo_profile, sample_analysis)

    assert result["mode"] == "fallback"
    assert result["live"] is False
    assert "No Featherless API key" in (result["error"] or "")
    assert result["summary"] is not None
    assert result["bullet_improvements"]
    for suggestion in result["bullet_improvements"]:
        assert suggestion["requires_confirmation"] is True


def test_network_failure_falls_back_without_pretending(demo_profile, sample_analysis, monkeypatch):
    monkeypatch.setenv("FEATHERLESS_API_KEY", "test-key-not-real")

    def boom(*args, **kwargs):
        raise AIUnavailable("Featherless AI returned HTTP 503. Service unavailable.")

    monkeypatch.setattr(ai_service, "call_featherless", boom)
    result = tailor_resume(demo_profile, sample_analysis)

    assert result["mode"] == "fallback"
    assert result["live"] is False
    assert "HTTP 503" in result["error"]
    assert "deterministic" in result["reason"].lower()
    assert result["bullet_improvements"]  # fallback still useful


def test_invalid_json_falls_back(demo_profile, sample_analysis, monkeypatch):
    monkeypatch.setenv("FEATHERLESS_API_KEY", "test-key-not-real")
    monkeypatch.setattr(ai_service, "call_featherless", lambda *a, **k: "not json at all")
    result = tailor_resume(demo_profile, sample_analysis)
    assert result["mode"] == "fallback"
    assert result["live"] is False
    assert "json" in (result["error"] or "").lower()


def test_live_path_validates_output(demo_profile, sample_analysis, monkeypatch):
    monkeypatch.setenv("FEATHERLESS_API_KEY", "test-key-not-real")
    monkeypatch.setattr(
        ai_service,
        "call_featherless",
        lambda *args, **kwargs: '```json\n' + __import__("json").dumps(_payload()) + '\n```',
    )
    result = tailor_resume(demo_profile, sample_analysis)
    assert result["mode"] == "live"
    assert result["live"] is True
    assert len(result["bullet_improvements"]) == 1


def test_deterministic_fallback_never_adds_skills(demo_profile, sample_analysis):
    result = deterministic_tailoring(demo_profile, sample_analysis)
    candidate = build_candidate(demo_profile)
    known = {name.lower() for name in candidate["skills"]}
    known_text = " ".join(known)

    for suggestion in result["bullet_improvements"]:
        for skill in ai_service.find_skills(suggestion["improved"]):
            assert skill.lower() in known_text or skill in candidate["skills"], skill

    if result["summary"]:
        for skill in ai_service.find_skills(result["summary"]["text"]):
            assert skill in candidate["skills"], skill


def test_fallback_can_be_forced_even_with_key(demo_profile, sample_analysis, monkeypatch):
    monkeypatch.setenv("FEATHERLESS_API_KEY", "test-key-not-real")

    def should_not_run(*args, **kwargs):
        raise AssertionError("Live AI must not be called when force_fallback is set")

    monkeypatch.setattr(ai_service, "call_featherless", should_not_run)
    result = tailor_resume(demo_profile, sample_analysis, force_fallback=True)
    assert result["mode"] == "fallback"
    assert result["error"] is None


def test_tailoring_uses_resume_document_bullets(demo_profile, sample_analysis):
    document = {
        "basics": {"full_name": "Aarav Sharma", "headline": "Backend student"},
        "summary": "Custom edited summary.",
        "skills": ["Python", "Flask"],
        "education": [],
        "projects": [],
        "experience": [
            {
                "role": "Backend Intern",
                "company": "Zeta",
                "bullets": ["Worked on internal reporting jobs and kept the documentation current."],
            }
        ],
        "certifications": [],
        "achievements": [],
        "custom_sections": [],
    }
    payload = {
        "summary": None,
        "bullet_improvements": [
            {
                "target": "experience",
                "index": 0,
                "original": "Worked on internal reporting jobs and kept the documentation current.",
                "improved": "Built and maintained internal reporting jobs and kept the documentation current.",
                "rationale": "Stronger verb.",
            }
        ],
        "keywords": [],
        "action_verbs": ["Built"],
        "notes": [],
    }
    result = validate_ai_output(demo_profile, sample_analysis, payload, document=document)
    assert len(result["bullet_improvements"]) == 1
    assert result["bullet_improvements"][0]["original"].startswith("Worked on internal")
