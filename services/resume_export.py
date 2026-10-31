"""Genuine PDF (ReportLab) and DOCX (python-docx) resume exports.

Both exporters read the latest saved resume document and follow the stored
section order/visibility. Text is escaped before it reaches ReportLab's
mini-markup, long tokens wrap instead of overflowing, and no forced page breaks
are used so empty pages cannot be produced.
"""

from __future__ import annotations

import re
from io import BytesIO
from typing import Any, Iterable
from xml.sax.saxutils import escape

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt, RGBColor
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import HRFlowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------
PDF_SPECS: dict[str, dict[str, Any]] = {
    "classic": {
        "name_size": 19,
        "name_color": "#111827",
        "headline_size": 9.6,
        "headline_color": "#374151",
        "contact_size": 9.0,
        "contact_color": "#374151",
        "section_size": 10.2,
        "section_color": "#111827",
        "rule_color": "#9CA3AF",
        "rule_thickness": 0.6,
        "body_size": 9.7,
        "body_leading": 12.8,
        "item_size": 10.0,
        "meta_size": 8.9,
        "meta_color": "#4B5563",
        "section_space": 11,
        "entry_space": 6,
        "bullet_space": 1.4,
        "bullet_indent": 12,
        "align": "left",
        "footer": False,
    },
    "modern": {
        "name_size": 24,
        "name_color": "#111C4E",
        "headline_size": 10.2,
        "headline_color": "#4338CA",
        "contact_size": 8.9,
        "contact_color": "#475569",
        "section_size": 10.6,
        "section_color": "#312E81",
        "rule_color": "#6366F1",
        "rule_thickness": 1.1,
        "body_size": 9.7,
        "body_leading": 13.0,
        "item_size": 10.0,
        "meta_size": 8.8,
        "meta_color": "#475569",
        "section_space": 13,
        "entry_space": 7,
        "bullet_space": 1.8,
        "bullet_indent": 12,
        "align": "center",
        "footer": True,
    },
    "minimal": {
        "name_size": 17,
        "name_color": "#0F172A",
        "headline_size": 9.0,
        "headline_color": "#475569",
        "contact_size": 8.4,
        "contact_color": "#475569",
        "section_size": 9.4,
        "section_color": "#0F172A",
        "rule_color": "#CBD5E1",
        "rule_thickness": 0.5,
        "body_size": 9.0,
        "body_leading": 11.6,
        "item_size": 9.3,
        "meta_size": 8.2,
        "meta_color": "#475569",
        "section_space": 9,
        "entry_space": 4,
        "bullet_space": 1.0,
        "bullet_indent": 10,
        "align": "left",
        "footer": True,
    },
}

DOCX_SPECS: dict[str, dict[str, Any]] = {
    "classic": {
        "body_font": "Calibri",
        "heading_font": "Calibri",
        "name_size": 20,
        "name_color": "111827",
        "headline_color": "374151",
        "heading_size": 11,
        "heading_color": "111827",
        "rule_color": "9CA3AF",
        "body_size": 10,
        "meta_size": 9,
        "meta_color": "4B5563",
        "align_center": False,
        "heading_before": 10,
        "compact": False,
    },
    "modern": {
        "body_font": "Calibri",
        "heading_font": "Georgia",
        "name_size": 23,
        "name_color": "111C4E",
        "headline_color": "4338CA",
        "heading_size": 11.5,
        "heading_color": "312E81",
        "rule_color": "6366F1",
        "body_size": 10,
        "meta_size": 9,
        "meta_color": "475569",
        "align_center": True,
        "heading_before": 12,
        "compact": False,
    },
    "minimal": {
        "body_font": "Calibri",
        "heading_font": "Calibri",
        "name_size": 18,
        "name_color": "0F172A",
        "headline_color": "475569",
        "heading_size": 10.5,
        "heading_color": "0F172A",
        "rule_color": "CBD5E1",
        "body_size": 9.5,
        "meta_size": 8.5,
        "meta_color": "475569",
        "align_center": False,
        "heading_before": 8,
        "compact": True,
    },
}


def _text(value: Any, limit: int = 2000) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        value = str(value)
    if not isinstance(value, str):
        return ""
    value = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    return value[:limit]


def _items(content: dict, key: str) -> list:
    value = content.get(key)
    return value if isinstance(value, list) else []


def _date_range(item: dict) -> str:
    start = _text(item.get("start_date"), 40)
    end = _text(item.get("end_date"), 40)
    if start and end:
        return f"{start} – {end}"
    return start or end


