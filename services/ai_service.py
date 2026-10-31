"""Featherless AI tailoring with a hard anti-fabrication guard.

The model is only allowed to *rephrase facts that already exist in the profile*.
Every response passes through :func:`validate_ai_output`, which rejects bullets
that introduce new numbers, new skills or content that is not present in the
source document. If the API is unavailable the caller receives a clearly
labelled deterministic fallback — never a fake "success".
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Any

import requests

from services.matcher import build_candidate, find_skills, normalize

DEFAULT_BASE_URL = "https://api.featherless.ai/v1"
DEFAULT_MODEL = "Qwen/Qwen2.5-7B-Instruct"
MAX_BULLET_LEN = 420
MAX_ITEMS = 12

ACTION_VERB_SUGGESTIONS = [
    "Architected",
    "Automated",
    "Built",
    "Designed",
    "Developed",
    "Implemented",
    "Improved",
    "Integrated",
    "Led",
    "Optimised",
    "Streamlined",
    "Tested",
]

WEAK_OPENERS = {
    "worked on": "Built",
    "worked with": "Collaborated with",
    "helped with": "Supported",
    "helped": "Supported",
    "responsible for": "Owned",
    "was responsible for": "Owned",
    "assisted with": "Contributed to",
    "assisted": "Contributed to",
    "participated in": "Collaborated on",
    "involved in": "Contributed to",
    "used": "Applied",
    "made": "Created",
    "did": "Delivered",
    "handled": "Managed",
}

DISCLAIMER = (
    "Suggestions only rephrase facts already in your profile. Nothing is added to your resume "
    "automatically — review every item and confirm it is true before applying. ResumeIQ cannot "
    "guarantee interviews, selection or ATS success."
)

SYSTEM_PROMPT = """You are ResumeIQ's resume tailoring assistant. You rewrite existing resume content to match a job description.

HARD RULES (breaking them is a failure):
1. NEVER invent degrees, employers, internships, job titles, projects, certifications, skills, tools, metrics, percentages, dates or achievements.
2. Only rephrase facts present in the PROFILE block. Every bullet you improve must keep the same factual content.
3. NEVER add a skill, tool or technology that is not in the profile, even if the job asks for it. List the gap under "keywords" with present_in_profile=false instead.
4. NEVER add numbers, percentages or scale that do not appear in the original bullet or the profile.
5. Do not claim ATS success, hiring probability or guaranteed selection.
6. Keep bullets one or two lines, start with a strong past-tense action verb, and stay under 300 characters.
7. Return STRICT JSON only, no markdown fences, matching this schema:

{
  "summary": {"text": "tailored 2-3 sentence summary using only profile facts", "rationale": "what was re-emphasised"},
  "bullet_improvements": [
    {"target": "project" | "experience", "index": 0, "original": "exact existing bullet", "improved": "rewritten bullet", "rationale": "why"}
  ],
  "keywords": [{"keyword": "term from the job description", "present_in_profile": true, "note": "where it appears or that it is missing"}],
  "action_verbs": ["StrongVerb", "AnotherVerb"],
  "notes": ["short, factual note"]
}"""


class AIUnavailable(Exception):
    """The live AI request could not be completed."""


def ai_status() -> dict[str, Any]:
    key = (os.environ.get("FEATHERLESS_API_KEY") or "").strip()
    return {
        "configured": bool(key),
        "provider": "Featherless AI",
        "model": (os.environ.get("FEATHERLESS_MODEL") or DEFAULT_MODEL).strip(),
        "base_url": (os.environ.get("FEATHERLESS_BASE_URL") or DEFAULT_BASE_URL).strip(),
    }


# ---------------------------------------------------------------------------
# Source facts
# ---------------------------------------------------------------------------
def _document_to_facts(document: dict | None) -> dict:
    """Convert a resume document into the profile-like shape used for checks."""
    if not document:
        return {}
    basics = document.get("basics") or {}
    return {
        "full_name": basics.get("full_name", ""),
        "headline": basics.get("headline", ""),
        "email": basics.get("email", ""),
        "phone": basics.get("phone", ""),
        "location": basics.get("location", ""),
        "linkedin": basics.get("linkedin", ""),
        "github": basics.get("github", ""),
        "summary": document.get("summary", ""),
        "skills": document.get("skills", []),
        "education": document.get("education", []),
        "projects": [
            {
                "name": item.get("name", ""),
                "tech": item.get("tech", ""),
                "description": "\n".join(item.get("bullets", [])),
            }
            for item in document.get("projects", [])
        ],
        "experience": [
            {
                "role": item.get("role", ""),
                "company": item.get("company", ""),
                "description": "\n".join(item.get("bullets", [])),
            }
            for item in document.get("experience", [])
        ],
        "certifications": document.get("certifications", []),
        "achievements": document.get("achievements", []),
    }


def _bullet_sources(facts: dict) -> list[dict]:
    """Flatten project/experience bullets with stable target + index."""
    sources: list[dict] = []
    for index, project in enumerate(facts.get("projects", []) or []):
        label = project.get("name") or f"Project {index + 1}"
        for bullet in _split_bullets(project.get("description", "")):
            sources.append(
                {"target": "project", "index": index, "location": f"Project — {label}", "original": bullet}
            )
    for index, job in enumerate(facts.get("experience", []) or []):
        label = " at ".join(bit for bit in (job.get("role"), job.get("company")) if bit) or f"Experience {index + 1}"
        for bullet in _split_bullets(job.get("description", "")):
            sources.append(
                {"target": "experience", "index": index, "location": f"Experience — {label}", "original": bullet}
            )
    return sources


def _split_bullets(text: str) -> list[str]:
    if not text:
        return []
    items = []
    for line in str(text).splitlines():
        cleaned = re.sub(r"^\s*[•\-\*–]\s*", "", line).strip()
        if cleaned:
            items.append(cleaned)
    return items


def _numbers(text: str) -> set[str]:
    return set(re.findall(r"\d+(?:\.\d+)?", text or ""))


def _facts_text(facts: dict) -> str:
    parts = [
        str(facts.get("summary", "") or ""),
        " ".join(str(s) for s in facts.get("skills", []) or []),
        " ".join(
            " ".join(str(p.get(key, "")) for key in ("name", "tech", "description"))
            for p in facts.get("projects", []) or []
        ),
        " ".join(
            " ".join(str(p.get(key, "")) for key in ("role", "company", "description"))
            for p in facts.get("experience", []) or []
        ),
        " ".join(str(a) for a in facts.get("achievements", []) or []),
        " ".join(
            " ".join(str(p.get(key, "")) for key in ("degree", "field", "institution", "score"))
            for p in facts.get("education", []) or []
        ),
        " ".join(
            " ".join(str(p.get(key, "")) for key in ("name", "issuer"))
            for p in facts.get("certifications", []) or []
        ),
    ]
    return " ".join(parts)


def _candidate_skills(profile: dict, facts: dict) -> set[str]:
    skills = set(build_candidate(profile).get("skills", set()))
    if facts:
        skills |= set(build_candidate(facts).get("skills", set()))
        for raw in facts.get("skills", []) or []:
            skills.add(str(raw).strip())
    return {s for s in skills if s}


# ---------------------------------------------------------------------------
# Validation of model output
# ---------------------------------------------------------------------------
def validate_ai_output(
    profile: dict,
    analysis: dict,
    payload: dict,
    document: dict | None = None,
) -> dict[str, Any]:
    """Filter model output down to content that is factually supported."""
    facts = _document_to_facts(document) if document else profile
    if not facts:
        facts = profile
    candidate_skills = _candidate_skills(profile, facts)
    allowed_numbers = _numbers(_facts_text(profile)) | _numbers(_facts_text(facts))
    sources = _bullet_sources(facts)
    source_by_key = {
        (item["target"], item["index"], normalize(item["original"])): item for item in sources
    }
    profile_norm = normalize(_facts_text(facts))

    rejected: list[dict] = []

    # Summary ---------------------------------------------------------------
    summary = None
    raw_summary = payload.get("summary")
    if isinstance(raw_summary, dict):
        text = re.sub(r"\s+", " ", str(raw_summary.get("text", ""))).strip()
        rationale = str(raw_summary.get("rationale", "")).strip()[:300]
    elif isinstance(raw_summary, str):
        text = re.sub(r"\s+", " ", raw_summary).strip()
        rationale = ""
    else:
        text = ""
        rationale = ""
    if text:
        text = text[:900]
        fabricated_terms = sorted(s for s in find_skills(text) if s not in candidate_skills)
        new_numbers = sorted(_numbers(text) - allowed_numbers)
        issues = []
        if fabricated_terms:
            issues.append("mentions skills not found in your profile: " + ", ".join(fabricated_terms))
        if new_numbers:
            issues.append("adds numbers not found in your profile: " + ", ".join(new_numbers))
        summary = {
            "text": text,
            "rationale": rationale,
            "status": "needs_confirmation" if issues else "ready",
            "issues": issues,
            "fabricated_terms": fabricated_terms,
            "fabricated_metrics": new_numbers,
        }

    # Bullet improvements ---------------------------------------------------
    improvements: list[dict] = []
    raw_bullets = payload.get("bullet_improvements")
    if isinstance(raw_bullets, list):
        for item in raw_bullets:
            if not isinstance(item, dict):
                continue
            target = str(item.get("target", "")).strip().lower()
            try:
                index = int(item.get("index", -1))
            except (TypeError, ValueError):
                index = -1
            original = re.sub(r"\s+", " ", str(item.get("original", ""))).strip()
            improved = re.sub(r"\s+", " ", str(item.get("improved", ""))).strip()
            rationale = str(item.get("rationale", "")).strip()[:300]
            if not original or not improved or target not in ("project", "experience"):
                continue
            key = (target, index, normalize(original))
            if key not in source_by_key:
                rejected.append(
                    {
                        "location": target.title(),
                        "original": original[:300],
                        "improved": improved[:300],
                        "reason": "Discarded: the original bullet was not found in your resume, so it cannot be verified.",
                    }
                )
                continue
            if len(improved) > MAX_BULLET_LEN:
                rejected.append(
                    {
                        "location": source_by_key[key]["location"],
                        "original": original[:300],
                        "improved": improved[:300],
                        "reason": f"Discarded: the rewritten bullet is longer than {MAX_BULLET_LEN} characters.",
                    }
                )
                continue
            if normalize(improved) == normalize(original):
                continue

            new_numbers = _numbers(improved) - _numbers(original) - allowed_numbers
            if new_numbers:
                rejected.append(
                    {
                        "location": source_by_key[key]["location"],
                        "original": original[:300],
                        "improved": improved[:300],
                        "reason": "Discarded: it adds a number or metric that is not in your profile ("
                        + ", ".join(sorted(new_numbers))
                        + ").",
                    }
                )
                continue
            new_skills = [
                skill
                for skill in find_skills(improved)
                if skill not in find_skills(original) and skill not in candidate_skills
            ]
            if new_skills:
                rejected.append(
                    {
                        "location": source_by_key[key]["location"],
                        "original": original[:300],
                        "improved": improved[:300],
                        "reason": "Discarded: it claims a skill that is not in your profile ("
                        + ", ".join(sorted(new_skills))
                        + ").",
                    }
                )
                continue

            improvements.append(
                {
                    "target": target,
                    "index": index,
                    "location": source_by_key[key]["location"],
                    "original": original,
                    "improved": improved,
                    "rationale": rationale,
                    "status": "ready",
                    "requires_confirmation": True,
                }
            )
            if len(improvements) >= MAX_ITEMS:
                break

    # Keywords --------------------------------------------------------------
    keywords: list[dict] = []
    seen_keywords: set[str] = set()
    raw_keywords = payload.get("keywords")
    if isinstance(raw_keywords, list):
        for item in raw_keywords[:20]:
            if isinstance(item, dict):
                keyword = str(item.get("keyword", "")).strip()[:80]
                note = str(item.get("note", "")).strip()[:240]
            else:
                keyword = str(item).strip()[:80]
                note = ""
            if not keyword:
                continue
            key = keyword.lower()
            if key in seen_keywords:
                continue
            seen_keywords.add(key)
            present = normalize(keyword) in profile_norm or normalize(keyword) in normalize(
                " ".join(facts.get("skills", []) or [])
            )
            keywords.append(
                {
                    "keyword": keyword,
                    "present_in_profile": present,
                    "requires_confirmation": not present,
                    "note": note
                    or (
                        "Found in your profile."
                        if present
                        else "Not found in your profile — do not add it unless it is genuinely true."
                    ),
                }
            )

    # Action verbs ----------------------------------------------------------
    verbs: list[str] = []
    raw_verbs = payload.get("action_verbs")
    if isinstance(raw_verbs, list):
        for item in raw_verbs[:12]:
            verb = str(item).strip()
            if re.fullmatch(r"[A-Za-z][A-Za-z-]{2,20}", verb) and verb.lower() not in {
                "used", "helped", "worked", "made", "did", "was",
            }:
                if verb not in verbs:
                    verbs.append(verb)

    notes = []
    if isinstance(payload.get("notes"), list):
        notes = [str(n).strip()[:300] for n in payload["notes"][:6] if str(n).strip()]

    # The model is never allowed to dictate skills to add.
    new_skill_claims = payload.get("skills_to_add") or payload.get("new_skills")
    if new_skill_claims:
        rejected.append(
            {
                "location": "Model output",
                "original": "",
                "improved": ", ".join(str(s) for s in new_skill_claims)[:300] if isinstance(new_skill_claims, list) else str(new_skill_claims)[:300],
                "reason": "Discarded: adding skills is never allowed, even when the job description asks for them.",
            }
        )

    return {
        "summary": summary,
        "bullet_improvements": improvements,
        "keywords": keywords,
        "action_verbs": verbs or ACTION_VERB_SUGGESTIONS[:6],
        "rejected": rejected,
        "notes": notes,
    }


# ---------------------------------------------------------------------------
# Featherless call
# ---------------------------------------------------------------------------
def _build_messages(profile: dict, analysis: dict, facts: dict) -> list[dict]:
    profile_payload = {
        "basics": {
            key: profile.get(key, "")
            for key in ("full_name", "headline", "email", "phone", "location", "linkedin", "github")
        },
        "summary": facts.get("summary", profile.get("summary", "")),
        "skills": facts.get("skills", profile.get("skills", [])),
        "education": facts.get("education", profile.get("education", [])),
        "projects": facts.get("projects", profile.get("projects", [])),
        "experience": facts.get("experience", profile.get("experience", [])),
        "certifications": facts.get("certifications", profile.get("certifications", [])),
        "achievements": facts.get("achievements", profile.get("achievements", [])),
    }
    job_payload = {
        "title": analysis.get("title", ""),
        "company": analysis.get("company", ""),
        "required_skills": analysis.get("required_skills", []),
        "preferred_skills": analysis.get("preferred_skills", []),
        "responsibilities": analysis.get("responsibilities", []),
        "keywords": analysis.get("keywords", []),
        "experience_requirements": analysis.get("experience_requirements", []),
        "education_requirements": analysis.get("education_requirements", []),
    }
    user_prompt = (
        "JOB DESCRIPTION ANALYSIS (do not treat as facts about the candidate):\n"
        + json.dumps(job_payload, indent=2)[:6000]
        + "\n\nPROFILE (the only allowed source of facts):\n"
        + json.dumps(profile_payload, indent=2)[:12000]
        + "\n\nBullet indexes refer to the order of bullets inside each project/experience entry. "
        "Only rewrite bullets that exist above. Return the JSON object only."
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def call_featherless(messages: list[dict], max_tokens: int = 1600) -> str:
    status = ai_status()
    if not status["configured"]:
        raise AIUnavailable(
            "FEATHERLESS_API_KEY is not configured. Add it to your .env file to enable live AI tailoring."
        )
    url = status["base_url"].rstrip("/") + "/chat/completions"
    try:
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {(os.environ.get('FEATHERLESS_API_KEY') or '').strip()}",
                "Content-Type": "application/json",
            },
            json={
                "model": status["model"],
                "messages": messages,
                "temperature": 0.3,
                "max_tokens": max_tokens,
            },
            timeout=90,
        )
    except requests.RequestException as exc:
        raise AIUnavailable(
            "Could not reach Featherless AI (network error or timeout). Check your connection and API settings."
        ) from exc

    if response.status_code != 200:
        detail = ""
        try:
            body = response.json()
            if isinstance(body, dict):
                error = body.get("error")
                if isinstance(error, dict):
                    detail = str(error.get("message", ""))[:200]
                elif error:
                    detail = str(error)[:200]
        except ValueError:
            detail = ""
        raise AIUnavailable(
            f"Featherless AI returned HTTP {response.status_code}."
            + (f" {detail}" if detail else "")
            + " Check that your key is valid and the selected model is available."
        )

    try:
        body = response.json()
        content = body["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise AIUnavailable("Featherless AI returned an unexpected response shape.") from exc
    if not isinstance(content, str) or not content.strip():
        raise AIUnavailable("Featherless AI returned an empty response.")
    return content


def _extract_json(text: str) -> dict:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.I).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise AIUnavailable("The AI response did not contain JSON. Try again or use demo mode.")
    try:
        payload = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        raise AIUnavailable("The AI response was not valid JSON. Try again or use demo mode.") from exc
    if not isinstance(payload, dict):
        raise AIUnavailable("The AI response was not a JSON object.")
    return payload


# ---------------------------------------------------------------------------
# Deterministic fallback
# ---------------------------------------------------------------------------
def deterministic_tailoring(profile: dict, analysis: dict, document: dict | None = None) -> dict[str, Any]:
    """Keyword-based suggestions that require no AI and invent nothing."""
    facts = _document_to_facts(document) if document else profile
    if not facts:
        facts = profile
    candidate_skills = _candidate_skills(profile, facts)
    facts_text = _facts_text(facts)
    facts_norm = normalize(facts_text)

    matched_required = [s for s in analysis.get("required_skills", []) if s in candidate_skills]
    summary = None
    headline = str(facts.get("headline", "") or "").strip()
    project_names = [p.get("name") for p in facts.get("projects", []) or [] if p.get("name")]
    if matched_required or headline or project_names:
        sentences = []
        if headline:
            sentences.append(headline.rstrip(".") + ".")
        if matched_required:
            sentences.append(
                "Hands-on with " + ", ".join(matched_required[:5]) + "."
            )
        if project_names:
            sentences.append("Recent work includes " + " and ".join(project_names[:2]) + ".")
        text = " ".join(sentences)
        summary = {
            "text": text,
            "rationale": (
                "Deterministic draft assembled only from your headline, skills and project names. "
                "Edit it before use."
            ),
            "status": "needs_confirmation",
            "issues": ["Generated without AI — review the wording before applying."],
            "fabricated_terms": [],
            "fabricated_metrics": [],
        }

    improvements: list[dict] = []
    for source in _bullet_sources(facts):
        original = source["original"]
        lowered = original.lower()
        improved = original
        for weak, strong in sorted(WEAK_OPENERS.items(), key=lambda item: -len(item[0])):
            if lowered.startswith(weak + " "):
                improved = strong + original[len(weak) :]
                break
        improved = re.sub(r"^i\s+", "", improved, flags=re.I)
        if improved:
            improved = improved[0].upper() + improved[1:]
            if not improved.rstrip().endswith((".", "!", "?")):
                improved = improved.rstrip() + "."
        if normalize(improved) == normalize(original):
            continue
        improvements.append(
            {
                "target": source["target"],
                "index": source["index"],
                "location": source["location"],
                "original": original,
                "improved": improved,
                "rationale": "Weak opening replaced with a stronger action verb; the facts are unchanged.",
                "status": "ready",
                "requires_confirmation": True,
            }
        )
        if len(improvements) >= 6:
            break

    keywords: list[dict] = []
    seen: set[str] = set()
    for keyword in list(analysis.get("keywords", [])) + [
        s for s in analysis.get("required_skills", []) if s in candidate_skills
    ]:
        key = keyword.lower()
        if key in seen:
            continue
        seen.add(key)
        present = normalize(keyword) in facts_norm
        keywords.append(
            {
                "keyword": keyword,
                "present_in_profile": present,
                "requires_confirmation": not present,
                "note": "Found in your profile."
                if present
                else "Not found in your profile — do not add it unless it is genuinely true.",
            }
        )
        if len(keywords) >= 12:
            break

    notes = [
        "Deterministic analysis: this uses keyword matching and verb swaps, not a live language model.",
        "Only your existing facts were reworded. No skills, employers, projects or metrics were added.",
    ]
    if analysis.get("required_years") is not None:
        notes.append(
            f"The job asks for about {analysis['required_years']:g}+ years of experience — compare that honestly with your profile."
        )

    return {
        "summary": summary,
        "bullet_improvements": improvements,
        "keywords": keywords,
        "action_verbs": ACTION_VERB_SUGGESTIONS[:8],
        "rejected": [],
        "notes": notes,
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def tailor_resume(
    profile: dict,
    analysis: dict,
    document: dict | None = None,
    force_fallback: bool = False,
) -> dict[str, Any]:
    """Return suggestions plus honest metadata about whether AI was used."""
    status = ai_status()
    facts = _document_to_facts(document) if document else profile
    if not facts:
        facts = profile

    meta = {
        "provider": status["provider"],
        "model": status["model"],
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "disclaimer": DISCLAIMER,
    }

    if not status["configured"] or force_fallback:
        fallback = deterministic_tailoring(profile, analysis, document)
        fallback.update(meta)
        fallback.update(
            {
                "mode": "fallback",
                "live": False,
                "error": None
                if force_fallback
                else "No Featherless API key is configured.",
                "reason": "Demo mode: deterministic keyword analysis and safe verb rewrites (no live AI call).",
            }
        )
        return fallback

    try:
        raw = call_featherless(_build_messages(profile, analysis, facts))
        payload = _extract_json(raw)
        result = validate_ai_output(profile, analysis, payload, document)
        result.update(meta)
        result.update(
            {
                "mode": "live",
                "live": True,
                "error": None,
                "reason": f"Generated live by {status['model']} via Featherless AI.",
            }
        )
        return result
    except AIUnavailable as exc:
        fallback = deterministic_tailoring(profile, analysis, document)
        fallback.update(meta)
        fallback.update(
            {
                "mode": "fallback",
                "live": False,
                "error": str(exc),
                "reason": "Live AI tailoring failed, so ResumeIQ switched to deterministic suggestions. No AI content was applied.",
            }
        )
        return fallback
