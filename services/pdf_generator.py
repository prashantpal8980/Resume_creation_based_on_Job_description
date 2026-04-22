"""
PDF Generator Service
Generates ATS-friendly, single-page resume PDFs using fpdf2.
Pure Python — no system dependencies needed (unlike WeasyPrint).
"""

import os
import json
from datetime import datetime
from typing import Dict, Any, List
from fpdf import FPDF


# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GENERATED_DIR = os.path.join(BASE_DIR, "generated")
HISTORY_DIR = os.path.join(BASE_DIR, "history")


def ensure_dirs():
    """Ensure output directories exist."""
    os.makedirs(GENERATED_DIR, exist_ok=True)
    os.makedirs(HISTORY_DIR, exist_ok=True)


def _sanitize(text: str) -> str:
    """Replace characters unsupported by latin-1 core fonts with safe ASCII alternatives."""
    if not text:
        return text
    replacements = {
        '\u2022': '-',   # bullet •
        '\u2013': '-',   # en-dash –
        '\u2014': '-',   # em-dash —
        '\u2018': "'",   # left single quote '
        '\u2019': "'",   # right single quote '
        '\u201c': '"',   # left double quote "
        '\u201d': '"',   # right double quote "
        '\u2026': '...', # ellipsis …
        '\u00a0': ' ',   # non-breaking space
        '\u2010': '-',   # hyphen ‐
        '\u2011': '-',   # non-breaking hyphen ‑
        '\u2012': '-',   # figure dash ‒
        '\u00b7': '-',   # middle dot ·
        '\u25cf': '-',   # black circle ●
        '\u25cb': '-',   # white circle ○
        '\u25aa': '-',   # black square ▪
        '\u00e9': 'e',   # é
        '&': 'and',
    }
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    # Final pass: strip any remaining non-latin-1 characters
    try:
        text.encode('latin-1')
    except UnicodeEncodeError:
        text = text.encode('latin-1', errors='replace').decode('latin-1')
    return text


class ResumePDF(FPDF):
    """Custom FPDF class for ATS-friendly resume generation."""

    def __init__(self):
        super().__init__(format='A4')
        self.set_auto_page_break(auto=False)
        # Colors
        self.COLOR_PRIMARY = (30, 58, 95)      # Dark navy
        self.COLOR_TEXT = (33, 33, 33)          # Near black
        self.COLOR_SECONDARY = (80, 80, 80)    # Dark gray
        self.COLOR_MUTED = (110, 110, 110)     # Medium gray
        self.COLOR_LINE = (180, 190, 200)      # Light blue-gray

    def _section_title(self, title: str):
        """Render a section heading with underline."""
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(*self.COLOR_PRIMARY)
        self.cell(0, 6, title.upper(), new_x="LMARGIN", new_y="NEXT")
        # Draw line under title
        y = self.get_y()
        self.set_draw_color(*self.COLOR_LINE)
        self.set_line_width(0.3)
        self.line(self.l_margin, y, self.w - self.r_margin, y)
        self.ln(2.5)

    def _bullet_point(self, text: str, indent: float = 14):
        """Render a bullet point with proper wrapping."""
        self.set_font("Helvetica", "", 9.5)
        self.set_text_color(*self.COLOR_TEXT)
        x = self.get_x()
        # Bullet character (use ASCII hyphen for latin-1 compatibility)
        self.set_x(indent)
        self.cell(4, 4.5, "-", new_x="END")
        # Text with wrapping
        available_width = self.w - self.r_margin - indent - 4
        self.multi_cell(available_width, 4.5, _sanitize(text), new_x="LMARGIN", new_y="NEXT")
        self.ln(0.5)

    def _check_space(self, needed: float) -> bool:
        """Check if there's enough space on the current page."""
        return (self.get_y() + needed) < (self.h - self.b_margin - 5)