def _display_url(url: str) -> str:
    text = _text(url, 300)
    text = re.sub(r"^https?://", "", text, flags=re.I)
    return text.rstrip("/")


def visible_sections(sections: Iterable[dict] | None) -> list[dict]:
    """Return visible sections in stored order."""
    ordered = [section for section in (sections or []) if isinstance(section, dict)]
    ordered.sort(key=lambda item: item.get("position", 0))
    result = [section for section in ordered if section.get("visible", True)]
    if result:
        return result
    # No ordering supplied: fall back to the standard order.
    from database.repo import SECTION_LIBRARY

    return [{"section_key": key, "label": label, "visible": True} for key, label in SECTION_LIBRARY]


def _section_payload(key: str, content: dict) -> list:
    if key.startswith("custom:"):
        custom_id = key.split(":", 1)[1]
        for item in _items(content, "custom_sections"):
            if isinstance(item, dict) and item.get("id") == custom_id:
                return [text for text in item.get("bullets", []) if _text(text)]
        return []
    if key == "summary":
        text = _text(content.get("summary"), 3000)
        return [text] if text else []
    if key == "skills":
        return [_text(skill, 80) for skill in _items(content, "skills") if _text(skill)]
    if key in ("projects", "experience", "certifications", "education"):
        return [item for item in _items(content, key) if isinstance(item, dict)]
    return []


def _contact_parts(content: dict) -> list[str]:
    basics = content.get("basics") if isinstance(content.get("basics"), dict) else {}
    parts = []
    for key in ("email", "phone", "location"):
        value = _text(basics.get(key), 160)
        if value:
            parts.append(value)
    for key in ("linkedin", "github"):
        value = _display_url(basics.get(key))
        if value:
            parts.append(value)
    return parts


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------
def _pdf_styles(spec: dict) -> dict[str, ParagraphStyle]:
    align = TA_CENTER if spec["align"] == "center" else TA_LEFT
    return {
        "name": ParagraphStyle(
            "ri-name",
            fontName="Helvetica-Bold",
            fontSize=spec["name_size"],
            leading=spec["name_size"] * 1.16,
            textColor=colors.HexColor(spec["name_color"]),
            alignment=align,
            spaceAfter=1.5,
        ),
        "headline": ParagraphStyle(
            "ri-headline",
            fontName="Helvetica",
            fontSize=spec["headline_size"],
            leading=spec["headline_size"] * 1.35,
            textColor=colors.HexColor(spec["headline_color"]),
            alignment=align,
            spaceAfter=2,
            wordWrap="CJK",
        ),
        "contact": ParagraphStyle(
            "ri-contact",
            fontName="Helvetica",
            fontSize=spec["contact_size"],
            leading=spec["contact_size"] * 1.4,
            textColor=colors.HexColor(spec["contact_color"]),
            alignment=align,
            wordWrap="CJK",
        ),
        "section": ParagraphStyle(
            "ri-section",
            fontName="Helvetica-Bold",
            fontSize=spec["section_size"],
            leading=spec["section_size"] * 1.25,
            textColor=colors.HexColor(spec["section_color"]),
            spaceBefore=spec["section_space"],
            spaceAfter=1,
            alignment=TA_LEFT,
        ),
        "item": ParagraphStyle(
            "ri-item",
            fontName="Helvetica",
            fontSize=spec["item_size"],
            leading=spec["item_size"] * 1.26,
            textColor=colors.HexColor("#111827"),
            spaceBefore=0,
            spaceAfter=0,
        ),
        "meta": ParagraphStyle(
            "ri-meta",
            fontName="Helvetica",
            fontSize=spec["meta_size"],
            leading=spec["meta_size"] * 1.35,
            textColor=colors.HexColor(spec["meta_color"]),
            spaceAfter=1,
        ),
        "body": ParagraphStyle(
            "ri-body",
            fontName="Helvetica",
            fontSize=spec["body_size"],
            leading=spec["body_leading"],
            textColor=colors.HexColor("#111827"),
            spaceAfter=2,
        ),
        "bullet": ParagraphStyle(
            "ri-bullet",
            fontName="Helvetica",
            fontSize=spec["body_size"],
            leading=spec["body_leading"],
            textColor=colors.HexColor("#111827"),
            leftIndent=spec["bullet_indent"],
            bulletIndent=0,
            spaceAfter=spec["bullet_space"],
        ),
    }


def _pdf_heading(label: str, styles: dict, spec: dict) -> list:
    return [
        Paragraph(escape(label.upper()), styles["section"]),
        HRFlowable(
            width="100%",
            thickness=spec["rule_thickness"],
            color=colors.HexColor(spec["rule_color"]),
            spaceBefore=1,
            spaceAfter=4,
        ),
    ]


