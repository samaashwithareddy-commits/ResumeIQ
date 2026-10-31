"""Deterministic job-description analysis and match scoring.

Design goals
------------
* No randomness: the same profile + job description always yields the same score.
* No invented requirements: everything reported here is extracted from the text
  the user supplied, or from the profile they filled in.
* Transparent weights: see ``DEFAULT_WEIGHTS`` and the ``explanation`` list that
  every result carries.

This module is deliberately rule-based so the app stays useful without an AI key.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Iterable

DEFAULT_WEIGHTS: dict[str, float] = {
    "required": 50.0,
    "preferred": 20.0,
    "projects_experience": 20.0,
    "education_other": 10.0,
}

WEIGHT_LABELS = {
    "required": "Required skill coverage",
    "preferred": "Preferred skill coverage",
    "projects_experience": "Relevant projects & experience",
    "education_other": "Education & other role requirements",
}

DISCLAIMER = (
    "This score measures how much of the job description is covered by what you listed in "
    "your profile. It is a keyword/evidence overlap signal, not a hiring prediction and not "
    "a guarantee of ATS success. Recruiters also judge context, depth and interviews."
)

# ---------------------------------------------------------------------------
# Skill catalogue: canonical name, category, aliases
# ---------------------------------------------------------------------------
SKILL_CATALOG: list[tuple[str, str, tuple[str, ...]]] = [
    # Languages
    ("Python", "language", ("python", "python3")),
    ("Java", "language", ("java",)),
    ("JavaScript", "language", ("javascript", "js", "ecmascript")),
    ("TypeScript", "language", ("typescript", "ts")),
    ("C++", "language", ("c++", "cpp")),
    ("C#", "language", ("c#", "csharp")),
    ("Go", "language", ("golang",)),
    ("Rust", "language", ("rust",)),
    ("Kotlin", "language", ("kotlin",)),
    ("Swift", "language", ("swift",)),
    ("PHP", "language", ("php",)),
    ("Ruby", "language", ("ruby",)),
    ("Scala", "language", ("scala",)),
    ("Dart", "language", ("dart",)),
    ("SQL", "language", ("sql",)),
    ("MATLAB", "language", ("matlab",)),
    ("Bash", "language", ("bash", "shell scripting", "shell script")),
    ("Objective-C", "language", ("objective c", "objective-c")),
    # Frontend / frameworks
    ("React", "framework", ("react", "react.js", "reactjs")),
    ("React Native", "framework", ("react native",)),
    ("Angular", "framework", ("angular", "angularjs")),
    ("Vue.js", "framework", ("vue", "vue.js", "vuejs")),
    ("Next.js", "framework", ("next.js", "nextjs", "next js")),
    ("Svelte", "framework", ("svelte", "sveltekit")),
    ("Redux", "framework", ("redux", "redux toolkit")),
    ("Tailwind CSS", "framework", ("tailwind", "tailwind css", "tailwindcss")),
    ("Bootstrap", "framework", ("bootstrap",)),
    ("HTML", "framework", ("html", "html5")),
    ("CSS", "framework", ("css", "css3")),
    ("Sass", "framework", ("sass", "scss")),
    ("jQuery", "framework", ("jquery",)),
    ("Accessibility", "concept", ("accessibility", "a11y", "wcag")),
    # Backend
    ("Node.js", "framework", ("node.js", "nodejs", "node")),
    ("Express.js", "framework", ("express", "express.js", "expressjs")),
    ("Django", "framework", ("django",)),
    ("Flask", "framework", ("flask",)),
    ("FastAPI", "framework", ("fastapi",)),
    ("Spring Boot", "framework", ("spring boot", "springboot")),
    ("Laravel", "framework", ("laravel",)),
    ("Ruby on Rails", "framework", ("ruby on rails", "rails")),
    (".NET", "framework", (".net", "dotnet", "asp.net")),
    ("REST APIs", "framework", ("rest", "rest api", "rest apis", "restful", "restful apis")),
    ("GraphQL", "framework", ("graphql",)),
    ("gRPC", "framework", ("grpc",)),
    ("Microservices", "concept", ("microservices", "microservice", "micro services")),
    # Mobile / data / ML
    ("Flutter", "framework", ("flutter",)),
    ("Android", "framework", ("android", "android sdk")),
    ("iOS", "framework", ("ios",)),
    ("TensorFlow", "framework", ("tensorflow",)),
    ("PyTorch", "framework", ("pytorch",)),
    ("scikit-learn", "framework", ("scikit-learn", "scikit learn", "sklearn")),
    ("Pandas", "framework", ("pandas",)),
    ("NumPy", "framework", ("numpy",)),
    ("OpenCV", "framework", ("opencv",)),
    ("Keras", "framework", ("keras",)),
    ("Apache Spark", "framework", ("spark", "pyspark", "apache spark")),
    ("Airflow", "framework", ("airflow", "apache airflow")),
    ("Machine Learning", "concept", ("machine learning", "ml models", "supervised learning")),
    ("Deep Learning", "concept", ("deep learning", "neural networks")),
    ("NLP", "concept", ("nlp", "natural language processing")),
    ("Computer Vision", "concept", ("computer vision",)),
    # Databases & data stores
    ("PostgreSQL", "database", ("postgresql", "postgres")),
    ("MySQL", "database", ("mysql",)),
    ("SQLite", "database", ("sqlite",)),
    ("MongoDB", "database", ("mongodb", "mongo")),
    ("Redis", "database", ("redis",)),
    ("DynamoDB", "database", ("dynamodb",)),
    ("Elasticsearch", "database", ("elasticsearch", "elastic search")),
    ("Oracle", "database", ("oracle db", "oracle database")),
    ("Snowflake", "database", ("snowflake",)),
    ("BigQuery", "database", ("bigquery", "big query")),
    # Cloud & infrastructure
    ("AWS", "cloud", ("aws", "amazon web services")),
    ("Azure", "cloud", ("azure", "microsoft azure")),
    ("GCP", "cloud", ("gcp", "google cloud", "google cloud platform")),
    ("Docker", "cloud", ("docker", "containers", "containerization")),
    ("Kubernetes", "cloud", ("kubernetes", "k8s")),
    ("Terraform", "cloud", ("terraform",)),
    ("Ansible", "cloud", ("ansible",)),
    ("CI/CD", "cloud", ("ci/cd", "cicd", "continuous integration", "continuous delivery", "continuous deployment")),
    ("Firebase", "cloud", ("firebase",)),
    ("Supabase", "cloud", ("supabase",)),
    ("Vercel", "cloud", ("vercel",)),
    ("Heroku", "cloud", ("heroku",)),
    ("Nginx", "cloud", ("nginx",)),
    # Tools & platforms
    ("Git", "tool", ("git",)),
    ("GitHub", "tool", ("github",)),
    ("GitLab", "tool", ("gitlab",)),
    ("Jenkins", "tool", ("jenkins",)),
    ("Jira", "tool", ("jira",)),
    ("Linux", "tool", ("linux", "unix")),
    ("Postman", "tool", ("postman",)),
    ("Figma", "tool", ("figma",)),
    ("Webpack", "tool", ("webpack",)),
    ("Vite", "tool", ("vite",)),
    ("Kafka", "tool", ("kafka",)),
    ("RabbitMQ", "tool", ("rabbitmq",)),
    ("Selenium", "tool", ("selenium",)),
    ("Pytest", "tool", ("pytest",)),
    ("Jest", "tool", ("jest",)),
    ("Cypress", "tool", ("cypress",)),
    ("Playwright", "tool", ("playwright",)),
    ("Tableau", "tool", ("tableau",)),
    ("Power BI", "tool", ("power bi", "powerbi")),
    ("Excel", "tool", ("excel", "advanced excel")),
    ("Unity", "tool", ("unity",)),
    ("Salesforce", "tool", ("salesforce",)),
    ("HubSpot", "tool", ("hubspot",)),
    # Concepts / practices
    ("Data Structures", "concept", ("data structures", "dsa")),
    ("Algorithms", "concept", ("algorithms", "algorithm design")),
    ("System Design", "concept", ("system design", "distributed systems")),
    ("Object-Oriented Design", "concept", ("oop", "object oriented", "object-oriented")),
    ("Unit Testing", "concept", ("unit testing", "unit tests", "test coverage", "automated testing")),
    ("Code Review", "concept", ("code review", "code reviews", "peer review")),
    ("Agile", "concept", ("agile", "scrum", "kanban")),
    ("API Design", "concept", ("api design", "api development")),
    ("Performance Optimization", "concept", ("performance optimization", "performance tuning", "optimization")),
    ("Data Pipelines", "concept", ("data pipelines", "etl", "data pipeline")),
    ("Version Control", "concept", ("version control",)),
    ("Debugging", "concept", ("debugging", "troubleshooting")),
    # Soft skills
    ("Communication", "soft", ("communication", "communicate clearly", "verbal communication")),
    ("Written Communication", "soft", ("written communication", "writing skills")),
    ("Teamwork", "soft", ("teamwork", "team player", "collaboration", "collaborate")),
    ("Problem Solving", "soft", ("problem solving", "problem-solving", "analytical skills")),
    ("Leadership", "soft", ("leadership", "lead teams", "mentoring", "mentor")),
    ("Time Management", "soft", ("time management", "prioritization", "prioritisation")),
    ("Adaptability", "soft", ("adaptability", "fast-paced", "fast paced")),
    ("Critical Thinking", "soft", ("critical thinking",)),
    ("Attention to Detail", "soft", ("attention to detail", "detail-oriented", "detail oriented")),
    ("Ownership", "soft", ("ownership", "self-starter", "self starter")),
    ("Stakeholder Management", "soft", ("stakeholder management", "stakeholders")),
    ("Presentation", "soft", ("presentation skills", "presenting")),
]


def normalize(text: str) -> str:
    """Lowercase and collapse punctuation so aliases match reliably."""
    text = (text or "").lower()
    text = text.replace("&", " and ").replace("+", " plus ").replace("#", " sharp ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


ALIAS_INDEX: dict[str, str] = {}
CATEGORY_INDEX: dict[str, str] = {}
for _canonical, _category, _aliases in SKILL_CATALOG:
    CATEGORY_INDEX[_canonical] = _category
    ALIAS_INDEX[normalize(_canonical)] = _canonical
    for _alias in _aliases:
        ALIAS_INDEX[normalize(_alias)] = _canonical


def _aliases_by_length() -> list[tuple[str, str]]:
    pairs = sorted(ALIAS_INDEX.items(), key=lambda item: len(item[0]), reverse=True)
    return pairs


_ALIAS_PAIRS = _aliases_by_length()


def canonical_for_skill(raw: str) -> str | None:
    """Map a user-entered skill string to a catalogue canonical name."""
    norm = normalize(raw)
    if not norm:
        return None
    if norm in ALIAS_INDEX:
        return ALIAS_INDEX[norm]
    # Try multi-token containment ("react native" from "react native developer").
    for alias, canonical in _ALIAS_PAIRS:
        if re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", norm):
            return canonical
    return None


def find_skills(text: str) -> dict[str, str]:
    """Return ``{canonical: category}`` in order of first appearance in ``text``.

    A shorter alias that sits inside a longer matched alias is discarded, so
    "React Native" does not also produce a spurious "React" match.
    """
    norm = normalize(text)
    if not norm:
        return {}

    raw_matches: list[tuple[int, int, str]] = []
    for alias, canonical in _ALIAS_PAIRS:
        for match in re.finditer(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", norm):
            raw_matches.append((match.start(), match.end(), canonical))
    raw_matches.sort(key=lambda item: (item[0], -(item[1] - item[0])))

    spans: list[tuple[int, int]] = []
    positions: dict[str, int] = {}
    for start, end, canonical in raw_matches:
        contained = any(
            outer_start <= start and end <= outer_end and (outer_end - outer_start) > (end - start)
            for outer_start, outer_end in spans
        )
        if contained:
            continue
        spans.append((start, end))
        if canonical not in positions or start < positions[canonical]:
            positions[canonical] = start

    return {canonical: CATEGORY_INDEX[canonical] for canonical in sorted(positions, key=positions.get)}


# ---------------------------------------------------------------------------
# Job description parsing
# ---------------------------------------------------------------------------
PREFERRED_CUES = (
    "preferred",
    "nice to have",
    "nice-to-have",
    "bonus",
    "good to have",
    "desired",
    "is a plus",
    "are a plus",
    "plus:",
    "advantage",
    "adds value",
)
REQUIRED_CUES = (
    "requirement",
    "qualification",
    "must have",
    "must-have",
    "what we look for",
    "what you need",
    "what you'll need",
    "who you are",
    "about you",
    "minimum",
    "basic qualifications",
    "skills:",
    "experience:",
)
RESPONSIBILITY_CUES = (
    "responsibilit",
    "what you'll do",
    "what you will do",
    "what you will be doing",
    "day to day",
    "day-to-day",
    "the role",
    "your role",
    "about the role",
    "you will",
    "key duties",
    "tasks",
)
IGNORE_CUES = (
    "benefit",
    "perks",
    "about us",
    "about the company",
    "why join",
    "compensation",
    "salary",
    "equal opportunity",
    "how to apply",
    "our culture",
    "what we offer",
)

EDU_LEVELS: dict[str, int] = {
    "phd": 5,
    "doctorate": 5,
    "m.tech": 4,
    "mtech": 4,
    "master": 4,
    "m.sc": 4,
    "msc": 4,
    "mba": 4,
    "mca": 4,
    "b.tech": 3,
    "btech": 3,
    "b.e": 3,
    "bachelor": 3,
    "b.sc": 3,
    "bsc": 3,
    "bca": 3,
    "undergraduate": 3,
    "degree": 3,
    "associate": 2,
    "diploma": 2,
    "high school": 1,
}
EDU_LEVEL_NAMES = {
    1: "high school",
    2: "associate/diploma",
    3: "bachelor's degree",
    4: "master's degree",
    5: "doctorate",
}

STOPWORDS = {
    "a", "a's", "able", "about", "above", "across", "after", "again", "against", "all", "also",
    "an", "and", "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can", "can't", "cannot", "could", "couldn't", "did",
    "didn't", "do", "does", "doesn't", "doing", "don't", "down", "during", "each", "etc", "even",
    "ever", "every", "few", "for", "from", "further", "get", "gets", "getting", "give", "go",
    "had", "hadn't", "has", "hasn't", "have", "haven't", "having", "he", "her", "here", "hers",
    "herself", "him", "himself", "his", "how", "however", "i", "if", "in", "including", "into",
    "is", "isn't", "it", "it's", "its", "itself", "just", "let", "like", "likely", "make", "many",
    "may", "me", "might", "more", "most", "must", "my", "need", "needs", "neither", "no", "nor",
    "not", "now", "of", "off", "on", "once", "one", "only", "or", "other", "our", "ours", "out",
    "over", "own", "per", "plus", "same", "she", "should", "so", "some", "such", "than", "that",
    "the", "their", "theirs", "them", "then", "there", "these", "they", "this", "those", "through",
    "to", "too", "under", "until", "up", "us", "use", "used", "using", "very", "want", "was",
    "wasn't", "we", "well", "were", "what", "when", "where", "which", "while", "who", "whom",
    "why", "will", "with", "within", "without", "would", "you", "your", "yours", "yourself",
    "years", "year", "work", "working", "works", "role", "job", "company", "team", "teams",
    "candidate", "candidates", "applicant", "ability", "strong", "good", "great", "new", "join",
    "looking", "seeking", "required", "preferred", "responsible", "responsibilities", "including",
    "help", "build", "building", "ensure", "deliver", "develop", "developing", "create",
    "creating", "design", "designing", "tools", "environment", "opportunity", "start", "about",
    "description", "position", "employment", "type", "location", "apply", "benefits",
    "qualifications", "requirements", "skills", "know", "knowledge", "understanding",
    "familiarity", "experience", "experienced", "hands", "solid", "proven", "excellent",
    "minimum", "relevant", "related", "degree", "field", "equivalent", "etc", "bonus",
    "preferred", "ideal", "ideally", "someone", "things", "something", "day", "days", "week",
    "time", "part", "full", "based", "across", "stakeholders", "solutions", "solution", "product",
    "products", "platform", "platforms", "systems", "system", "code", "coding", "features",
    "feature", "quality", "best", "practices", "provide", "support", "maintain", "maintaining",
    "implement", "implementing", "write", "writing", "review", "reviews", "test", "tests",
    "testing", "debug", "integrate", "integrating", "participate", "collaborate", "workflows",
    "workflow", "processes", "process", "business", "users", "user", "customer", "customers",
    "technical", "technology", "technologies", "software", "engineer", "engineering", "developer",
}

PHRASE_KEYWORDS = (
    "distributed systems",
    "code review",
    "unit testing",
    "system design",
    "api design",
    "clean code",
    "test coverage",
    "continuous integration",
    "continuous delivery",
    "cross functional",
    "best practices",
    "cloud infrastructure",
    "data pipelines",
    "performance optimization",
    "production support",
    "product roadmap",
    "stakeholder management",
    "technical documentation",
    "scalable systems",
    "high availability",
)


def _sentences(text: str) -> list[str]:
    raw = re.split(r"(?<=[.!?])\s+|\n+", text or "")
    return [re.sub(r"\s+", " ", s).strip() for s in raw if s.strip()]


def _is_heading(line: str) -> bool:
    low = line.strip().lower()
    if not low or len(low) > 90:
        return False
    if low.endswith(":"):
        return True
    return any(cue in low for cue in PREFERRED_CUES + REQUIRED_CUES + RESPONSIBILITY_CUES + IGNORE_CUES)


def _bucket_for(line: str) -> str:
    low = line.strip().lower()
    if any(cue in low for cue in IGNORE_CUES):
        return "ignore"
    if any(cue in low for cue in PREFERRED_CUES):
        return "preferred"
    if any(cue in low for cue in RESPONSIBILITY_CUES):
        return "responsibility"
    return "required"


def _clean_bullet(line: str) -> str:
    cleaned = re.sub(r"^\s*(?:[-*•·▪◦]|\d+[.)])\s*", "", line).strip()
    return cleaned


def _extract_years(text: str) -> tuple[float | None, list[str]]:
    requirements: list[str] = []
    years: list[float] = []
    pattern = re.compile(r"(\d{1,2})\s*(?:\+|plus)?\s*(?:-|–|to)?\s*(\d{1,2})?\s*(?:years?|yrs?)\b", re.I)
    for sentence in _sentences(text):
        low = sentence.lower()
        if not re.search(r"\b(experience|exp)\b", low):
            continue
        match = pattern.search(sentence)
        if not match:
            if re.search(r"\b(entry level|entry-level|fresh graduate|new grad|internship)\b", low):
                requirements.append(sentence[:220])
                years.append(0.0)
            continue
        low_value = float(match.group(1))
        years.append(low_value)
        requirements.append(sentence[:220])
    if not years:
        return None, requirements
    return min(years), requirements[:3]


def _extract_education(lines_with_buckets: Iterable[tuple[str, str]]) -> tuple[list[str], int | None]:
    requirements: list[str] = []
    required_levels: list[int] = []
    other_levels: list[int] = []
    for line, bucket in lines_with_buckets:
        low = line.lower()
        levels = [level for token, level in EDU_LEVELS.items() if token in low]
        if not levels:
            continue
        level = min(levels)
        if bucket in ("required", "responsibility"):
            required_levels.append(level)
        else:
            other_levels.append(level)
        if len(requirements) < 4 and any(
            word in low for word in ("degree", "bachelor", "master", "b.tech", "b.e", "diploma", "graduate")
        ):
            requirements.append(line.strip()[:220])
    candidates = required_levels or other_levels
    return requirements, (min(candidates) if candidates else None)


ACRONYMS = {"api", "apis", "ats", "aws", "ci/cd", "sql", "rest", "nlp", "ml", "ui", "ux", "qa", "etl", "gcp", "html", "css", "js", "saas"}


def _titlecase_keyword(value: str) -> str:
    return " ".join(
        part.upper() if part.lower() in ACRONYMS else part.capitalize() for part in value.split()
    )


def _extract_keywords(text: str, skill_canonicals: set[str], limit: int = 16,
                      exclude_terms: tuple[str, ...] = ()) -> list[str]:
    norm = normalize(text)
    tokens = [t for t in norm.split() if len(t) >= 3 and t not in STOPWORDS]
    counts: dict[str, int] = {}
    for token in tokens:
        counts[token] = counts.get(token, 0) + 1

    excluded: set[str] = set()
    for term in exclude_terms:
        excluded |= {token for token in normalize(term).split() if len(token) >= 3}

    keywords: list[str] = []
    for phrase in PHRASE_KEYWORDS:
        if re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", norm):
            keywords.append(_titlecase_keyword(phrase))

    skill_tokens = {normalize(skill) for skill in skill_canonicals}
    for token, count in sorted(counts.items(), key=lambda item: (-item[1], -len(item[0]))):
        if count < 2 or len(token) < 4:
            continue
        if token in skill_tokens or token in excluded:
            continue
        keywords.append(_titlecase_keyword(token))

    seen: set[str] = set()
    result: list[str] = []
    for keyword in keywords:
        key = keyword.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(keyword)
        if len(result) >= limit:
            break
    return result


def parse_job_description(description: str, title: str = "", company: str = "", url: str = "") -> dict[str, Any]:
    """Extract skills, requirements, keywords and responsibilities from a JD."""
    description = (description or "").strip()
    if len(description) < 40:
        raise ValueError("The job description is too short to analyse (minimum 40 characters).")

    lines = [re.sub(r"\s+", " ", line).strip() for line in description.splitlines()]
    lines = [line for line in lines if line]

    bucket = "required"
    line_buckets: list[tuple[str, str]] = []
    responsibilities: list[str] = []
    required: dict[str, str] = {}
    preferred: dict[str, str] = {}

    for raw_line in lines:
        low = raw_line.lower()
        if _is_heading(raw_line):
            bucket = _bucket_for(raw_line)
            line_buckets.append((raw_line, bucket))
            continue
        line_buckets.append((raw_line, bucket))
        skills = find_skills(raw_line)
        for canonical, category in skills.items():
            entry = {"source_line": raw_line[:200], "category": category}
            target = preferred if bucket == "preferred" else required
            if bucket == "ignore":
                continue
            if canonical in required:
                continue
            if bucket == "preferred":
                preferred.setdefault(canonical, entry)
            else:
                required.setdefault(canonical, entry)
        if bucket == "responsibility":
            bullet = _clean_bullet(raw_line)
            if 25 <= len(bullet) <= 260 and len(responsibilities) < 8 and not _is_heading(bullet):
                responsibilities.append(bullet)

    preferred = {k: v for k, v in preferred.items() if k not in required}

    soft_skills = sorted(
        [skill for skill in list(required) + list(preferred) if CATEGORY_INDEX.get(skill) == "soft"]
    )
    required_technical = [s for s in required if CATEGORY_INDEX.get(s) != "soft"]
    preferred_technical = [s for s in preferred if CATEGORY_INDEX.get(s) != "soft"]

    languages = [s for s in required_technical if CATEGORY_INDEX.get(s) == "language"]
    maps = {
        "framework": [s for s in required_technical if CATEGORY_INDEX.get(s) == "framework"],
        "database": [s for s in required_technical if CATEGORY_INDEX.get(s) == "database"],
        "cloud": [s for s in required_technical if CATEGORY_INDEX.get(s) == "cloud"],
        "tool": [s for s in required_technical if CATEGORY_INDEX.get(s) == "tool"],
        "concept": [s for s in required_technical if CATEGORY_INDEX.get(s) == "concept"],
    }
    frameworks_tools = maps["framework"] + maps["tool"] + maps["cloud"] + maps["database"]
    for skill in preferred_technical:
        if skill not in frameworks_tools and skill not in languages:
            frameworks_tools.append(skill)

    years, experience_requirements = _extract_years(description)
    education_requirements, education_level = _extract_education(line_buckets)
    keywords = _extract_keywords(
        description,
        set(required) | set(preferred),
        exclude_terms=(title, company),
    )

    notes: list[str] = []
    if not required_technical:
        notes.append("No technical skills were detected in the required sections; check the description text.")
    if not preferred_technical:
        notes.append("The description does not list any preferred skills.")
    if years is None:
        notes.append("No explicit years-of-experience requirement was found.")
    if education_level is None:
        notes.append("No formal education requirement was detected.")
    if not responsibilities:
        notes.append("No responsibility list was detected; only requirement text was analysed.")

    return {
        "title": (title or "").strip()[:160],
        "company": (company or "").strip()[:160],
        "url": (url or "").strip()[:500],
        "required_skills": required_technical,
        "preferred_skills": preferred_technical,
        "languages": languages,
        "frameworks_tools": list(dict.fromkeys(frameworks_tools)),
        "databases": maps["database"],
        "concepts": list(dict.fromkeys(maps["concept"])),
        "soft_skills": soft_skills,
        "experience_requirements": experience_requirements,
        "required_years": years,
        "education_requirements": education_requirements,
        "education_level": education_level,
        "keywords": keywords,
        "responsibilities": responsibilities,
        "required_evidence": {k: v["source_line"] for k, v in required.items() if k in required_technical},
        "preferred_evidence": {k: v["source_line"] for k, v in preferred.items() if k in preferred_technical},
        "notes": notes,
        "word_count": len(description.split()),
        "description": description,
    }


# ---------------------------------------------------------------------------
# Candidate evidence
# ---------------------------------------------------------------------------
def _parse_month(value: str) -> tuple[int, int] | None:
    """Parse '2024-06', 'Jun 2024', 'June 2024', '06/2024' or '2024'."""
    value = (value or "").strip()
    if not value:
        return None
    if re.fullmatch(r"present|current|now|ongoing", value, re.I):
        today = date.today()
        return today.year, today.month
    match = re.search(r"(\d{4})", value)
    if not match:
        return None
    year = int(match.group(1))
    month = 1
    month_names = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }
    lower = value.lower()
    for name, number in month_names.items():
        if name in lower:
            month = number
            break
    else:
        numeric = re.search(r"\b(\d{1,2})[/-](\d{4})\b", value)
        if numeric and 1 <= int(numeric.group(1)) <= 12:
            month = int(numeric.group(1))
    return year, month


def _months_between(start: tuple[int, int], end: tuple[int, int]) -> int:
    return max(0, (end[0] - start[0]) * 12 + (end[1] - start[1]))


def _estimate_years(experience: list[dict]) -> float:
    total_months = 0
    for item in experience or []:
        start = _parse_month(item.get("start_date", ""))
        end = _parse_month(item.get("end_date", "")) or _parse_month("present")
        if start and end:
            total_months += _months_between(start, end)
    return round(total_months / 12.0, 1)


def _education_level_from_profile(education: list[dict]) -> int | None:
    levels: list[int] = []
    for item in education or []:
        text = normalize(" ".join(str(item.get(key, "")) for key in ("degree", "field", "institution", "score")))
        if not text:
            continue
        found = [level for token, level in EDU_LEVELS.items() if re.search(rf"\b{re.escape(normalize(token))}\b", text)]
        if found:
            levels.append(max(found))
    return max(levels) if levels else None


def build_candidate(profile: dict) -> dict[str, Any]:
    """Collect skill evidence from every part of the profile."""
    skill_sources: dict[str, set[str]] = {}

    def add_skills(text: str, source: str) -> None:
        for canonical in find_skills(text):
            skill_sources.setdefault(canonical, set()).add(source)

    for raw_skill in profile.get("skills", []) or []:
        raw_skill = str(raw_skill).strip()
        if not raw_skill:
            continue
        canonical = canonical_for_skill(raw_skill) or raw_skill
        skill_sources.setdefault(canonical, set()).add("Skills")

    add_skills(profile.get("summary", "") or "", "Summary")
    add_skills(" ".join(profile.get("achievements", []) or []), "Achievements")

    projects = []
    for item in profile.get("projects", []) or []:
        name = item.get("name", "") or ""
        text = " ".join(
            str(item.get(key, "")) for key in ("name", "description", "tech", "link")
        )
        add_skills(text, f"Project: {name}" if name else "Projects")
        projects.append(
            {
                "name": name,
                "text": text,
                "skills": set(find_skills(text)) | {
                    canonical_for_skill(part)
                    for part in re.split(r"[,;|/]", str(item.get("tech", "")))
                    if canonical_for_skill(part)
                },
            }
        )

    experience = []
    for item in profile.get("experience", []) or []:
        label_bits = [item.get("role", ""), item.get("company", "")]
        label = " at ".join([bit for bit in label_bits if bit]) or "Experience"
        text = " ".join(
            str(item.get(key, ""))
            for key in ("role", "company", "description", "location")
        )
        add_skills(text, f"Experience: {label}")
        experience.append({"label": label, "text": text, "skills": set(find_skills(text))})

    for item in profile.get("education", []) or []:
        text = " ".join(str(item.get(key, "")) for key in ("degree", "field", "institution", "score"))
        add_skills(text, "Education")

    cert_text = " ".join(
        " ".join(str(item.get(key, "")) for key in ("name", "issuer"))
        for item in profile.get("certifications", []) or []
    )
    add_skills(cert_text, "Certifications")

    all_text = " ".join(
        [
            str(profile.get("summary", "") or ""),
            " ".join(str(s) for s in profile.get("skills", []) or []),
            " ".join(p["text"] for p in projects),
            " ".join(e["text"] for e in experience),
            " ".join(str(a) for a in profile.get("achievements", []) or []),
            " ".join(
                " ".join(str(item.get(key, "")) for key in ("degree", "field", "institution"))
                for item in profile.get("education", []) or []
            ),
            cert_text,
        ]
    )

    return {
        "skills": set(skill_sources),
        "skill_sources": {skill: sorted(sources) for skill, sources in skill_sources.items()},
        "text": all_text,
        "projects": projects,
        "experience": experience,
        "years_experience": _estimate_years(profile.get("experience", []) or []),
        "education_level": _education_level_from_profile(profile.get("education", []) or []),
        "has_experience": bool(experience),
        "has_projects": bool(projects),
    }


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------
def _tokens(name: str) -> set[str]:
    return {token for token in normalize(name).split() if token}


def _is_catalogue_alias(token: str) -> bool:
    return token in ALIAS_INDEX


def _find_partial(required_skill: str, candidate_skills: Iterable[str]) -> str | None:
    """Return a candidate skill that partially covers ``required_skill``."""
    required_tokens = _tokens(required_skill)
    for candidate in sorted(candidate_skills):
        if candidate == required_skill:
            continue
        candidate_tokens = _tokens(candidate)
        shared = {t for t in required_tokens & candidate_tokens if len(t) >= 3}
        if shared:
            return candidate
        for req_token in required_tokens:
            for cand_token in candidate_tokens:
                if len(req_token) < 4 or len(cand_token) < 4:
                    continue
                if req_token in cand_token or cand_token in req_token:
                    shorter = min(req_token, cand_token, key=len)
                    if not _is_catalogue_alias(shorter):
                        return candidate
    return None


def _coverage(skills: list[str], candidate: dict) -> dict[str, Any]:
    matched: list[str] = []
    partial: list[dict[str, str]] = []
    missing: list[str] = []
    for skill in skills:
        if skill in candidate["skills"]:
            matched.append(skill)
        else:
            partner = _find_partial(skill, candidate["skills"])
            if partner:
                partial.append({"skill": skill, "matched_with": partner})
            else:
                missing.append(skill)
    total = len(skills)
    ratio = (len(matched) + 0.5 * len(partial)) / total if total else None
    return {"total": total, "matched": matched, "partial": partial, "missing": missing, "ratio": ratio}


def score_match(profile: dict, analysis: dict, weights: dict[str, float] | None = None) -> dict[str, Any]:
    """Score a profile against a parsed job description.

    Category weights (default): required 50, preferred 20, projects/experience 20,
    education/other 10. Categories that cannot apply are dropped and the remaining
    weights are renormalised to 100, which is reported in ``effective_weights``.
    """
    weights = {**DEFAULT_WEIGHTS, **(weights or {})}
    candidate = build_candidate(profile)
    candidate_skills = candidate["skills"]

    required = list(analysis.get("required_skills", []))
    preferred = list(analysis.get("preferred_skills", []))
    soft_required = list(analysis.get("soft_skills", []))
    jd_skills = set(required) | set(preferred)

    required_cov = _coverage(required, candidate)
    preferred_cov = _coverage(preferred, candidate)

    categories: list[dict[str, Any]] = []
    explanation: list[str] = []

    # 1. Required skills -----------------------------------------------------
    if required_cov["ratio"] is None:
        categories.append(
            {
                "key": "required",
                "label": WEIGHT_LABELS["required"],
                "weight": weights["required"],
                "score": None,
                "status": "not_applicable",
                "note": "The job description did not list any required technical skills.",
            }
        )
        explanation.append(
            "Required-skill coverage was skipped because no required technical skills were extracted, "
            "so its weight was redistributed."
        )
    else:
        categories.append(
            {
                "key": "required",
                "label": WEIGHT_LABELS["required"],
                "weight": weights["required"],
                "score": required_cov["ratio"],
                "status": "scored",
                "note": (
                    f"{len(required_cov['matched'])} of {required_cov['total']} required skills found in your profile"
                    + (f", {len(required_cov['partial'])} partially aligned" if required_cov["partial"] else "")
                    + "."
                ),
            }
        )
        explanation.append(
            f"Required skills: {len(required_cov['matched'])}/{required_cov['total']} covered"
            + (f", {len(required_cov['partial'])} partially aligned (worth half credit)" if required_cov["partial"] else "")
            + f" → {round(required_cov['ratio'] * 100)}% of the {int(weights['required'])}-point required-skill category."
        )

    # 2. Preferred skills ---------------------------------------------------
    if preferred_cov["ratio"] is None:
        categories.append(
            {
                "key": "preferred",
                "label": WEIGHT_LABELS["preferred"],
                "weight": weights["preferred"],
                "score": None,
                "status": "not_applicable",
                "note": "No preferred skills were listed in the job description.",
            }
        )
        explanation.append(
            "Preferred-skill coverage was not applicable (nothing was listed as preferred), "
            "so that weight was redistributed."
        )
    else:
        categories.append(
            {
                "key": "preferred",
                "label": WEIGHT_LABELS["preferred"],
                "weight": weights["preferred"],
                "score": preferred_cov["ratio"],
                "status": "scored",
                "note": (
                    f"{len(preferred_cov['matched'])} of {preferred_cov['total']} preferred skills found"
                    + (f", {len(preferred_cov['partial'])} partial" if preferred_cov["partial"] else "")
                    + "."
                ),
            }
        )
        explanation.append(
            f"Preferred skills: {len(preferred_cov['matched'])}/{preferred_cov['total']} covered → "
            f"{round(preferred_cov['ratio'] * 100)}% of the {int(weights['preferred'])}-point category."
        )

    # 3. Projects and experience -------------------------------------------
    project_relevant: list[dict[str, Any]] = []
    for project in candidate["projects"]:
        matched = sorted(project["skills"] & jd_skills)
        if matched:
            project_relevant.append({"name": project["name"], "matched": matched})
    project_relevant.sort(key=lambda item: (-len(item["matched"]), item["name"]))

    experience_matched = sorted(
        {skill for item in candidate["experience"] for skill in (item["skills"] & jd_skills)}
    )

    denominator = max(3, min(8, len(jd_skills) or 3))
    project_component = None
    experience_component = None
    if candidate["has_projects"]:
        breadth = len(project_relevant[0]["matched"]) if project_relevant else 0
        all_project_skills = set()
        for project in candidate["projects"]:
            all_project_skills |= project["skills"] & jd_skills
        breadth_score = min(1.0, len(all_project_skills) / denominator)
        project_component = 0.7 * breadth_score + 0.3 * (1.0 if project_relevant else 0.0)
        project_component = min(1.0, project_component + 0.05 * max(0, min(3, breadth - 1)))
    if candidate["has_experience"]:
        breadth_score = min(1.0, len(experience_matched) / denominator)
        required_years = analysis.get("required_years")
        if required_years is None or required_years <= 0:
            years_score = 1.0
            years_note = "the job sets no meaningful minimum experience"
        else:
            years_score = min(1.0, candidate["years_experience"] / required_years)
            years_note = (
                f"the job asks for {required_years:g}+ years and your profile shows "
                f"about {candidate['years_experience']:g} years of dated experience"
            )
        experience_component = 0.6 * breadth_score + 0.4 * years_score
        experience_component = min(1.0, experience_component)
    else:
        years_note = "no dated work experience was found on your profile"

    if project_component is None and experience_component is None:
        categories.append(
            {
                "key": "projects_experience",
                "label": WEIGHT_LABELS["projects_experience"],
                "weight": weights["projects_experience"],
                "score": None,
                "status": "not_applicable",
                "note": "No projects or experience entries exist on the profile.",
            }
        )
        explanation.append(
            "Projects and experience could not be scored because the profile has neither, so that weight was redistributed."
        )
    else:
        if project_component is not None and experience_component is not None:
            category_score = 0.5 * project_component + 0.5 * experience_component
            note = (
                f"{len(project_relevant)} project(s) and {len(candidate['experience'])} experience entr(ies) "
                f"reference job skills; {years_note}."
            )
        elif project_component is not None:
            category_score = project_component
            note = (
                f"Only project evidence exists, so projects carry this category: "
                f"{len(project_relevant)} project(s) reference job skills; {years_note}."
            )
        else:
            category_score = experience_component
            note = f"Only work experience exists; {years_note}."
        categories.append(
            {
                "key": "projects_experience",
                "label": WEIGHT_LABELS["projects_experience"],
                "weight": weights["projects_experience"],
                "score": category_score,
                "status": "scored",
                "note": note,
            }
        )
        explanation.append(
            f"Projects & experience: {round(category_score * 100)}% of the "
            f"{int(weights['projects_experience'])}-point category ({note})"
        )

    # 4. Education and other role requirements -----------------------------
    edu_level_required = analysis.get("education_level")
    edu_level_candidate = candidate["education_level"]
    edu_component = None
    edu_note = ""
    if edu_level_required:
        if edu_level_candidate is None:
            edu_component = 0.0
            edu_note = (
                f"the job asks for a {EDU_LEVEL_NAMES.get(edu_level_required, 'degree')} "
                "and no education entry was found on the profile"
            )
        elif edu_level_candidate >= edu_level_required:
            edu_component = 1.0
            edu_note = (
                f"the job asks for a {EDU_LEVEL_NAMES.get(edu_level_required, 'degree')} and your highest "
                f"qualification is a {EDU_LEVEL_NAMES.get(edu_level_candidate, 'degree')}"
            )
        elif edu_level_candidate == edu_level_required - 1:
            edu_component = 0.6
            edu_note = (
                f"the job asks for a {EDU_LEVEL_NAMES.get(edu_level_required, 'degree')} and your highest "
                f"qualification is a {EDU_LEVEL_NAMES.get(edu_level_candidate, 'degree')}"
            )
        else:
            edu_component = 0.25
            edu_note = "your listed qualification is below the level requested by the job"
    else:
        edu_note = "no formal education requirement was detected in the job description"

    soft_cov = _coverage(soft_required, candidate) if soft_required else None
    if edu_component is None and soft_cov is None:
        categories.append(
            {
                "key": "education_other",
                "label": WEIGHT_LABELS["education_other"],
                "weight": weights["education_other"],
                "score": None,
                "status": "not_applicable",
                "note": "No education requirement or soft-skill requirement was extracted.",
            }
        )
        explanation.append(
            "Education/other requirements were not applicable, so that weight was redistributed."
        )
    else:
        components = []
        if edu_component is not None:
            components.append(edu_component)
        if soft_cov is not None and soft_cov["ratio"] is not None:
            components.append(soft_cov["ratio"])
        category_score = sum(components) / len(components)
        if edu_component is not None and soft_cov is not None:
            note = (
                f"Education: {edu_note}. Soft skills: {len(soft_cov['matched'])}/{soft_cov['total']} mentioned "
                "in your profile."
            )
        elif edu_component is not None:
            note = f"Education: {edu_note}."
        else:
            note = (
                f"Soft skills: {len(soft_cov['matched'])}/{soft_cov['total']} of the requested soft skills "
                "appear in your profile (no education requirement was listed)."
            )
        categories.append(
            {
                "key": "education_other",
                "label": WEIGHT_LABELS["education_other"],
                "weight": weights["education_other"],
                "score": category_score,
                "status": "scored",
                "note": note,
            }
        )
        explanation.append(
            f"Education & other requirements: {round(category_score * 100)}% of the "
            f"{int(weights['education_other'])}-point category ({note})"
        )

    # Weight renormalisation -------------------------------------------------
    scored = [c for c in categories if c["status"] == "scored"]
    weight_total = sum(c["weight"] for c in scored)
    effective_weights: dict[str, float] = {}
    total_points = 0.0
    for category in categories:
        if category["status"] == "scored" and weight_total > 0:
            effective = category["weight"] / weight_total * 100.0
            effective_weights[category["key"]] = round(effective, 1)
            points = category["score"] * effective
            category["effective_weight"] = round(effective, 1)
            category["points"] = round(points, 1)
            total_points += points
        else:
            category["effective_weight"] = 0.0
            category["points"] = 0.0

    score = round(max(0.0, min(100.0, total_points)), 1)

    # Informational keyword similarity (explicitly not part of the score) ---
    keywords = list(analysis.get("keywords", []))
    candidate_norm = normalize(candidate["text"])
    matched_keywords = [k for k in keywords if normalize(k) and normalize(k) in candidate_norm]
    missing_keywords = [k for k in keywords if k not in matched_keywords]
    for skill in preferred:
        if skill in preferred_cov["missing"] and skill not in missing_keywords:
            missing_keywords.append(skill)
    for skill in required:
        if skill in required_cov["missing"] and skill not in missing_keywords:
            missing_keywords.append(skill)
    missing_keywords = missing_keywords[:14]
    keyword_similarity = round(len(matched_keywords) / len(keywords) * 100) if keywords else 0

    experience_alignment = {
        "required_years": analysis.get("required_years"),
        "candidate_years": candidate["years_experience"],
        "has_experience": candidate["has_experience"],
        "status": _alignment_status(analysis.get("required_years"), candidate["years_experience"], candidate["has_experience"]),
        "note": (
            "No years requirement was stated in the job description."
            if analysis.get("required_years") is None
            else (
                f"Profile shows about {candidate['years_experience']:g} year(s) of dated experience "
                f"against a {analysis['required_years']:g}+ year requirement."
            )
        ),
    }
    education_alignment = {
        "required_level": edu_level_required,
        "required_label": EDU_LEVEL_NAMES.get(edu_level_required) if edu_level_required else None,
        "candidate_level": edu_level_candidate,
        "candidate_label": EDU_LEVEL_NAMES.get(edu_level_candidate) if edu_level_candidate else None,
        "status": _edu_status(edu_level_required, edu_level_candidate),
        "note": edu_note,
    }

    if score >= 85:
        label = "Excellent alignment"
    elif score >= 70:
        label = "Strong alignment"
    elif score >= 55:
        label = "Moderate alignment"
    elif score >= 40:
        label = "Partial alignment"
    else:
        label = "Low alignment"

    matched_skills = required_cov["matched"] + [s for s in preferred_cov["matched"] if s not in required_cov["matched"]]

    return {
        "score": score,
        "label": label,
        "categories": categories,
        "effective_weights": effective_weights,
        "weights": {key: float(value) for key, value in weights.items()},
        "matched_skills": matched_skills,
        "missing_skills": [s for s in required_cov["missing"] if s not in preferred_cov["matched"]][:16],
        "partial_skills": required_cov["partial"] + [p for p in preferred_cov["partial"] if p not in required_cov["partial"]],
        "required_matched": required_cov["matched"],
        "required_missing": required_cov["missing"],
        "preferred_matched": preferred_cov["matched"],
        "preferred_missing": preferred_cov["missing"],
        "relevant_projects": project_relevant[:5],
        "experience_alignment": experience_alignment,
        "education_alignment": education_alignment,
        "keywords": {
            "matched": matched_keywords,
            "missing": missing_keywords,
            "similarity": keyword_similarity,
        },
        "skill_sources": {
            skill: candidate["skill_sources"].get(skill, [])
            for skill in matched_skills
        },
        "explanation": explanation,
        "disclaimer": DISCLAIMER,
        "renormalised": len(scored) < len(categories),
        "candidate_years": candidate["years_experience"],
    }


def _alignment_status(required_years: float | None, candidate_years: float, has_experience: bool) -> str:
    if required_years is None:
        return "not_specified"
    if not has_experience:
        return "not_met"
    if candidate_years >= required_years:
        return "met"
    if required_years > 0 and candidate_years >= required_years * 0.5:
        return "partial"
    return "not_met"


def _edu_status(required: int | None, candidate: int | None) -> str:
    if required is None:
        return "not_specified"
    if candidate is None:
        return "not_met"
    if candidate >= required:
        return "met"
    if candidate == required - 1:
        return "partial"
    return "not_met"
