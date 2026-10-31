"""ResumeIQ — AI-powered tailored resume architect and interactive editor.

Run locally with:  python app.py
"""

from __future__ import annotations

import json
import os
import secrets
from io import BytesIO
from pathlib import Path

from dotenv import load_dotenv
from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

from database import repo
from database.db import DEFAULT_DB_PATH, init_db
from database.seed import DEMO_PROFILE, SAMPLE_JOB, load_demo
from services.ai_service import ai_status, tailor_resume
from services.job_fetch import FetchError, fetch_job_description
from services.matcher import DEFAULT_WEIGHTS, parse_job_description, score_match
from services.resume_export import build_docx, build_pdf, filename_for
from services.validation import (
    clean_job_payload,
    clean_profile_payload,
    clean_resume_content,
    safe_template,
)

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

RESUME_TEMPLATES = [
    {
        "id": "classic",
        "name": "ATS Classic",
        "tagline": "Single column, plain headings, parser-friendly.",
        "description": (
            "The safest default for technical applications and campus placements. No colour blocks, "
            "no tables, no text boxes — just clean headings and bullets that applicant tracking "
            "systems read reliably."
        ),
        "tags": ["ATS-first", "Single column", "Recruiter friendly"],
    },
    {
        "id": "modern",
        "name": "Modern Professional",
        "tagline": "Navy name, indigo rules, generous hierarchy.",
        "description": (
            "A polished layout for product companies and experienced-hire roles. Subtle accent rules "
            "and clear section hierarchy keep it elegant while staying fully text-based."
        ),
        "tags": ["Accent colour", "Senior roles", "Clean hierarchy"],
    },
    {
        "id": "minimal",
        "name": "Minimal Technical",
        "tagline": "Compact spacing that puts projects first.",
        "description": (
            "Dense and scannable, designed for students and internship applications where skills and "
            "projects deserve the most space. Everything still exports as real text."
        ),
        "tags": ["Compact", "Student friendly", "Project focus"],
    },
]
TEMPLATE_IDS = [item["id"] for item in RESUME_TEMPLATES]


def profile_completeness(profile: dict) -> int:
    checks = [
        bool(profile.get("full_name")),
        bool(profile.get("email")),
        bool(profile.get("location") or profile.get("phone")),
        bool(profile.get("summary")),
        bool(profile.get("skills")),
        bool(profile.get("education")),
        bool(profile.get("projects")),
        bool(profile.get("experience")),
        bool(profile.get("certifications") or profile.get("achievements")),
    ]
    return round(sum(1 for check in checks if check) / len(checks) * 100)