def _pdf_entry(title: str, secondary: str, meta_parts: list[str], bullets: list[str], styles, spec) -> list:
    head = f"<b>{escape(title)}</b>"
    if secondary:
        head += f" — {escape(secondary)}"
    flowables: list = [Paragraph(head, styles["item"])]
    meta = " · ".join(part for part in meta_parts if part)
    if meta:
        flowables.append(Paragraph(escape(meta), styles["meta"]))
    for bullet in bullets:
        if bullet:
            flowables.append(Paragraph(escape(bullet), styles["bullet"], bulletText="•"))
    return flowables


def _pdf_section_body(key: str, content: dict, styles, spec) -> list:
    payload = _section_payload(key, content)
    if not payload:
        return []
    body: list = []
    if key == "summary":
        for paragraph in payload[0].split("\n"):
            paragraph = paragraph.strip()
            if paragraph:
                body.append(Paragraph(escape(paragraph), styles["body"]))
        return body
    if key == "skills":
        return [Paragraph(escape("  •  ".join(payload)), styles["body"])]
    if key == "education":
        for item in payload:
            degree = " ".join(part for part in (_text(item.get("degree")), _text(item.get("field"))) if part)
            primary = degree or _text(item.get("institution")) or "Education"
            secondary = _text(item.get("institution")) if degree else ""
            meta = [_date_range(item), _text(item.get("score"), 60), _text(item.get("location"), 120)]
            body.extend(_pdf_entry(primary, secondary, meta, [], styles, spec))
            body.append(Spacer(1, spec["entry_space"] - 3))
        return body
    if key == "projects":
        for item in payload:
            meta = [_text(item.get("tech"), 220)]
            link = _display_url(item.get("link", ""))
            if link:
                meta.append(link)
            bullets = [_text(text, 600) for text in item.get("bullets", []) if _text(text)]
            body.extend(
                _pdf_entry(_text(item.get("name")) or "Project", "", [part for part in meta if part], bullets, styles, spec)
            )
            body.append(Spacer(1, spec["entry_space"] - 3))
        return body
    if key == "experience":
        for item in payload:
            meta = [_date_range(item), _text(item.get("location"), 120)]
            bullets = [_text(text, 600) for text in item.get("bullets", []) if _text(text)]
            body.extend(
                _pdf_entry(
                    _text(item.get("role")) or "Role",
                    _text(item.get("company")),
                    [part for part in meta if part],
                    bullets,
                    styles,
                    spec,
                )
            )
            body.append(Spacer(1, spec["entry_space"] - 3))
        return body
    if key == "certifications":
        for item in payload:
            name = _text(item.get("name")) or "Certification"
            issuer = _text(item.get("issuer"), 120)
            year = _text(item.get("year"), 20)
            line = f"<b>{escape(name)}</b>"
            if issuer:
                line += f" — {escape(issuer)}"
            if year:
                line += f" ({escape(year)})"
            body.append(Paragraph(line, styles["bullet"], bulletText="•"))
        return body
    for bullet in payload:
        body.append(Paragraph(escape(_text(bullet)), styles["bullet"], bulletText="•"))
    return body


def _pdf_footer(name: str, spec: dict):
    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor(spec["rule_color"]))
        canvas.setLineWidth(0.4)
        canvas.line(doc.leftMargin, 13 * mm, A4[0] - doc.rightMargin, 13 * mm)
        canvas.setFont("Helvetica", 7.4)
        canvas.setFillColor(colors.HexColor("#64748B"))
        canvas.drawString(doc.leftMargin, 8.5 * mm, name[:80])
        canvas.drawRightString(A4[0] - doc.rightMargin, 8.5 * mm, f"Page {doc.page}")
        canvas.restoreState()

    return footer


