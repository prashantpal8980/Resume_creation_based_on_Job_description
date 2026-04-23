"""
PDF Generator Service — LaTeX-Based
Generates ATS-friendly, single-page resume PDFs by filling content into
the existing latex_code.tex template and compiling with pdflatex.

Only content sections are updated — the LaTeX structure, formatting,
links, badge, and icons remain untouched.
"""

import os
import json
import re
import subprocess
import shutil
import tempfile
from datetime import datetime
from typing import Dict, Any, List, Optional


# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GENERATED_DIR = os.path.join(BASE_DIR, "generated")
HISTORY_DIR = os.path.join(BASE_DIR, "history")
TEMPLATE_TEX = os.path.join(BASE_DIR, "latex_code.tex")
BADGE_IMAGE = os.path.join(BASE_DIR, "ceh_v13_badge.png")

# MiKTeX path (auto-detected)
PDFLATEX_PATH = None


def _find_pdflatex() -> str:
    """Find pdflatex executable."""
    global PDFLATEX_PATH
    if PDFLATEX_PATH:
        return PDFLATEX_PATH

    # Check PATH first
    try:
        result = subprocess.run(
            ["pdflatex", "--version"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            PDFLATEX_PATH = "pdflatex"
            return PDFLATEX_PATH
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Check common MiKTeX locations on Windows
    candidates = [
        r"C:\Program Files\MiKTeX\miktex\bin\x64\pdflatex.exe",
        r"C:\Program Files (x86)\MiKTeX\miktex\bin\x64\pdflatex.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\MiKTeX\miktex\bin\x64\pdflatex.exe"),
        os.path.expandvars(r"%APPDATA%\MiKTeX\miktex\bin\x64\pdflatex.exe"),
    ]
    for path in candidates:
        if os.path.exists(path):
            PDFLATEX_PATH = path
            return PDFLATEX_PATH

    raise FileNotFoundError(
        "pdflatex not found. Please install MiKTeX from https://miktex.org/download"
    )


def ensure_dirs():
    """Ensure output directories exist."""
    os.makedirs(GENERATED_DIR, exist_ok=True)
    os.makedirs(HISTORY_DIR, exist_ok=True)


# ─────────────────────────────────────────────
# LaTeX Escaping
# ─────────────────────────────────────────────

def _escape_latex(text: str) -> str:
    """
    Escape special LaTeX characters in plain text.
    Does NOT process text that already contains LaTeX commands.
    """
    if not text:
        return ""
    # Order matters: backslash first, then others
    replacements = [
        ('\\', r'\textbackslash{}'),
        ('&', r'\&'),
        ('%', r'\%'),
        ('$', r'\$'),
        ('#', r'\#'),
        ('_', r'\_'),
        ('{', r'\{'),
        ('}', r'\}'),
        ('~', r'\textasciitilde{}'),
        ('^', r'\textasciicircum{}'),
    ]
    for char, replacement in replacements:
        text = text.replace(char, replacement)
    return text


def _smart_escape(text: str) -> str:
    """
    Escape text for LaTeX but preserve intentional LaTeX formatting
    that the AI might include (like \\textbf{}).
    
    Strategy: escape only the dangerous chars that aren't part of commands.
    Since we control the template, we just escape the content text.
    """
    if not text:
        return ""
    # Escape & and % which are the most common problematic chars in resume content
    # Don't escape backslash, braces — the AI shouldn't produce those
    text = text.replace('&', r'\&')
    text = text.replace('%', r'\%')
    text = text.replace('#', r'\#')
    text = text.replace('$', r'\$')
    # Don't escape _ — it's used in URLs and technical terms but those are in \href
    # Handle standalone underscores not in URLs
    return text


def _bold_keywords(text: str) -> str:
    """
    Add \\textbf{} around key metrics and percentages in bullet text
    to match the original resume style.
    
    Matches patterns like: 99.5%, 5+, 80% accuracy, 20% reduction, etc.
    """
    # Bold percentages with context (e.g., "99.5% data accuracy")
    text = re.sub(
        r'(\d+\.?\d*\%)',
        r'\\textbf{\1}',
        text
    )
    # Bold "N+" patterns (e.g., "5+ global technology clients")
    text = re.sub(
        r'(\d+\+)',
        r'\\textbf{\1}',
        text
    )
    return text


# ─────────────────────────────────────────────
# Section Builders
# ─────────────────────────────────────────────

def _build_summary(summary: str) -> str:
    """Build the Professional Summary section."""
    escaped = _smart_escape(summary)
    return (
        "% --- SUMMARY ---\n"
        "\\section{Professional Summary}\n"
        f"\\noindent {escaped}\n"
    )


def _build_skills(skills: list) -> str:
    """
    Build the Technical Skills section.
    
    Accepts either:
    - List of {category, items} dicts (preferred)
    - Flat list of strings (backward compat — will be grouped as single category)
    """
    lines = [
        "% --- SKILLS ---\n"
        "\\section{Technical Skills}\n"
        "\\begin{itemize}"
    ]

    if not skills:
        lines.append("    \\item No skills listed.")
    elif isinstance(skills[0], dict) and "category" in skills[0]:
        # Categorized format
        for skill in skills:
            category = _smart_escape(skill.get("category", ""))
            items = _smart_escape(skill.get("items", ""))
            lines.append(f"    \\item \\textbf{{{category}:}} {items}")
    else:
        # Flat list — group as single line
        escaped = [_smart_escape(s) for s in skills]
        lines.append(f"    \\item {', '.join(escaped)}")

    lines.append("\\end{itemize}")
    return "\n".join(lines) + "\n"


def _build_certifications(certifications: list) -> str:
    """
    Build the Certifications section.
    
    Accepts either:
    - List of {name, issuer, date} dicts (preferred)
    - Flat list of strings (backward compat)
    """
    lines = [
        "% --- CERTIFICATIONS ---\n"
        "\\section{Certifications}\n"
        "\\begin{itemize}"
    ]

    if not certifications:
        lines.append("    \\item No certifications listed.")
    elif isinstance(certifications[0], dict) and "name" in certifications[0]:
        for cert in certifications:
            name = _smart_escape(cert.get("name", ""))
            issuer = _smart_escape(cert.get("issuer", ""))
            date = cert.get("date", "")
            issuer_part = f" -- {issuer}" if issuer else ""
            date_part = f" \\hfill {date}" if date else ""
            lines.append(f"    \\item \\textbf{{{name}}}{issuer_part}{date_part}")
    else:
        # Flat string list
        for cert in certifications:
            lines.append(f"    \\item {_smart_escape(str(cert))}")

    lines.append("\\end{itemize}")
    return "\n".join(lines) + "\n"


def _build_experience(experience: list) -> str:
    """Build the Professional Experience section with company/title/location/dates + bullets."""
    lines = [
        "% --- EXPERIENCE ---\n"
        "\\section{Professional Experience}"
    ]

    for exp in experience:
        company = _smart_escape(exp.get("company", ""))
        title = _smart_escape(exp.get("title", ""))
        location = _smart_escape(exp.get("location", ""))
        dates = exp.get("dates", "")
        bullets = exp.get("bullets", [])

        # Header line: Company | Title \hfill Location
        location_part = f" \\hfill \\textbf{{{location}}}" if location else ""
        lines.append(f"\\noindent \\textbf{{{company}}} $|$ {{{title}}}{location_part} \\\\")
        lines.append(f"{{{dates}}}")
        
        if bullets:
            lines.append("\\begin{itemize}")
            for bullet in bullets:
                escaped = _smart_escape(bullet)
                escaped = _bold_keywords(escaped)
                lines.append(f"    \\item {escaped}")
            lines.append("\\end{itemize}")
        lines.append("")

    return "\n".join(lines) + "\n"


def _build_projects(projects: list, original_projects: list) -> str:
    """
    Build the Projects section.
    
    Preserves the original link_text (href with FontAwesome icons) from
    the template, but updates bullet content from the AI.
    
    original_projects: parsed from the original .tex to preserve links.
    """
    lines = [
        "% --- PROJECTS ---\n\n"
        "\\section{Projects}\n"
    ]

    # Build a lookup of original project links by project name
    orig_links = {}
    for proj in original_projects:
        orig_links[proj["name"].lower().strip()] = proj.get("link_line", "")

    for proj in projects:
        name = proj.get("name", "")
        dates = proj.get("dates", "")
        bullets = proj.get("bullets", [])
        
        # Try to find the original link for this project
        link_line = orig_links.get(name.lower().strip(), "")
        
        # Build project header
        name_escaped = _smart_escape(name)
        if link_line:
            lines.append(f"\\noindent \\textbf{{{name_escaped}}} $|$ ")
            lines.append(f"{link_line}")
        else:
            lines.append(f"\\noindent \\textbf{{{name_escaped}}}")
        
        if dates:
            lines.append(f"\\hfill {dates}")
        
        if bullets:
            lines.append("\\begin{itemize}")
            for bullet in bullets:
                escaped = _smart_escape(bullet)
                escaped = _bold_keywords(escaped)
                lines.append(f"    \\item {escaped}")
            lines.append("\\end{itemize}")
        lines.append("")

    return "\n".join(lines) + "\n"


# ─────────────────────────────────────────────
# Template Parsing
# ─────────────────────────────────────────────

def _parse_original_projects(tex_content: str) -> list:
    """
    Parse the original .tex file to extract project names and their
    link lines (\\href{...}{\\faIcon ...}) so we can preserve them.
    """
    projects = []
    
    # Split into project blocks — each starts with \noindent \textbf{
    project_pattern = re.compile(
        r'\\noindent\s+\\textbf\{([^}]+)\}\s*\$\|\$\s*\n?(.*?)(?=\\begin\{itemize\})',
        re.DOTALL
    )
    
    # Find the projects section
    proj_section_match = re.search(
        r'% --- PROJECTS ---.*?(?=% --- EDUCATION ---|\\end\{document\})',
        tex_content, re.DOTALL
    )
    
    if not proj_section_match:
        return projects
    
    proj_text = proj_section_match.group()
    
    # Parse each project block
    blocks = re.split(r'(?=\\noindent\s+\\textbf\{)', proj_text)
    
    for block in blocks:
        if not block.strip() or '\\textbf{' not in block:
            continue
        
        # Extract project name
        name_match = re.search(r'\\textbf\{([^}]+)\}', block)
        if not name_match:
            continue
        name = name_match.group(1)
        
        # Extract the full link part (everything between $|$ and \hfill or \begin{itemize})
        # This captures \href{...}{...} lines with FontAwesome icons
        link_line = ""
        link_match = re.search(
            r'\$\|\$\s*\n?(.*?)(?=\\hfill|$)',
            block, re.DOTALL
        )
        if link_match:
            candidate = link_match.group(1).strip()
            if '\\href' in candidate or '\\fa' in candidate:
                link_line = candidate
        
        # Extract dates
        dates = ""
        dates_match = re.search(r'\\hfill\s+(.*?)(?:\n|$)', block)
        if dates_match:
            dates = dates_match.group(1).strip()
        
        projects.append({
            "name": name,
            "link_line": link_line,
            "dates": dates,
        })
    
    return projects


def _read_fixed_sections(tex_content: str) -> dict:
    """
    Extract the fixed (non-changing) parts from the template:
    - preamble (everything before \\begin{document})
    - contact_and_badge (contact info + CEH badge)
    - education section
    - document end
    """
    parts = {}
    
    # Preamble: everything up to and including \begin{document}
    preamble_match = re.search(r'(.*?\\begin\{document\})', tex_content, re.DOTALL)
    parts["preamble"] = preamble_match.group(1) if preamble_match else ""
    
    # Contact + Badge: from \begin{document} to first section marker
    contact_match = re.search(
        r'(% --- CONTACT INFO ---.*?% --- CEH BADGE ---.*?)(?=% --- (?:SUMMARY|SKILLS|CERT|EXPERIENCE|PROJECTS|EDUCATION) ---)',
        tex_content, re.DOTALL
    )
    parts["contact_and_badge"] = contact_match.group(1).strip() if contact_match else ""
    
    # Education: fixed section
    edu_match = re.search(
        r'(% --- EDUCATION ---.*?)(?=\\end\{document\})',
        tex_content, re.DOTALL
    )
    parts["education"] = edu_match.group(1).strip() if edu_match else ""
    
    return parts


# ─────────────────────────────────────────────
# Main Generator
# ─────────────────────────────────────────────

def generate_resume_pdf(
    resume_data: Dict[str, Any],
    job_title: str = "Resume",
    platform_used: str = "unknown",
) -> Dict[str, str]:
    """
    Generate a resume PDF by filling AI content into the LaTeX template.
    
    1. Read latex_code.tex for fixed sections (preamble, contact, badge, education)
    2. Build content sections from AI data (summary, skills, certs, experience, projects)
    3. Assemble in the AI-recommended section order
    4. Compile with pdflatex
    
    Returns:
        Dict with 'filename', 'filepath', 'preview_url', 'download_url'
    """
    ensure_dirs()

    # Read the original template
    with open(TEMPLATE_TEX, "r", encoding="utf-8") as f:
        original_tex = f.read()

    # Extract fixed sections from template
    fixed = _read_fixed_sections(original_tex)
    
    # Parse original projects to preserve their links
    original_projects = _parse_original_projects(original_tex)
    print(f"[LaTeX] Parsed {len(original_projects)} original projects with links")

    # Extract AI data
    summary = resume_data.get("summary", "")
    skills = resume_data.get("skills", [])
    experience = resume_data.get("experience", [])
    projects = resume_data.get("projects", [])
    certifications = resume_data.get("certifications", [])
    section_order = resume_data.get("section_order", [
        "summary", "skills", "certifications", "experience", "projects", "education"
    ])

    # Build each content section
    section_content = {
        "summary": _build_summary(summary),
        "skills": _build_skills(skills),
        "certifications": _build_certifications(certifications),
        "experience": _build_experience(experience),
        "projects": _build_projects(projects, original_projects),
        "education": fixed["education"],
    }

    # Assemble the full LaTeX document
    doc_parts = [
        fixed["preamble"],
        "",
        fixed["contact_and_badge"],
        "",
    ]

    # Add sections in the recommended order
    for section in section_order:
        if section in section_content:
            doc_parts.append(section_content[section])

    # Any sections not in the order (safety net)
    for section in section_content:
        if section not in section_order:
            doc_parts.append(section_content[section])

    doc_parts.append("\\end{document}")

    full_tex = "\n".join(doc_parts)

    # Write to a temp .tex file in the project directory (so badge image is accessible)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = resume_data.get("name", "Resume").replace(" ", "_")
    safe_job = "".join(c for c in job_title if c.isalnum() or c in (' ', '-', '_')).strip()[:30]
    safe_job = safe_job.replace(" ", "_") if safe_job else "Resume"
    
    tex_filename = f"{name}_{safe_job}_{timestamp}.tex"
    tex_filepath = os.path.join(BASE_DIR, tex_filename)

    with open(tex_filepath, "w", encoding="utf-8") as f:
        f.write(full_tex)

    print(f"[LaTeX] Wrote {len(full_tex)} chars to {tex_filename}")

    # Compile with pdflatex (run twice for proper references)
    pdflatex = _find_pdflatex()
    pdf_filename = tex_filename.replace(".tex", ".pdf")
    
    try:
        for run in range(2):
            result = subprocess.run(
                [
                    pdflatex,
                    "-interaction=nonstopmode",
                    f"-output-directory={GENERATED_DIR}",
                    tex_filepath,
                ],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=BASE_DIR,  # So badge image is found
            )
            
            if run == 1:  # Only check final run
                pdf_path = os.path.join(GENERATED_DIR, pdf_filename)
                if not os.path.exists(pdf_path):
                    # Check for errors in log
                    log_file = os.path.join(GENERATED_DIR, tex_filename.replace(".tex", ".log"))
                    error_msg = "LaTeX compilation failed."
                    if os.path.exists(log_file):
                        with open(log_file, "r", encoding="utf-8", errors="replace") as lf:
                            log = lf.read()
                        # Find the error lines
                        errors = re.findall(r'!(.*?)(?:\n(?:l\.\d+.*))?', log)
                        if errors:
                            error_msg += " Errors: " + "; ".join(e.strip() for e in errors[:3])
                    raise RuntimeError(error_msg)

        print(f"[LaTeX] PDF compiled successfully: {pdf_filename}")

    finally:
        # Clean up temp .tex file and auxiliary files
        for ext in [".tex", ".aux", ".log", ".out"]:
            cleanup = tex_filepath.replace(".tex", ext)
            if os.path.exists(cleanup):
                try:
                    os.remove(cleanup)
                except Exception:
                    pass
        # Also clean aux files from generated dir
        for ext in [".aux", ".log", ".out"]:
            cleanup = os.path.join(GENERATED_DIR, tex_filename.replace(".tex", ext))
            if os.path.exists(cleanup):
                try:
                    os.remove(cleanup)
                except Exception:
                    pass

    pdf_filepath = os.path.join(GENERATED_DIR, pdf_filename)

    # Save history metadata
    history_entry = {
        "filename": pdf_filename,
        "generated_at": datetime.now().isoformat(),
        "platform": platform_used,
        "job_title": job_title,
        "name": resume_data.get("name", ""),
        "skills_count": len(skills),
        "experience_count": len(experience),
    }

    history_file = os.path.join(HISTORY_DIR, f"{timestamp}.json")
    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(history_entry, f, indent=2)

    return {
        "filename": pdf_filename,
        "filepath": pdf_filepath,
        "preview_url": f"/api/preview/{pdf_filename}",
        "download_url": f"/api/download/{pdf_filename}",
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
