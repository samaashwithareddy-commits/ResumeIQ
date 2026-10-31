-- ResumeIQ database schema (SQLite)
-- All application queries use parameterised statements (see database/repo.py).

PRAGMA foreign_keys = ON;

-- Master profile: exactly one row (id = 1).
CREATE TABLE IF NOT EXISTS profile (
    id            INTEGER PRIMARY KEY CHECK (id = 1),
    full_name     TEXT NOT NULL DEFAULT '',
    headline      TEXT NOT NULL DEFAULT '',
    email         TEXT NOT NULL DEFAULT '',
    phone         TEXT NOT NULL DEFAULT '',
    location      TEXT NOT NULL DEFAULT '',
    linkedin      TEXT NOT NULL DEFAULT '',
    github        TEXT NOT NULL DEFAULT '',
    summary       TEXT NOT NULL DEFAULT '',
    updated_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS skills (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL REFERENCES profile(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    position   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS education (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id  INTEGER NOT NULL REFERENCES profile(id) ON DELETE CASCADE,
    institution TEXT NOT NULL DEFAULT '',
    degree      TEXT NOT NULL DEFAULT '',
    field       TEXT NOT NULL DEFAULT '',
    start_date  TEXT NOT NULL DEFAULT '',
    end_date    TEXT NOT NULL DEFAULT '',
    score       TEXT NOT NULL DEFAULT '',
    location    TEXT NOT NULL DEFAULT '',
    position    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS projects (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id  INTEGER NOT NULL REFERENCES profile(id) ON DELETE CASCADE,
    name        TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    tech        TEXT NOT NULL DEFAULT '',
    link        TEXT NOT NULL DEFAULT '',
    position    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS experience (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id  INTEGER NOT NULL REFERENCES profile(id) ON DELETE CASCADE,
    role        TEXT NOT NULL DEFAULT '',
    company     TEXT NOT NULL DEFAULT '',
    start_date  TEXT NOT NULL DEFAULT '',
    end_date    TEXT NOT NULL DEFAULT '',
    location    TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    position    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS certifications (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL REFERENCES profile(id) ON DELETE CASCADE,
    name       TEXT NOT NULL DEFAULT '',
    issuer     TEXT NOT NULL DEFAULT '',
    year       TEXT NOT NULL DEFAULT '',
    position   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS achievements (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL REFERENCES profile(id) ON DELETE CASCADE,
    text       TEXT NOT NULL DEFAULT '',
    position   INTEGER NOT NULL DEFAULT 0
);

-- Saved job descriptions and their deterministic analysis.
CREATE TABLE IF NOT EXISTS jobs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    title         TEXT NOT NULL DEFAULT '',
    company       TEXT NOT NULL DEFAULT '',
    url           TEXT NOT NULL DEFAULT '',
    description   TEXT NOT NULL,
    analysis_json TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Editable resume documents (snapshot of the profile at creation time).
CREATE TABLE IF NOT EXISTS resumes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT NOT NULL DEFAULT 'Untitled resume',
    template     TEXT NOT NULL DEFAULT 'classic',
    job_id       INTEGER REFERENCES jobs(id) ON DELETE SET NULL,
    content_json TEXT NOT NULL,
    created_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Section order and visibility for each resume document.
CREATE TABLE IF NOT EXISTS resume_sections (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    resume_id   INTEGER NOT NULL REFERENCES resumes(id) ON DELETE CASCADE,
    section_key TEXT NOT NULL,
    label       TEXT NOT NULL,
    position    INTEGER NOT NULL DEFAULT 0,
    visible     INTEGER NOT NULL DEFAULT 1
);

-- Stored match results so the dashboard can show the latest analysis.
CREATE TABLE IF NOT EXISTS match_results (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id         INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    resume_id      INTEGER REFERENCES resumes(id) ON DELETE SET NULL,
    score          REAL NOT NULL,
    breakdown_json TEXT NOT NULL,
    created_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Download history for generated PDF / DOCX files.
CREATE TABLE IF NOT EXISTS exports (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    resume_id  INTEGER NOT NULL REFERENCES resumes(id) ON DELETE CASCADE,
    filename   TEXT NOT NULL,
    fmt        TEXT NOT NULL,
    template   TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_match_job ON match_results(job_id);
CREATE INDEX IF NOT EXISTS idx_sections_resume ON resume_sections(resume_id);
CREATE INDEX IF NOT EXISTS idx_exports_resume ON exports(resume_id);