def build_pdf(content: dict, sections: Iterable[dict] | None, template: str = "classic") -> bytes:
    """Render an A4 PDF from the resume document."""
    template = template if template in PDF_SPECS else "classic"
    spec = PDF_SPECS[template]
    styles = _pdf_styles(spec)
    content = content if isinstance(content, dict) else {}
    basics = content.get("basics") if isinstance(content.get("basics"), dict) else {}

    name = _text(basics.get("full_name"), 120) or "Your Name"
    headline = _text(basics.get("headline"), 160)
    contacts = _contact_parts(content)

    story: list = [Paragraph(escape(name), styles["name"])]
    if headline:
        story.append(Paragraph(escape(headline), styles["headline"]))
    if contacts:
        story.append(Paragraph(escape("  •  ".join(contacts)), styles["contact"]))
    story.append(Spacer(1, 6))

    for section in visible_sections(sections):
        key = str(section.get("section_key", ""))
        label = _text(section.get("label"), 80) or key.replace(":", " ").title()
        body = _pdf_section_body(key, content, styles, spec)
        if not body:
            continue
        heading = _pdf_heading(label, styles, spec)
        story.append(KeepTogether(heading))
        story.extend(body)

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=17 * mm,
        rightMargin=17 * mm,
        topMargin=15 * mm,
        bottomMargin=18 * mm,
        title=f"{name} — Resume",
        author=name,
        subject="Resume generated with ResumeIQ",
        creator="ResumeIQ",
    )
    if spec["footer"]:
        footer = _pdf_footer(name, spec)
        doc.build(story, onFirstPage=footer, onLaterPages=footer)
    else:
        doc.build(story)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# DOCX
# ---------------------------------------------------------------------------
def _docx_border(paragraph, color: str) -> None:
    p_pr = paragraph._p.get_or_add_pPr()
    borders = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "6")
    bottom.set(qn("w:space"), "2")
    bottom.set(qn("w:color"), color)
    borders.append(bottom)
    p_pr.append(borders)


def _docx_run(run, font: str | None = None, size: float | None = None,
              color: str | None = None, bold: bool | None = None, italic: bool | None = None):
    if font:
        run.font.name = font
        rpr = run._element.get_or_add_rPr()
        rfonts = rpr.find(qn("w:rFonts"))
        if rfonts is None:
            rfonts = OxmlElement("w:rFonts")
            rpr.append(rfonts)
        rfonts.set(qn("w:ascii"), font)
        rfonts.set(qn("w:hAnsi"), font)
    if size is not None:
        run.font.size = Pt(size)
    if color:
        run.font.color.rgb = RGBColor.from_string(color.replace("#", "").upper())
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic


def _docx_heading(doc, label: str, spec: dict):
    paragraph = doc.add_heading(label.upper(), level=2)
    paragraph.paragraph_format.space_before = Pt(spec["heading_before"])
    paragraph.paragraph_format.space_after = Pt(3)
    paragraph.paragraph_format.keep_with_next = True
    for run in paragraph.runs:
        _docx_run(run, spec["heading_font"], spec["heading_size"], spec["heading_color"], True)
    _docx_border(paragraph, spec["rule_color"])
    return paragraph


def _docx_bullet(doc, text: str, spec: dict, space_after: float = 1.0) -> None:
    paragraph = doc.add_paragraph(text, style="List Bullet")
    paragraph.paragraph_format.space_after = Pt(space_after)
    if spec["compact"]:
        paragraph.paragraph_format.space_before = Pt(0)
    for run in paragraph.runs:
        _docx_run(run, spec["body_font"], spec["body_size"])


def _docx_entry(doc, title: str, secondary: str, meta_parts: list[str], bullets: list[str], spec: dict) -> None:
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.space_before = Pt(4 if not spec["compact"] else 3)
    paragraph.paragraph_format.space_after = Pt(1)
    paragraph.paragraph_format.keep_with_next = True
    run = paragraph.add_run(title)
    _docx_run(run, spec["body_font"], spec["body_size"] + 0.5, spec["name_color"], True)
    if secondary:
        run2 = paragraph.add_run(" — " + secondary)
        _docx_run(run2, spec["body_font"], spec["body_size"], spec["heading_color"])

    meta = " · ".join(part for part in meta_parts if part)
    if meta:
        meta_paragraph = doc.add_paragraph()
        meta_paragraph.paragraph_format.space_before = Pt(0)
        meta_paragraph.paragraph_format.space_after = Pt(2)
        meta_paragraph.paragraph_format.keep_with_next = bool(bullets)
        meta_run = meta_paragraph.add_run(meta)
        _docx_run(meta_run, spec["body_font"], spec["meta_size"], spec["meta_color"])

    for bullet in bullets:
        _docx_bullet(doc, bullet, spec)


