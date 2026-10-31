# ResumeIQ — AI-Powered Tailored Resume Architect & Interactive Editor

> **Your experience. Their requirements. One perfect match.**

ResumeIQ is a local-first resume builder for students, freshers and experienced professionals.
Paste a job description, get a transparent match score against your **real** profile, see exactly
which skills are missing, apply only the AI rewrites you agree with, edit in a live two-panel
editor, and download a genuine PDF and DOCX.

It is built for a hackathon demo: the complete workflow works **with no API key** in clearly
labelled demo mode, and adds live AI tailoring when you configure Featherless AI.

---

## Feature checklist

| Area | What works |
| --- | --- |
| Dashboard | Greeting, latest match score, resume drafts, jobs analysed, exports, profile readiness, quick links. No fake statistics. |
| Master profile | Personal details, summary, skills chips, multiple education / project / experience / certification entries, achievements. Add, edit, delete, validate, persist. |
| Job analyser | Paste text or fetch a public URL (SSRF-safe), extracts required & preferred skills, languages, frameworks/tools, databases, concepts, soft skills, years requirement, education requirement, role keywords, responsibilities. Never invents requirements. |
| Match score | Deterministic 0–100 score with documented 50/20/20/10 weights, matched / missing / partial skills, relevant projects, education & experience alignment, missing keywords, plain-language explanation, automatic renormalisation when a category does not apply. |
| AI tailoring | Featherless AI summary rewrite, bullet improvements, keyword suggestions, action verbs. A fabrication guard rejects new numbers, new skills and unverifiable originals. Suggestions are never auto-applied. |
| Editor | Live A4 preview, three templates, add/remove sections (including custom sections), drag or button section reordering, bullet add/reorder/delete, show/hide sections, undo/redo, autosave, desktop & mobile preview, delete draft. |
| Templates | ATS Classic, Modern Professional, Minimal Technical — all text-based and export cleanly. |
| Export | Real A4 PDF (ReportLab) and real `.docx` (python-docx) built from the latest saved content. Export history with re-download. |
| Demo | One-click fictional candidate + sample software-engineering internship. Labelled as demonstration data everywhere. |
| Tests | 54 pytest tests covering scoring, missing keywords, persistence, section ordering, PDF/DOCX validity, AI failure, fabrication prevention and API security. |

---

## Technology

- **Frontend:** HTML5, CSS3, vanilla JavaScript (no build step, no CDN dependency).
- **Backend:** Python 3 + Flask.
- **Database:** SQLite (parameterised SQL only).
- **AI (optional):** Featherless AI, OpenAI-compatible chat completions.
- **PDF:** ReportLab. **DOCX:** python-docx.
- **Icons:** inline Lucide-style SVG.

---

## Project structure

```
ResumeIQ/
├── app.py                    # Flask app factory, pages, JSON API, exports
├── requirements.txt
├── .env.example              # copy to .env, never commit .env
├── README.md
├── database/
│   ├── schema.sql            # profile, skills, education, projects, experience,
│   │                         # certifications, achievements, jobs, resumes,
│   │                         # resume_sections, match_results, exports, settings
│   ├── db.py                 # connection + initialisation
│   ├── repo.py               # parameterised data access
│   └── seed.py               # fictional demo candidate + sample job
├── services/
│   ├── matcher.py            # skill taxonomy, JD parsing, scoring
│   ├── ai_service.py         # Featherless call, validation, deterministic fallback
│   ├── job_fetch.py          # SSRF-safe public page fetcher
│   ├── resume_export.py      # PDF + DOCX renderers
│   └── validation.py         # backend input validation / normalisation
├── templates/
│   ├── base.html, base_public.html, index.html
│   ├── dashboard.html, profile.html, builder.html, matcher.html
│   ├── templates.html, history.html, settings.html, error.html
├── static/
│   ├── css/style.css         # app shell & design system
│   ├── css/pages.css         # page-specific layouts
│   ├── css/resume.css        # resume themes (preview)
│   └── js/app.js, profile.js, matcher.js, editor.js, gallery.js
└── tests/
    ├── conftest.py, test_matcher.py, test_persistence.py,
    ├── test_export.py, test_ai.py, test_api.py
```

---

## Install on Windows (CMD)

> Do not assume Python is installed. If `python --version` is not recognised, install Python first.

### 0. If Python is missing

1. Download Python 3.11 or newer for Windows from <https://www.python.org/downloads/windows/>.
2. Run the installer and **tick “Add python.exe to PATH”** on the first screen.
3. Close and reopen CMD, then verify:

```bat
python --version
python -m pip --version
```

### 1. Open the project folder

```bat
cd path\to\ResumeIQ
```

### 2. Create and activate a virtual environment

```bat
python -m venv .venv
.venv\Scripts\activate
```

You should see `(.venv)` at the start of the prompt. If PowerShell blocks activation, use CMD as
shown, or run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` in PowerShell first.

### 3. Install dependencies

```bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 4. Configure environment variables

```bat
copy .env.example .env
notepad .env
```

