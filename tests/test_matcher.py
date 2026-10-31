"""Deterministic job parsing and scoring tests."""

from __future__ import annotations

from services.matcher import (
    DEFAULT_WEIGHTS,
    build_candidate,
    find_skills,
    parse_job_description,
    score_match,
)

SIMPLE_PROFILE = {
    "full_name": "Test Candidate",
    "headline": "Backend developer",
    "summary": "Backend developer who builds Flask APIs.",
    "skills": ["Python", "Flask", "SQL", "Git"],
    "education": [
        {
            "institution": "Test University",
            "degree": "B.Tech",
            "field": "Computer Science",
            "start_date": "2021",
            "end_date": "2025",
            "score": "CGPA 8.0/10",
        }
    ],
    "projects": [
        {
            "name": "Notes API",
            "tech": "Python, Flask, SQLite",
            "description": "Built a Flask REST API for notes.\nWrote unit tests for the endpoints.",
        }
    ],
    "experience": [],
    "certifications": [],
    "achievements": [],
}


def test_extracts_required_and_preferred_skills(sample_analysis):
    required = set(sample_analysis["required_skills"])
    preferred = set(sample_analysis["preferred_skills"])

    assert "Python" in required
    assert "Flask" in required
    assert "PostgreSQL" in required
    assert "Docker" in required
    assert "AWS" in preferred
    assert "Kubernetes" in preferred
    # A skill listed under both sections is only counted as required.
    assert not preferred & required
    assert "Communication" in sample_analysis["soft_skills"]
    assert sample_analysis["education_level"] == 3
    assert sample_analysis["required_years"] == 0.0
    assert any("responsib" in item.lower() or "build" in item.lower() for item in sample_analysis["responsibilities"])


def test_analysis_never_invents_skills_not_in_text():
    description = "We need a Python developer who enjoys clear documentation and code review."
    analysis = parse_job_description(description, "Backend Intern", "Example Co")
    text = description.lower().replace(".", " ")
    for skill in analysis["required_skills"] + analysis["preferred_skills"]:
        canonical_tokens = [token for token in skill.lower().split() if len(token) > 2]
        assert any(token in text for token in canonical_tokens), f"{skill} was not in the description"


def test_score_is_deterministic_and_weighted(demo_profile, sample_analysis):
    first = score_match(demo_profile, sample_analysis)
    second = score_match(demo_profile, sample_analysis)

    assert first["score"] == second["score"]
    assert 0 <= first["score"] <= 100
    assert sum(first["weights"].values()) == sum(DEFAULT_WEIGHTS.values())

    total = sum(category["points"] for category in first["categories"])
    assert abs(total - first["score"]) <= 0.2
    assert first["categories"][0]["key"] == "required"
    assert first["categories"][0]["status"] == "scored"


def test_missing_skill_and_keyword_detection():
    job = """
    Requirements
    - Strong Rust and Kubernetes experience
    - Experience with distributed systems and performance optimization
    - Familiarity with Terraform
    """
    analysis = parse_job_description(job, "Platform Engineer", "Example")
    match = score_match(SIMPLE_PROFILE, analysis)

    assert "Rust" in match["missing_skills"]
    assert "Kubernetes" in match["missing_skills"]
    assert "Rust" not in match["matched_skills"]
    assert any("Distributed Systems" == keyword or "distributed" in keyword.lower() for keyword in match["keywords"]["missing"])


def test_partial_skill_match_counts_half():
    profile = dict(SIMPLE_PROFILE)
    profile["skills"] = ["React"]
    analysis = parse_job_description(
        "Requirements\n- Build interfaces with React Native for our mobile app.\n",
        "Mobile Intern",
        "Example",
    )
    match = score_match(profile, analysis)
    partial = {(item["skill"], item["matched_with"]) for item in match["partial_skills"]}
    assert ("React Native", "React") in partial
    # Only one required skill is extracted (React Native), counted as half credit.
    assert analysis["required_skills"] == ["React Native"]
    required = next(category for category in match["categories"] if category["key"] == "required")
    assert abs(required["score"] - 0.5) <= 0.01


def test_inapplicable_categories_are_renormalised():
    job = "Requirements\n- Python programming for backend services\n- SQL database design and reporting work\n"
    analysis = parse_job_description(job, "Junior Developer", "Example")
    profile = {
        "full_name": "Student",
        "skills": ["Python"],
        "education": [],
        "projects": [],
        "experience": [],
        "certifications": [],
        "achievements": [],
        "summary": "",
    }
    match = score_match(profile, analysis)

    statuses = {category["key"]: category["status"] for category in match["categories"]}
    assert statuses["required"] == "scored"
    assert statuses["preferred"] == "not_applicable"
    assert statuses["projects_experience"] == "not_applicable"
    assert statuses["education_other"] == "not_applicable"
    assert match["effective_weights"] == {"required": 100.0}
    assert match["score"] == 50.0
    assert match["renormalised"] is True
    assert any("redistributed" in line for line in match["explanation"])


def test_keyword_similarity_is_separate_from_score():
    job = "Requirements\n- Python\n- Build reliable data pipelines for analytics\n"
    analysis = parse_job_description(job, "Data Intern", "Example")
    match = score_match(SIMPLE_PROFILE, analysis)
    assert 0 <= match["keywords"]["similarity"] <= 100
    assert "data pipelines" not in [line.lower() for line in match["explanation"]]


def test_build_candidate_tracks_skill_sources():
    candidate = build_candidate(SIMPLE_PROFILE)
    assert "Python" in candidate["skills"]
    assert "SQL" in candidate["skills"]
    assert "Skills" in candidate["skill_sources"]["Python"]
    assert any(source.startswith("Project:") for source in candidate["skill_sources"]["Flask"])
    assert candidate["has_projects"] is True
    assert candidate["has_experience"] is False


def test_find_skills_respects_word_boundaries():
    found = find_skills("Strong JavaScript and TypeScript skills for web interfaces.")
    assert "JavaScript" in found
    assert "TypeScript" in found
    assert "Java" not in found


def test_container_alias_does_not_double_count():
    found = find_skills("We build interfaces with React Native for iOS and Android.")
    assert "React Native" in found
    assert "React" not in found


def test_no_technical_skills_is_handled():
    analysis = parse_job_description(
        "This internship is about learning how a product team operates day to day. "
        "You will attend planning sessions and shadow engineers.",
        "Product Intern",
        "Example",
    )
    match = score_match(SIMPLE_PROFILE, analysis)
    assert 0 <= match["score"] <= 100
    assert match["categories"][0]["status"] == "not_applicable"
    assert any("at least" not in line for line in match["explanation"])