def build_docx(content: dict, sections: Iterable[dict] | None, template: str = "classic") -> bytes:
    """Render a real .docx document with editable paragraphs and list bullets."""
    template = template if template in DOCX_SPECS else "classic"
    spec = DOCX_SPECS[template]
    content = content if isinstance(content, dict) else {}
    basics = content.get("basics") if isinstance(content.get("basics"), dict) else {}

    doc = Document()
    section = doc.sections[0]
    section.page_width = Mm(210)
    section.page_height = Mm(297)
    section.left_margin = Mm(17)
    section.right_margin = Mm(17)
    section.top_margin = Mm(15)
    section.bottom_margin = Mm(15)

    normal = doc.styles["Normal"]
    normal.font.name = spec["body_font"]
    normal.font.size = Pt(spec["body_size"])
    normal.paragraph_format.space_after = Pt(2)
    normal.paragraph_format.line_spacing = 1.05
    rpr = normal.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rfonts.set(qn(attr), spec["body_font"])

    name = _text(basics.get("full_name"), 120) or "Your Name"
    headline = _text(basics.get("headline"), 160)
    contacts = _contact_parts(content)

    name_paragraph = doc.add_paragraph()
    name_paragraph.paragraph_format.space_after = Pt(2)
    if spec["align_center"]:
        name_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    name_run = name_paragraph.add_run(name)
    _docx_run(name_run, spec["heading_font"], spec["name_size"], spec["name_color"], True)

    if headline:
        headline_paragraph = doc.add_paragraph()
        headline_paragraph.paragraph_format.space_after = Pt(2)
        if spec["align_center"]:
            headline_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _docx_run(
            headline_paragraph.add_run(headline),
            spec["body_font"],
            spec["body_size"] + 0.3,
            spec["headline_color"],
        )

    if contacts:
        contact_paragraph = doc.add_paragraph()
        contact_paragraph.paragraph_format.space_after = Pt(6)
        if spec["align_center"]:
            contact_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _docx_run(
            contact_paragraph.add_run("  •  ".join(contacts)),
            spec["body_font"],
            spec["meta_size"],
            spec["meta_color"],
        )

    for section_info in visible_sections(sections):
        key = str(section_info.get("section_key", ""))
        label = _text(section_info.get("label"), 80) or key.replace(":", " ").title()
        payload = _section_payload(key, content)
        if not payload:
            continue
        if key == "summary":
            _docx_heading(doc, label, spec)
            for paragraph in payload[0].split("\n"):
                if paragraph.strip():
                    text_paragraph = doc.add_paragraph()
                    text_paragraph.paragraph_format.space_after = Pt(3)
                    _docx_run(text_paragraph.add_run(paragraph.strip()), spec["body_font"], spec["body_size"])
            continue

        _docx_heading(doc, label, spec)

        if key == "skills":
            paragraph = doc.add_paragraph()
            paragraph.paragraph_format.space_after = Pt(2)
            _docx_run(paragraph.add_run("  •  ".join(payload)), spec["body_font"], spec["body_size"])
        elif key == "education":
            for item in payload:
                degree = " ".join(
                    part for part in (_text(item.get("degree")), _text(item.get("field"))) if part
                )
                primary = degree or _text(item.get("institution")) or "Education"
                secondary = _text(item.get("institution")) if degree else ""
                meta = [_date_range(item), _text(item.get("score"), 60), _text(item.get("location"), 120)]
                _docx_entry(doc, primary, secondary, meta, [], spec)
        elif key == "projects":
            for item in payload:
                meta = [_text(item.get("tech"), 220)]
                link = _display_url(item.get("link", ""))
                if link:
                    meta.append(link)
                bullets = [_text(text, 600) for text in item.get("bullets", []) if _text(text)]
                _docx_entry(doc, _text(item.get("name")) or "Project", "", meta, bullets, spec)
        elif key == "experience":
            for item in payload:
                meta = [_date_range(item), _text(item.get("location"), 120)]
                bullets = [_text(text, 600) for text in item.get("bullets", []) if _text(text)]
                _docx_entry(
                    doc,
                    _text(item.get("role")) or "Role",
                    _text(item.get("company")),
                    meta,
                    bullets,
                    spec,
                )
        elif key == "certifications":
            for item in payload:
                name_text = _text(item.get("name")) or "Certification"
                issuer = _text(item.get("issuer"), 120)
                year = _text(item.get("year"), 20)
                line = name_text
                if issuer:
                    line += f" — {issuer}"
                if year:
                    line += f" ({year})"
                _docx_bullet(doc, line, spec)
        else:
            for bullet in payload:
                _docx_bullet(doc, _text(bullet), spec)

    doc.core_properties.title = f"{name} — Resume"
    doc.core_properties.author = name
    doc.core_properties.subject = "Resume generated with ResumeIQ"
    doc.core_properties.comments = "Edit this document freely; it was generated from your ResumeIQ draft."

    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def filename_for(name: str | None, template: str, fmt: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", (name or "resume").lower()).strip("-")[:42] or "resume"
    return f"{base}-{template}.{fmt}"
