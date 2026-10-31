"""Real PDF and DOCX generation tests."""

from __future__ import annotations

from io import BytesIO

from docx import Document
from pypdf import PdfReader

from database import repo
from services.resume_export import build_docx, build_pdf, filename_for


def _resume(db_path, demo_profile):
    profile = repo.save_profile(db_path, demo_profile)
    resume_id = repo.create_resume_from_profile(db_path, profile, "Export test", template="classic")
    return repo.get_resume(db_path, resume_id)


def test_pdf_is_real_and_contains_resume_text(db_path, demo_profile):
    resume = _resume(db_path, demo_profile)
    blob = build_pdf(resume["content"], resume["sections"], "classic")

    assert blob.startswith(b"%PDF")
    assert len(blob) > 3000

    reader = PdfReader(BytesIO(blob))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "Aarav Sharma" in text
    assert "Python" in text
    assert "PROFESSIONAL SUMMARY" in text.upper()
    assert "EXPERIENCE" in text.upper()
    assert "PROJECTS" in text.upper()
    # No page should be blank.
    assert all((page.extract_text() or "").strip() for page in reader.pages)


def test_pdf_respects_section_order_and_visibility(db_path, demo_profile):
    resume = _resume(db_path, demo_profile)
    sections = [
        {"section_key": "education", "label": "Education", "visible": True},
        {"section_key": "projects", "label": "Projects", "visible": True},
        {"section_key": "summary", "label": "Professional Summary", "visible": False},
    ]
    blob = build_pdf(resume["content"], sections, "modern")
    text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(blob)).pages)

    assert text.index("EDUCATION") < text.index("PROJECTS")
    assert "Aarav Sharma" in text
    # The summary is hidden in this configuration.
    assert "Final-year Computer Science student" not in text


def test_pdf_handles_long_content_without_blank_pages(db_path, demo_profile):
    demo_profile["experience"] = []
    for role_index in range(6):
        demo_profile["experience"].append(
            {
                "role": f"Backend Intern {role_index + 1}",
                "company": "Example Technologies",
                "start_date": "Jan 2023",
                "end_date": "Jun 2023",
                "location": "Bengaluru",
                "description": "\n".join(
                    f"Delivered backend improvement {role_index}-{bullet} with clear documentation and tests for the internal platform."
                    for bullet in range(9)
                ),
            }
        )
    resume = _resume(db_path, demo_profile)
    blob = build_pdf(resume["content"], resume["sections"], "minimal")
    reader = PdfReader(BytesIO(blob))

    assert len(reader.pages) >= 2
    for page in reader.pages:
        assert len((page.extract_text() or "").strip()) > 20


def test_docx_is_real_word_document(db_path, demo_profile):
    resume = _resume(db_path, demo_profile)
    blob = build_docx(resume["content"], resume["sections"], "classic")

    assert blob.startswith(b"PK")
    document = Document(BytesIO(blob))
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    assert "Aarav Sharma" in text
    assert "EDUCATION" in text
    assert "PROJECTS" in text
    assert any(paragraph.style.name == "List Bullet" for paragraph in document.paragraphs)
    assert "Built a MERN application" in text

    # Headings should be real heading paragraphs, not just bold text.
    heading_styles = {paragraph.style.name for paragraph in document.paragraphs}
    assert "Heading 2" in heading_styles


def test_docx_hides_sections_and_keeps_custom_sections(db_path, demo_profile):
    resume = _resume(db_path, demo_profile)
    content = dict(resume["content"])
    content["custom_sections"] = [
        {"id": "vol", "title": "Volunteering", "bullets": ["Mentored 20 first-year students in Python."]}
    ]
    sections = [
        {"section_key": "summary", "label": "Professional Summary", "visible": False},
        {"section_key": "skills", "label": "Skills", "visible": True},
        {"section_key": "custom:vol", "label": "Volunteering", "visible": True},
    ]
    blob = build_docx(content, sections, "minimal")
    document = Document(BytesIO(blob))
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)

    assert "VOLUNTEERING" in text
    assert "Mentored 20 first-year students" in text
    assert "Final-year Computer Science student" not in text
    assert "EXPERIENCE" not in text


def test_templates_produce_different_documents(db_path, demo_profile):
    resume = _resume(db_path, demo_profile)
    classic = build_pdf(resume["content"], resume["sections"], "classic")
    modern = build_pdf(resume["content"], resume["sections"], "modern")
    minimal = build_pdf(resume["content"], resume["sections"], "minimal")

    assert classic != modern != minimal
    for blob in (classic, modern, minimal):
        assert blob.startswith(b"%PDF")


def test_export_filenames_are_safe():
    assert filename_for("Aarav Sharma", "classic", "pdf") == "aarav-sharma-classic.pdf"
    assert filename_for("../../etc/passwd", "modern", "docx") == "etc-passwd-modern.docx"
    assert filename_for("", "minimal", "pdf") == "resume-minimal.pdf"
