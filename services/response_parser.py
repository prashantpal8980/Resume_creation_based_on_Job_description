"""
Response Parser Service
Parses the AI's response text into a structured resume dictionary.
Handles JSON wrapped in markdown fences, raw JSON, and free-text fallback.
"""

import json
import re
from typing import Dict, Any, Optional


def extract_json_from_text(text: str) -> Optional[Dict]:
    """
    Extract and parse JSON from AI response that might contain markdown
    fences, extra text, or other wrapping.
    
    Tries multiple strategies in order of reliability.
    """
    if not text or not text.strip():
        return None

    cleaned = text.strip()

    # ─── Strategy 1: Strip markdown code fences ───
    # Handles ```json\n{...}\n``` and ```\n{...}\n```
    fence_patterns = [
        r'```(?:json)?\s*\n?([\s\S]*?)\n?\s*```',
    ]
    for pattern in fence_patterns:
        matches = re.findall(pattern, cleaned, re.DOTALL)
        for match in matches:
            candidate = match.strip()
            if candidate.startswith('{'):
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    # Try fixing common issues
                    fixed = _fix_json_issues(candidate)
                    if fixed:
                        return fixed

    # ─── Strategy 2: Direct JSON parse ───
    if cleaned.startswith('{'):
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            # Try fixing newlines-in-strings and other issues
            fixed = _fix_json_issues(cleaned)
            if fixed:
                return fixed

    # ─── Strategy 3: Find the outermost balanced JSON object ───
    result = _find_balanced_json(cleaned)
    if result:
        return result

    # ─── Strategy 4: Aggressive extraction — find { and } ───
    first_brace = cleaned.find('{')
    last_brace = cleaned.rfind('}')
    if first_brace != -1 and last_brace > first_brace:
        candidate = cleaned[first_brace:last_brace + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            fixed = _fix_json_issues(candidate)
            if fixed:
                return fixed

    return None


def _find_balanced_json(text: str) -> Optional[Dict]:
    """Find the largest balanced JSON object in the text using brace counting."""
    start = text.find('{')
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape_next = False
    best_result = None

    for i in range(start, len(text)):
        c = text[i]

        if escape_next:
            escape_next = False
            continue

        if c == '\\' and in_string:
            escape_next = True
            continue

        if c == '"' and not escape_next:
            in_string = not in_string
            continue

        if in_string:
            continue

        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                candidate = text[start:i + 1]
                try:
                    parsed = json.loads(candidate)
                    # Prefer results with resume-like keys
                    if isinstance(parsed, dict):
                        has_resume_keys = any(
                            k in parsed for k in ['name', 'summary', 'skills', 'experience']
                        )
                        if has_resume_keys:
                            return parsed
                        if best_result is None:
                            best_result = parsed
                except json.JSONDecodeError:
                    pass
                # Reset to find the next potential JSON object
                start = text.find('{', i + 1)
                if start == -1:
                    break
                depth = 0

    return best_result


def _fix_json_issues(text: str) -> Optional[Dict]:
    """
    Fix common JSON issues from AI responses.
    
    Key issue: ChatGPT's inner_text() produces JSON with LITERAL newlines
    inside string values (e.g., "email@example.com\n"). This is invalid JSON.
    """
    # Step 1: Replace literal newlines inside JSON strings with spaces
    # Walk through the text and fix newlines that appear inside quoted strings
    fixed_chars = []
    in_string = False
    escape_next = False
    
    for c in text:
        if escape_next:
            fixed_chars.append(c)
            escape_next = False
            continue
        
        if c == '\\' and in_string:
            fixed_chars.append(c)
            escape_next = True
            continue
        
        if c == '"':
            in_string = not in_string
            fixed_chars.append(c)
            continue
        
        if in_string and c == '\n':
            fixed_chars.append(' ')  # Replace newline with space
            continue
        if in_string and c == '\r':
            continue  # Skip carriage returns
        
        fixed_chars.append(c)
    
    fixed = ''.join(fixed_chars)
    
    # Step 2: Remove trailing commas before } or ]
    fixed = re.sub(r',\s*([}\]])', r'\1', fixed)
    
    # Step 3: Remove any control characters
    fixed = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', fixed)
    
    try:
        return json.loads(fixed)
    except json.JSONDecodeError as e:
        print(f"[Parser] JSON fix still failed: {e}")
        return None


def parse_json_response(text: str) -> Optional[Dict[str, Any]]:
    """
    Try to parse the AI response as JSON.
    Returns the parsed dict or None if parsing fails.
    """
    return extract_json_from_text(text)


def parse_freetext_response(text: str) -> Dict[str, Any]:
    """
    Fallback parser: extract resume sections from free-text AI response
    when JSON parsing fails.
    """
    resume = {
        "name": "",
        "contact": {
            "email": "",
            "phone": "",
            "linkedin": "",
            "github": "",
            "location": ""
        },
        "summary": "",
        "skills": [],
        "experience": [],
        "projects": [],
        "education": [],
        "certifications": []
    }
    
    lines = text.split('\n')
    current_section = None
    current_entry = None
    
    section_patterns = {
        'summary': r'(?:professional\s+)?summary|(?:career\s+)?(?:objective|profile)',
        'skills': r'(?:technical\s+)?skills|technologies|competencies',
        'experience': r'(?:work\s+|professional\s+)?experience|employment(?:\s+history)?',
        'projects': r'projects|(?:key\s+)?projects',
        'education': r'education|academic|qualifications',
        'certifications': r'certifications?|licenses?|credentials',
        'contact': r'contact(?:\s+info(?:rmation)?)?',
    }
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        
        lower = stripped.lower().replace('*', '').replace('#', '').strip()
        matched_section = None
        for section, pattern in section_patterns.items():
            if re.match(pattern, lower):
                matched_section = section
                break
        
        if matched_section:
            current_section = matched_section
            current_entry = None
            continue
        
        if not resume["name"] and i < 5 and not current_section:
            if len(stripped.split()) <= 5 and not any(c in stripped for c in ['@', '•', '|', ':']):
                resume["name"] = stripped.replace('*', '').replace('#', '').strip()
                continue
        
        if current_section == 'summary':
            if resume["summary"]:
                resume["summary"] += " " + stripped
            else:
                resume["summary"] = stripped
        
        elif current_section == 'skills':
            skills = re.split(r'[,|•·]', stripped)
            for skill in skills:
                s = skill.strip().strip('-').strip('•').strip()
                if s and len(s) > 1:
                    resume["skills"].append(s)
        
        elif current_section == 'experience':
            if re.match(r'^[\w\s]+(?:\s+[-–|@]\s+|\s+at\s+)', stripped) or \
               (stripped.startswith('**') and '**' in stripped[2:]):
                current_entry = {
                    "title": "",
                    "company": "",
                    "dates": "",
                    "bullets": []
                }
                clean = stripped.replace('*', '').strip()
                parts = re.split(r'\s*[|–—]\s*', clean)
                if len(parts) >= 2:
                    current_entry["title"] = parts[0].strip()
                    current_entry["company"] = parts[1].strip()
                    if len(parts) >= 3:
                        current_entry["dates"] = parts[2].strip()
                else:
                    current_entry["title"] = clean
                resume["experience"].append(current_entry)
            elif current_entry and (stripped.startswith('-') or stripped.startswith('•') or stripped.startswith('*')):
                bullet = stripped.lstrip('-•* ').strip()
                if bullet:
                    current_entry["bullets"].append(bullet)
        
        elif current_section == 'projects':
            if stripped.startswith('**') or (not stripped.startswith('-') and not stripped.startswith('•')):
                current_entry = {
                    "name": stripped.replace('*', '').strip(),
                    "tech": "",
                    "bullets": []
                }
                resume["projects"].append(current_entry)
            elif current_entry and (stripped.startswith('-') or stripped.startswith('•')):
                bullet = stripped.lstrip('-•* ').strip()
                if bullet:
                    if any(kw in bullet.lower() for kw in ['technologies:', 'tech:', 'built with', 'stack:']):
                        current_entry["tech"] = bullet.split(':', 1)[-1].strip()
                    else:
                        current_entry["bullets"].append(bullet)
        
        elif current_section == 'education':
            if not stripped.startswith('-') and not stripped.startswith('•'):
                current_entry = {
                    "degree": stripped.replace('*', '').strip(),
                    "institution": "",
                    "dates": "",
                    "details": ""
                }
                resume["education"].append(current_entry)
            elif current_entry:
                bullet = stripped.lstrip('-•* ').strip()
                if re.search(r'\d{4}', bullet):
                    current_entry["dates"] = bullet
                elif not current_entry["institution"]:
                    current_entry["institution"] = bullet
                else:
                    current_entry["details"] = bullet
        
        elif current_section == 'certifications':
            cert = stripped.lstrip('-•* ').strip()
            if cert:
                resume["certifications"].append(cert)
        
        elif current_section == 'contact':
            if '@' in stripped:
                emails = re.findall(r'[\w.+-]+@[\w-]+\.[\w.]+', stripped)
                resume["contact"]["email"] = emails[0] if emails else stripped
            elif 'linkedin' in stripped.lower():
                resume["contact"]["linkedin"] = stripped.split()[-1]
            elif 'github' in stripped.lower():
                resume["contact"]["github"] = stripped.split()[-1]
            elif re.search(r'\+?\d[\d\s()-]{7,}', stripped):
                phones = re.findall(r'\+?\d[\d\s()-]{7,}', stripped)
                resume["contact"]["phone"] = phones[0] if phones else ""
            else:
                if not resume["contact"]["location"]:
                    resume["contact"]["location"] = stripped
    
    return resume


def parse_ai_response(response_text: str) -> Dict[str, Any]:
    """
    Parse AI response into structured resume data.
    Tries JSON first, falls back to free-text parsing.
    """
    if not response_text or not response_text.strip():
        print("[Parser] Empty response received!")
        return parse_freetext_response("")

    print(f"[Parser] Parsing response ({len(response_text)} chars)...")
    print(f"[Parser] First 200 chars: {response_text[:200]}")

    # Try JSON parsing
    result = extract_json_from_text(response_text)
    if result and isinstance(result, dict):
        required_keys = ['name', 'summary', 'skills', 'experience']
        if all(key in result for key in required_keys):
            defaults = {
                "name": "",
                "contact": {"email": "", "phone": "", "linkedin": "", "github": "", "location": ""},
                "summary": "",
                "skills": [],
                "experience": [],
                "projects": [],
                "education": [],
                "certifications": []
            }
            for key, default_val in defaults.items():
                if key not in result:
                    result[key] = default_val
            print(f"[Parser] JSON parsed successfully! Name: {result['name']}, "
                  f"Skills: {len(result.get('skills', []))}, "
                  f"Experience: {len(result.get('experience', []))}")
            return result
        else:
            missing = [k for k in required_keys if k not in result]
            print(f"[Parser] JSON found but missing keys: {missing}")
    
    # Fallback
    print("[Parser] JSON parsing failed, using free-text parser...")
    return parse_freetext_response(response_text)


def validate_resume_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and clean up the parsed resume data."""
    issues = []
    
    if not data.get("name"):
        issues.append("Name is missing")
    if not data.get("summary"):
        issues.append("Summary is missing")
    if not data.get("skills") or len(data["skills"]) == 0:
        issues.append("Skills section is empty")
    if not data.get("experience") or len(data["experience"]) == 0:
        issues.append("Experience section is empty")
    
    if data.get("skills"):
        data["skills"] = list(dict.fromkeys([s.strip() for s in data["skills"] if s.strip()]))
    
    for exp in data.get("experience", []):
        exp.setdefault("title", "")
        exp.setdefault("company", "")
        exp.setdefault("dates", "")
        exp.setdefault("bullets", [])
    
    for proj in data.get("projects", []):
        proj.setdefault("name", "")
        proj.setdefault("tech", "")
        proj.setdefault("bullets", [])
    
    if issues:
        print(f"[Parser] Validation issues: {', '.join(issues)}")
    
    data["_validation_issues"] = issues
    return data