Set a `SECRET_KEY` (any long random string). Leave `FEATHERLESS_API_KEY` empty to run in demo mode.
Generate a key value with:

```bat
python -c "import secrets; print(secrets.token_hex(32))"
```

### 5. Run

```bat
python app.py
```

Open <http://127.0.0.1:5000>.

The SQLite database is created automatically at `database/resumeiq.db`.

### macOS / Linux equivalent

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python app.py
```

---

## Featherless AI configuration

1. Create an account at <https://featherless.ai> and generate an API key.
2. Add it to `.env` (never to `app.py`, the database, or browser code):

```ini
FEATHERLESS_API_KEY=your_key_here
FEATHERLESS_BASE_URL=https://api.featherless.ai/v1
FEATHERLESS_MODEL=Qwen/Qwen2.5-7B-Instruct
```

3. Restart `python app.py`.
4. Open **Settings** to confirm “Configured” and the model name. You can also force
   “Always deterministic (no AI calls)” for an offline demo even when a key exists.

The key is only read server-side by `services/ai_service.py`. It is never returned by any endpoint.

### What happens without a key

- The match score, skill extraction, editor, templates and both exports are fully functional.
- The AI panel shows a **Demo mode** banner and returns deterministic, clearly labelled
  suggestions (weak-verb replacement + keyword presence checks).
- `live: false` is returned by the API. The UI never claims a live AI call succeeded.

### If the Featherless call fails

The API returns HTTP 200 with `tailoring.live = false`, a friendly `error`, and deterministic
suggestions. The UI shows an amber “No live AI used” banner with the exact failure reason
(e.g. HTTP 503, invalid JSON, network timeout) and never applies anything automatically.

---

## How the match score works

Weights are fixed and visible in Settings:

| Category | Weight | Calculation |
| --- | --- | --- |
| Required skill coverage | 50 | `(full matches + 0.5 × partial matches) ÷ required skills` |
| Preferred skill coverage | 20 | Same formula for preferred/bonus skills |
| Relevant projects & experience | 20 | 70% breadth of job skills evidenced in projects/roles + 30% presence/years alignment (50/50 when both exist, available half when only one does) |
| Education & other requirements | 10 | 70% degree level vs requirement (full / partial / below) + 30% soft-skill coverage; whichever exists if only one does |

- **Partial matches** happen when a skill shares a token with a relevant one (`React Native ≈ React`,
  `Postgres ≈ PostgreSQL`). They earn half credit and are shown as “partially matched”.
- **Not-applicable categories** (no preferred skills listed, no projects on the profile, no education
  requirement) are removed and the remaining weights renormalise to 100%. The result payload
  includes `effective_weights` and an explanation sentence listing what was redistributed.
- **Keyword similarity** is displayed separately on the matcher and is **not** part of the score.
- The score is deterministic: the same profile + job description always produces the same number.
- The score measures keyword/evidence overlap. It is **not** a hiring prediction and does not
  guarantee ATS success. This disclaimer is shown next to every score.

Example from the bundled demo data: Aarav Sharma scores about **67/100 — Moderate alignment** against
the Northwind Labs backend internship, with PostgreSQL, Redis, CI/CD and API Design shown as gaps.
(Exact decimal score depends on the profile and job text; the UI rounds consistently.)

---

## AI safety rules (enforced in code, not just in the prompt)

`services/ai_service.py` sends the profile plus the parsed job analysis and requires structured JSON.
`validate_ai_output()` then:

1. Rejects a bullet rewrite whose original is **not an exact bullet in your profile/draft**.
2. Rejects rewrites that introduce **numbers or percentages** not present in your profile.
3. Rejects rewrites that introduce **skills** not already evidenced in your profile.
4. Flags a summary that mentions unsupported skills or new metrics as “needs confirmation”.
5. Discards any `skills_to_add` list outright — adding skills is never allowed.
6. Returns rejected items with reasons so the demo can show the guard working.

Users apply or dismiss every suggestion manually. The master profile is never mutated by AI.
The only automatic change is the deterministic fallback, which performs verb swaps on your own
bullets and is still presented for confirmation.

---

## Exports

- **PDF:** A4, 17 mm side margins, 15 mm top / 18 mm bottom, ReportLab flowables. Long unbroken
  strings wrap (`wordWrap="CJK"` on contact/headline), bullets are real paragraphs, section headings
  are kept with their rule, and no forced page breaks are used, so blank pages cannot be produced.
- **DOCX:** real Word document with normal paragraphs, `Heading 2` section headings, `List Bullet`
  list items and template-specific fonts/colours. Opens in Word, Google Docs and LibreOffice.
- Both use the **latest saved** content. The editor flushes autosave before starting a download and
  blocks the download if that save fails.
- Every successful download is logged on **Export History** with a re-export link.

---

## Demo script (about 3 minutes)

1. Open the app and click **Load the demo candidate** (landing page or dashboard).
   *Aarav Sharma, fictional final-year student, plus the Northwind Labs internship posting.*
2. The Job Matcher opens with the sample posting and the analysis already rendered.
3. Walk through the score card: **64%**, “Required 8/12”, then the breakdown bars and the plain
   language explanation below.
4. Point at **Missing skills**: PostgreSQL, Redis, CI/CD, API Design — “these are learning targets,
   not things we add.”
5. Click **Create tailored resume** → the builder opens with the job linked.
6. In the AI panel click **Generate suggestions**. With no key, point out the amber
   **“Demo mode / no live AI used”** banner, then apply one bullet rewrite and read the
   “requires confirmation” label. (With a key, show the green “Live AI” banner and the rejected
   suggestions list that proves fabricated metrics were blocked.)
7. Edit the summary live; the A4 preview updates as you type. Toggle **Mobile** preview.
8. Drag a section (or use ↑/↓), hide Certifications with the switch, press **Undo**.
9. Switch template from ATS Classic to Modern Professional.
10. Click **PDF**, then **DOCX**, and open the downloaded files. Finish on **Export History**.

Offline fallback path for step 6: everything except the AI card is fully functional without a key.

---

## Tests

```bat
.venv\Scripts\activate
python -m pytest -q
```

Coverage highlights:

- `test_matcher.py` — required/preferred extraction, no invented skills, deterministic weighting,
  missing skills & keywords, partial credit, renormalisation, word-boundary matching.
- `test_persistence.py` — profile round-trip, replacement semantics, SQL-injection-as-text,
  resume + section ordering and visibility, custom sections, jobs/matches/exports, reset.
- `test_export.py` — PDF magic bytes, extracted text, hidden sections, section order, multi-page
  documents with no blank pages, DOCX structure/heading/list styles, filename sanitising.
- `test_ai.py` — valid rewrite acceptance, fabricated metric/skill rejection, unknown original
  rejection, summary flagging, `skills_to_add` rejection, missing key, HTTP failure, invalid JSON,
  forced fallback, deterministic fallback never adds skills.
- `test_api.py` — page rendering, profile validation, job analysis persistence, autosave ordering,
  tailor fallback, real PDF/DOCX downloads, export history, SSRF/port/scheme guards, demo + reset.

---

## API summary

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Health + AI configured flag (no secrets) |
| GET/POST | `/api/profile` | Read / replace master profile and child entries |
| GET/POST | `/api/resumes` | List / create a draft from the profile (optional `job_id`, `template`) |
| GET/PUT/DELETE | `/api/resumes/<id>` | Load / autosave (`content` + `sections`) / delete |
| POST | `/api/jobs/fetch` | Fetch a public job page (http/https, public IPs, 2 MB cap) |
| POST | `/api/jobs/analyze` | Parse a JD, store job + match result, return breakdown |
| GET | `/api/jobs/<id>` | Reload a stored analysis and its latest match |
| POST | `/api/resumes/<id>/tailor` | Featherless tailoring with deterministic fallback |
| GET | `/export/<resume_id>/pdf` / `.../docx` | Download and log an export |
| POST | `/api/demo/load`, `/api/data/reset` | Demo data / clear local records |
| POST | `/api/settings` | Default template and AI mode |

---

## Security and reliability notes

- API keys live only in `.env`; `.env` is git-ignored and `.env.example` contains no secrets.
- All SQL uses bound parameters; table names come from fixed allow-lists.
- Backend validation for emails, phones, URLs, lengths, entry counts and payload size (2 MB).
- URL fetching blocks non-http(s) schemes, credentials in URLs, non-standard ports, loopback,
  private, link-local, reserved and multicast addresses, revalidates every redirect, and caps the
  response at 2 MB and 12 s.
- Jinja auto-escaping plus JS `escapeHtml` for the client-rendered preview.
- Security headers: CSP, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`;
  API responses are `no-store`.