def generate_resume_pdf(
    resume_data: Dict[str, Any],
    job_title: str = "Resume",
    platform_used: str = "unknown",
) -> Dict[str, str]:
    """
    Generate an ATS-friendly PDF resume from structured data.
    
    Args:
        resume_data: Parsed resume dictionary from response_parser
        job_title: Brief job title for filename
        platform_used: Which AI platform was used
        
    Returns:
        Dict with 'filename', 'filepath', 'preview_url', 'download_url'
    """
    ensure_dirs()

    pdf = ResumePDF()
    pdf.add_page()
    pdf.set_margins(14, 12, 14)
    pdf.set_y(12)

    name = resume_data.get("name", "Resume")
    contact = resume_data.get("contact", {})
    summary = resume_data.get("summary", "")
    skills = resume_data.get("skills", [])
    experience = resume_data.get("experience", [])
    projects = resume_data.get("projects", [])
    education = resume_data.get("education", [])
    certifications = resume_data.get("certifications", [])

    # ─── Header: Name ───
    pdf.set_font("Helvetica", "B", 20)
    pdf.set_text_color(*pdf.COLOR_PRIMARY)
    pdf.cell(0, 9, _sanitize(name), align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1.5)

    # ─── Contact Info ───
    contact_parts = []
    for key in ["email", "phone", "linkedin", "github", "location"]:
        val = contact.get(key, "").strip()
        if val:
            contact_parts.append(val)

    if contact_parts:
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*pdf.COLOR_MUTED)
        contact_line = "  |  ".join(contact_parts)
        pdf.cell(0, 5, _sanitize(contact_line), align="C", new_x="LMARGIN", new_y="NEXT")
    
    # Separator line
    pdf.ln(2)
    y = pdf.get_y()
    pdf.set_draw_color(*pdf.COLOR_PRIMARY)
    pdf.set_line_width(0.6)
    pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
    pdf.ln(4)

    # ─── Professional Summary ───
    if summary:
        pdf._section_title("Professional Summary")
        pdf.set_font("Helvetica", "", 9.5)
        pdf.set_text_color(*pdf.COLOR_TEXT)
        pdf.multi_cell(0, 4.5, _sanitize(summary), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3)

    # ─── Technical Skills ───
    if skills:
        pdf._section_title("Technical Skills")
        pdf.set_font("Helvetica", "", 9.5)
        pdf.set_text_color(*pdf.COLOR_TEXT)
        # Join skills with separator (use pipe for latin-1 compatibility)
        skills_text = "  |  ".join([_sanitize(s) for s in skills])
        pdf.multi_cell(0, 4.5, skills_text, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3)

    # ─── Professional Experience ───
    if experience:
        pdf._section_title("Professional Experience")
        for i, exp in enumerate(experience):
            title = exp.get("title", "")
            company = exp.get("company", "")
            dates = exp.get("dates", "")
            bullets = exp.get("bullets", [])

            # Title and Company
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(*pdf.COLOR_TEXT)
            
            title_company = _sanitize(title)
            if company:
                title_company += f"  -  {_sanitize(company)}"
            dates = _sanitize(dates)
            
            # Calculate dates width
            if dates:
                pdf.set_font("Helvetica", "", 9)
                dates_w = pdf.get_string_width(dates) + 2
                title_w = pdf.w - pdf.l_margin - pdf.r_margin - dates_w
            else:
                title_w = 0
                dates_w = 0

            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(*pdf.COLOR_TEXT)
            
            if dates:
                pdf.cell(title_w, 5, title_company, new_x="END")
                pdf.set_font("Helvetica", "", 9)
                pdf.set_text_color(*pdf.COLOR_MUTED)
                pdf.cell(dates_w, 5, dates, align="R", new_x="LMARGIN", new_y="NEXT")
            else:
                pdf.cell(0, 5, title_company, new_x="LMARGIN", new_y="NEXT")
            
            pdf.ln(1)

            # Bullets
            for bullet in bullets:
                if pdf._check_space(6):
                    pdf._bullet_point(bullet)

            if i < len(experience) - 1:
                pdf.ln(1.5)
        
        pdf.ln(2)

    # ─── Projects ───
    if projects:
        pdf._section_title("Projects")
        for i, proj in enumerate(projects):
            proj_name = proj.get("name", "")
            tech = proj.get("tech", "")
            bullets = proj.get("bullets", [])

            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(*pdf.COLOR_TEXT)
            
            proj_name = _sanitize(proj_name)
            tech = _sanitize(tech)
            if tech:
                pdf.cell(pdf.get_string_width(proj_name) + 2, 5, proj_name, new_x="END")
                pdf.set_font("Helvetica", "I", 9)
                pdf.set_text_color(*pdf.COLOR_MUTED)
                pdf.cell(0, 5, f"  |  {tech}", new_x="LMARGIN", new_y="NEXT")
            else:
                pdf.cell(0, 5, proj_name, new_x="LMARGIN", new_y="NEXT")
            
            pdf.ln(1)

            for bullet in bullets:
                if pdf._check_space(6):
                    pdf._bullet_point(bullet)

            if i < len(projects) - 1:
                pdf.ln(1)
        
        pdf.ln(2)

    # ─── Education ───
    if education:
        pdf._section_title("Education")
        for edu in education:
            degree = edu.get("degree", "")
            institution = edu.get("institution", "")
            dates = edu.get("dates", "")
            details = edu.get("details", "")

            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(*pdf.COLOR_TEXT)
            
            degree = _sanitize(degree)
            institution = _sanitize(institution)
            dates = _sanitize(dates)
            details = _sanitize(details)

            if dates:
                dates_w = pdf.get_string_width(dates) + 2
                title_w = pdf.w - pdf.l_margin - pdf.r_margin - dates_w
                pdf.cell(title_w, 5, degree, new_x="END")
                pdf.set_font("Helvetica", "", 9)
                pdf.set_text_color(*pdf.COLOR_MUTED)
                pdf.cell(dates_w, 5, dates, align="R", new_x="LMARGIN", new_y="NEXT")
            else:
                pdf.cell(0, 5, degree, new_x="LMARGIN", new_y="NEXT")

            if institution:
                pdf.set_font("Helvetica", "I", 9.5)
                pdf.set_text_color(*pdf.COLOR_SECONDARY)
                pdf.cell(0, 5, institution, new_x="LMARGIN", new_y="NEXT")

            if details:
                pdf.set_font("Helvetica", "", 9)
                pdf.set_text_color(*pdf.COLOR_MUTED)
                pdf.cell(0, 4.5, details, new_x="LMARGIN", new_y="NEXT")
            
            pdf.ln(1.5)
        
        pdf.ln(1)

    # ─── Certifications ───
    if certifications:
        pdf._section_title("Certifications")
        pdf.set_font("Helvetica", "", 9.5)
        pdf.set_text_color(*pdf.COLOR_TEXT)
        certs_text = "  |  ".join([_sanitize(c) for c in certifications])
        pdf.multi_cell(0, 4.5, certs_text, new_x="LMARGIN", new_y="NEXT")

    # ─── Save PDF ───
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = name.replace(" ", "_")
    safe_job = "".join(c for c in job_title if c.isalnum() or c in (' ', '-', '_')).strip()[:30]
    safe_job = safe_job.replace(" ", "_") if safe_job else "Resume"
    filename = f"{safe_name}_{safe_job}_{timestamp}.pdf"
    filepath = os.path.join(GENERATED_DIR, filename)

    pdf.output(filepath)

    # Save history metadata
    history_entry = {
        "filename": filename,
        "generated_at": datetime.now().isoformat(),
        "platform": platform_used,
        "job_title": job_title,
        "name": name,
        "skills_count": len(skills),
        "experience_count": len(experience),
    }

    history_file = os.path.join(HISTORY_DIR, f"{timestamp}.json")
    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(history_entry, f, indent=2)

    return {
        "filename": filename,
        "filepath": filepath,
        "preview_url": f"/api/preview/{filename}",
        "download_url": f"/api/download/{filename}",
    }


def get_generation_history() -> list:
    """Get list of previously generated resumes, newest first."""
    ensure_dirs()

    history = []
    for fname in sorted(os.listdir(HISTORY_DIR), reverse=True):
        if fname.endswith(".json"):
            fpath = os.path.join(HISTORY_DIR, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    entry = json.load(f)
                    history.append(entry)
            except Exception:
                continue

    return history[:20]