def initials_for(name: str) -> str:
    parts = [part for part in (name or "").split() if part]
    if not parts:
        return "RI"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def create_app(db_path: str | Path | None = None) -> Flask:
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(24),
        DB_PATH=str(db_path or os.environ.get("RESUMEIQ_DB") or DEFAULT_DB_PATH),
        MAX_CONTENT_LENGTH=2 * 1024 * 1024,
        JSON_SORT_KEYS=False,
    )
    init_db(app.config["DB_PATH"])

    def db() -> str:
        return app.config["DB_PATH"]

    def json_error(message: str, status: int = 400, **extra):
        payload = {"ok": False, "error": message}
        payload.update(extra)
        return jsonify(payload), status

    def current_profile() -> dict:
        return repo.get_profile(db())

    @app.template_filter("score_int")
    def score_int(value):
        try:
            return int(round(float(value) + 0.5))
        except (TypeError, ValueError):
            return 0

    @app.template_filter("nicedt")
    def nicedt(value):
        from datetime import datetime

        if not value:
            return "—"
        try:
            parsed = datetime.strptime(str(value)[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return str(value)
        return parsed.strftime("%d %b %Y · %H:%M")

    @app.context_processor
    def inject_globals():
        profile = repo.get_profile(db())
        status = ai_status()
        return {
            "ai": status,
            "profile": profile,
            "profile_initials": initials_for(profile.get("full_name", "")),
            "profile_completeness": profile_completeness(profile),
            "demo_loaded": repo.get_setting(db(), "demo_loaded", "0") == "1",
            "app_name": "ResumeIQ",
            "tagline": "Your experience. Their requirements. One perfect match.",
        }

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'; connect-src 'self'; form-action 'self'; "
            "base-uri 'self'; frame-ancestors 'self'",
        )
        if request.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    # ------------------------------------------------------------------
    # Pages
    # ------------------------------------------------------------------
    @app.get("/")
    def index():
        stats = {
            "resumes": repo.count_resumes(db()),
            "jobs": len(repo.list_jobs(db(), limit=100)),
            "ai_ready": ai_status()["configured"],
        }
        return render_template("index.html", stats=stats, active="home")

    @app.get("/dashboard")
    def dashboard_page():
        profile = current_profile()
        resumes = repo.list_resumes(db(), limit=5)
        latest = repo.latest_match(db())
        jobs = repo.list_jobs(db(), limit=5)
        stats = {
            "resumes": repo.count_resumes(db()),
            "jobs": len(repo.list_jobs(db(), limit=100)),
            "exports": len(repo.list_exports(db(), limit=100)),
            "completeness": profile_completeness(profile),
        }
        return render_template(
            "dashboard.html",
            active="dashboard",
            resumes=resumes,
            latest_match=latest,
            jobs=jobs,
            stats=stats,
            demo_profile=DEMO_PROFILE if not profile.get("full_name") else None,
        )

    @app.get("/profile")
    def profile_page():
        return render_template(
            "profile.html",
            active="profile",
            profile=current_profile(),
            profile_json=current_profile(),
        )

    @app.get("/builder")
    @app.get("/builder/<int:resume_id>")
    def builder_page(resume_id: int | None = None):
        resume = repo.get_resume(db(), resume_id) if resume_id else None
        if resume is None:
            resumes = repo.list_resumes(db(), limit=1)
            if resumes:
                resume = repo.get_resume(db(), resumes[0]["id"])
        jobs = repo.list_jobs(db(), limit=10)
        return render_template(
            "builder.html",
            active="builder",
            resume=resume,
            resume_json=resume,
            jobs=jobs,
            templates=RESUME_TEMPLATES,
            requested_job_id=request.args.get("job", type=int),
        )

    @app.get("/matcher")
    @app.get("/matcher/<int:job_id>")
    def matcher_page(job_id: int | None = None):
        initial = None
        if job_id:
            job = repo.get_job(db(), job_id)
            if job:
                breakdown = repo.latest_match_for_job(db(), job_id)
                initial = {
                    "job": {
                        "id": job["id"],
                        "title": job["title"],
                        "company": job["company"],
                        "url": job["url"],
                        "description": job["description"],
                    },
                    "analysis": job["analysis"],
                    "match": breakdown["breakdown"] if breakdown else None,
                }
        return render_template(
            "matcher.html",
            active="matcher",
            initial=initial,
            initial_json=initial,
            sample_job=SAMPLE_JOB,
            templates=RESUME_TEMPLATES,
        )

    @app.get("/templates")
    def templates_page():
        profile = current_profile()
        latest = repo.list_resumes(db(), limit=1)
        preview_content = (
            repo.get_resume(db(), latest[0]["id"])["content"] if latest else repo.content_from_profile(profile)
        )
        return render_template(
            "templates.html",
            active="templates",
            templates=RESUME_TEMPLATES,
            preview_content=preview_content,
            has_profile=bool(profile.get("full_name") or profile.get("skills")),
            default_template=repo.get_setting(db(), "default_template", "classic"),
        )

    @app.get("/history")
    def history_page():
        return render_template(
            "history.html",
            active="history",
            exports=repo.list_exports(db(), limit=100),
            resumes=repo.list_resumes(db(), limit=20),
        )

    @app.get("/settings")
    def settings_page():
        return render_template(
            "settings.html",
            active="settings",
            settings={
                "default_template": repo.get_setting(db(), "default_template", "classic"),
                "ai_mode": repo.get_setting(db(), "ai_mode", "auto"),
            },
            weights=DEFAULT_WEIGHTS,
            templates=RESUME_TEMPLATES,
            counts={
                "resumes": repo.count_resumes(db()),
                "jobs": len(repo.list_jobs(db(), limit=100)),
                "exports": len(repo.list_exports(db(), limit=100)),
            },
        )

    # ------------------------------------------------------------------
    # Profile API
    # ------------------------------------------------------------------
    @app.get("/api/profile")
    def api_get_profile():
        return jsonify({"ok": True, "profile": current_profile()})

    @app.post("/api/profile")
    def api_save_profile():
        payload = request.get_json(silent=True)
        data, errors = clean_profile_payload(payload)
        if errors:
            return json_error(errors[0], 400, errors=errors)
        saved = repo.save_profile(db(), data)
        return jsonify({"ok": True, "profile": saved, "completeness": profile_completeness(saved)})

    @app.get("/api/summary")
    def api_summary():
        profile = current_profile()
        latest = repo.latest_match(db())
        return jsonify(
            {
                "ok": True,
                "profile_name": profile.get("full_name") or "",
                "completeness": profile_completeness(profile),
                "resumes": repo.list_resumes(db(), limit=5),
                "latest_match": latest,
                "counts": {
                    "resumes": repo.count_resumes(db()),
                    "jobs": len(repo.list_jobs(db(), limit=100)),
                    "exports": len(repo.list_exports(db(), limit=100)),
                },
            }
        )

    # ------------------------------------------------------------------
    # Resume API
    # ------------------------------------------------------------------
    @app.get("/api/resumes")
    def api_list_resumes():
        return jsonify({"ok": True, "resumes": repo.list_resumes(db())})

    @app.post("/api/resumes")
    def api_create_resume():
        payload = request.get_json(silent=True) or {}
        profile = current_profile()
        if not profile.get("full_name") and not profile.get("skills"):
            return json_error(
                "Your master profile is empty. Add your details first, or load the demonstration profile.",
                400,
                needs_profile=True,
            )
        template = safe_template(payload.get("template") or repo.get_setting(db(), "default_template", "classic"))
        job_id = payload.get("job_id")
        if job_id is not None:
            try:
                job_id = int(job_id)
            except (TypeError, ValueError):
                return json_error("Invalid job reference.")
            if not repo.get_job(db(), job_id):
                return json_error("That analysed job no longer exists.", 404)
        title = payload.get("title")
        resume_id = repo.create_resume_from_profile(
            db(), profile, title=title if isinstance(title, str) else None, template=template, job_id=job_id
        )
        return jsonify(
            {
                "ok": True,
                "resume_id": resume_id,
                "redirect": url_for("builder_page", resume_id=resume_id),
            }
        )

    @app.get("/api/resumes/<int:resume_id>")
    def api_get_resume(resume_id: int):
        resume = repo.get_resume(db(), resume_id)
        if not resume:
            return json_error("Resume not found.", 404)
        return jsonify({"ok": True, "resume": resume})

    @app.put("/api/resumes/<int:resume_id>")
    @app.post("/api/resumes/<int:resume_id>")
    def api_save_resume(resume_id: int):
        existing = repo.get_resume(db(), resume_id)
        if not existing:
            return json_error("Resume not found.", 404)
        payload = request.get_json(silent=True) or {}
        content, errors, sections = clean_resume_content(payload, existing["content"])
        if errors:
            return json_error(errors[0], 400, errors=errors)
        title = payload.get("title") if isinstance(payload.get("title"), str) else existing["title"]
        template = safe_template(payload.get("template") or existing["template"])
        repo.update_resume(
            db(),
            resume_id,
            {"title": title, "template": template, "content": content, "sections": sections},
        )
        return jsonify(
            {
                "ok": True,
                "saved_at": repo.get_resume(db(), resume_id)["updated_at"],
                "sections": sections,
                "content": content,
            }
        )

    @app.delete("/api/resumes/<int:resume_id>")
    def api_delete_resume(resume_id: int):
        if not repo.delete_resume(db(), resume_id):
            return json_error("Resume not found.", 404)
        return jsonify({"ok": True})

    # ------------------------------------------------------------------
    # Job analysis
    # ------------------------------------------------------------------
    @app.post("/api/jobs/fetch")
    def api_fetch_job():
        payload = request.get_json(silent=True) or {}
        url = payload.get("url")
        if not isinstance(url, str) or not url.strip():
            return json_error("Enter a job posting URL first.")
        try:
            result = fetch_job_description(url)
        except FetchError as exc:
            return json_error(str(exc), 400, paste_fallback=True)
        return jsonify({"ok": True, **result})

    @app.post("/api/jobs/analyze")
    def api_analyze_job():
        payload = request.get_json(silent=True) or {}
        data, errors = clean_job_payload(payload)
        if errors:
            return json_error(errors[0], 400, errors=errors)
        try:
            analysis = parse_job_description(
                data["description"], title=data["title"], company=data["company"], url=data["url"]
            )
        except ValueError as exc:
            return json_error(str(exc), 400)

        profile = current_profile()
        result = score_match(profile, analysis)
        stored_analysis = {key: value for key, value in analysis.items() if key != "description"}
        job_id = repo.save_job(
            db(), data["title"], data["company"], data["url"], data["description"], stored_analysis
        )
        match_id = repo.save_match(db(), job_id, None, result["score"], result)

        warnings = []
        if not profile.get("full_name") and not profile.get("skills"):
            warnings.append(
                "Your master profile is empty, so the score only reflects what is on the profile. "
                "Add your details or load the demonstration profile."
            )
        if not analysis.get("required_skills"):
            warnings.append("No required technical skills were detected in the description.")

        return jsonify(
            {
                "ok": True,
                "job_id": job_id,
                "match_id": match_id,
                "job": {
                    "title": data["title"],
                    "company": data["company"],
                    "url": data["url"],
                    "description": data["description"],
                },
                "analysis": stored_analysis,
                "match": result,
                "warnings": warnings,
                "candidate_name": profile.get("full_name") or "",
            }
        )

    @app.get("/api/jobs/<int:job_id>")
    def api_get_job(job_id: int):
        job = repo.get_job(db(), job_id)
        if not job:
            return json_error("Job not found.", 404)
        latest = repo.latest_match_for_job(db(), job_id)
        return jsonify(
            {
                "ok": True,
                "job": {
                    "id": job["id"],
                    "title": job["title"],
                    "company": job["company"],
                    "url": job["url"],
                    "description": job["description"],
                    "created_at": job["created_at"],
                },
                "analysis": job["analysis"],
                "match": latest["breakdown"] if latest else None,
            }
        )

    # ------------------------------------------------------------------
    # AI tailoring
    # ------------------------------------------------------------------
    @app.post("/api/resumes/<int:resume_id>/tailor")
    def api_tailor(resume_id: int):
        resume = repo.get_resume(db(), resume_id)
        if not resume:
            return json_error("Resume not found.", 404)
        payload = request.get_json(silent=True) or {}
        job_id = payload.get("job_id") or resume.get("job_id")
        if job_id:
            try:
                job_id = int(job_id)
            except (TypeError, ValueError):
                return json_error("Invalid job reference.")
        job = repo.get_job(db(), job_id) if job_id else None
        if not job:
            return json_error(
                "Analyse a job description first — tailoring needs the job requirements to work against.",
                400,
                needs_job=True,
            )
        profile = current_profile()
        force_fallback = repo.get_setting(db(), "ai_mode", "auto") == "fallback"
        result = tailor_resume(
            profile,
            job["analysis"],
            document=resume["content"],
            force_fallback=force_fallback,
        )
        return jsonify(
            {
                "ok": True,
                "tailoring": result,
                "job": {"id": job["id"], "title": job["title"], "company": job["company"]},
                "resume_id": resume_id,
            }
        )

    @app.get("/api/ai/status")
    def api_ai_status():
        return jsonify({"ok": True, "ai": ai_status()})

    # ------------------------------------------------------------------
    # Exports
    # ------------------------------------------------------------------
    @app.get("/export/<int:resume_id>/<fmt>")
    def export_resume(resume_id: int, fmt: str):
        fmt = fmt.lower()
        if fmt not in ("pdf", "docx"):
            abort(404)
        resume = repo.get_resume(db(), resume_id)
        if not resume:
            flash("That resume could not be found. It may have been deleted.", "error")
            return redirect(url_for("builder_page"))
        template = safe_template(resume["template"])
        try:
            if fmt == "pdf":
                blob = build_pdf(resume["content"], resume["sections"], template)
                mimetype = "application/pdf"
            else:
                blob = build_docx(resume["content"], resume["sections"], template)
                mimetype = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        except Exception:  # noqa: BLE001 - surfaced to the user with a clear message
            app.logger.exception("Export failed for resume %s (%s)", resume_id, fmt)
            flash(
                f"The {fmt.upper()} export failed. Your edits are safe — please try again or switch templates.",
                "error",
            )
            return redirect(url_for("builder_page", resume_id=resume_id))

        name = filename_for(resume["content"].get("basics", {}).get("full_name"), template, fmt)
        repo.record_export(db(), resume_id, name, fmt, template)
        return send_file(BytesIO(blob), mimetype=mimetype, as_attachment=True, download_name=name)

    # ------------------------------------------------------------------
    # Settings, demo data, reset
    # ------------------------------------------------------------------
    @app.post("/settings")
    def save_settings_form():
        template = safe_template(request.form.get("default_template"))
        ai_mode = "fallback" if request.form.get("ai_mode") == "fallback" else "auto"
        repo.set_setting(db(), "default_template", template)
        repo.set_setting(db(), "ai_mode", ai_mode)
        flash("Settings saved.", "success")
        return redirect(url_for("settings_page"))

    @app.post("/api/settings")
    def api_save_settings():
        payload = request.get_json(silent=True) or {}
        repo.set_setting(db(), "default_template", safe_template(payload.get("default_template")))
        repo.set_setting(
            db(), "ai_mode", "fallback" if payload.get("ai_mode") == "fallback" else "auto"
        )
        return jsonify({"ok": True})

    @app.post("/api/demo/load")
    def api_demo_load():
        result = load_demo(db(), template=repo.get_setting(db(), "default_template", "classic"))
        return jsonify(
            {
                "ok": True,
                "job_id": result["job_id"],
                "resume_id": result["resume_id"],
                "score": result["score"],
                "redirect": url_for("builder_page", resume_id=result["resume_id"]),
                "matcher_url": url_for("matcher_page", job_id=result["job_id"]),
            }
        )

    @app.post("/demo/start")
    def demo_start():
        result = load_demo(db(), template=repo.get_setting(db(), "default_template", "classic"))
        flash(
            f"Demonstration profile loaded for {DEMO_PROFILE['full_name']} (fictional candidate) with a sample job.",
            "success",
        )
        return redirect(url_for("matcher_page", job_id=result["job_id"]))

    def _reset():
        repo.reset_all(db())
        repo.set_setting(db(), "demo_loaded", "0")
        repo.set_setting(db(), "default_template", "classic")
        repo.set_setting(db(), "ai_mode", "auto")

    @app.post("/api/data/reset")
    def api_reset():
        _reset()
        return jsonify({"ok": True})

    @app.post("/data/reset")
    def reset_form():
        _reset()
        flash("All ResumeIQ data has been cleared.", "success")
        return redirect(url_for("dashboard_page"))

    # ------------------------------------------------------------------
    # Health, errors
    # ------------------------------------------------------------------
    @app.get("/api/health")
    def health():
        return jsonify(
            {
                "ok": True,
                "app": "ResumeIQ",
                "ai_configured": ai_status()["configured"],
                "model": ai_status()["model"],
            }
        )

    @app.errorhandler(404)
    def not_found(error):
        if request.path.startswith("/api/"):
            return json_error("Not found.", 404)
        return render_template("error.html", code=404, title="Page not found",
                               message="That page does not exist.", active=""), 404

    @app.errorhandler(413)
    def too_large(error):
        if request.path.startswith("/api/"):
            return json_error("Request too large.", 413)
        return render_template("error.html", code=413, title="Request too large",
                               message="The submitted data was too large.", active=""), 413

    @app.errorhandler(500)
    def server_error(error):
        app.logger.exception("Unhandled error: %s", error)
        if request.path.startswith("/api/"):
            return json_error("Unexpected server error. Please try again.", 500)
        return render_template("error.html", code=500, title="Something went wrong",
                               message="An unexpected error occurred. Your saved data is intact.", active=""), 500

    return app


app = create_app()


if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    print(f"\n  ResumeIQ running on http://{host}:{port}\n")
    app.run(host=host, port=port, debug=debug)