- No uploads are implemented, so no file-type/size upload surface exists.
- No user-supplied code is executed. No `eval`, no `exec`.
- Graceful error pages (HTML) and `{ok:false,error}` JSON for API failures.

### Known limitations

- The skill taxonomy is curated (~120 skills). Unknown niche tools are not extracted as skills and
  may appear only as keywords; add them manually to the profile.
- Keyword extraction is frequency/phrase based, so company boilerplate can occasionally appear.
- SSRF validation resolves DNS and then requests performs its own resolution; a determined DNS
  rebinding attack is not fully mitigated (acceptable for a local tool).
- PDF/DOCX fidelity is intentionally close but not pixel-identical; Word may reflow lines.
- AI quality depends on the Featherless model; the safety validator can only reject unsupported
  content, it cannot verify that a rewrite is stylistically better.
- Login/multi-user accounts, CSRF tokens and background workers are out of scope for this local
  single-user build.
- One master profile per installation (multiple named resume drafts are supported).

---

## Hackathon talking points

- The score is auditable: fixed weights, visible math, explicit “not applicable” handling.
- The anti-fabrication guard is demonstrable — feed it a metric and watch it reject.
- Everything runs locally on Windows with free software; the demo never depends on a paid service.
- The demo candidate is fictional and labelled as such, including contact details on `example.com`.
## Project Overview

ResumeIQ is an AI-powered resume analysis and job-matching application designed to help users evaluate resumes and identify relevant job opportunities.