"""Test parser with the ACTUAL ChatGPT response format (literal newlines in strings)."""
from services.response_parser import parse_ai_response

# This is EXACTLY what ChatGPT returns via inner_text() scraping:
# Note: email value has a literal newline INSIDE the quoted string
test_response = """{
"name": "Prashant Pal",
"contact": {
"email": "palprashant8980@gmail.com
",
"phone": "+91-8839436332",
"linkedin": "linkedin.com/in/prashantpal0405",
"github": "github.com/prashantpal8980",
"location": "Madhya Pradesh, India"
},
"summary": "Junior Information Security professional with a B.Tech in CSE and hands-on experience in vulnerability assessment, SIEM operations, and network security.",
"skills": ["Python", "Penetration Testing", "SIEM", "Vulnerability Assessment", "Network Security", "Wireshark", "Nmap"],
"experience": [{"title": "Security Intern", "company": "TestCorp", "dates": "2024 - Present", "bullets": ["Conducted vulnerability scans", "Monitored SIEM alerts"]}],
"projects": [{"name": "Portfolio Website", "tech": "Django, Python", "bullets": ["Built a full-stack portfolio"]}],
"education": [{"degree": "B.Tech CSE", "institution": "Test University", "dates": "2024", "details": "CGPA: 7.5"}],
"certifications": ["CEH", "CompTIA Security+"]
}"""

result = parse_ai_response(test_response)
print(f"Name: {result.get('name', 'MISSING')}")
print(f"Email: {result.get('contact', {}).get('email', 'MISSING')}")
print(f"Skills: {len(result.get('skills', []))}")
print(f"Experience: {len(result.get('experience', []))}")
print(f"Summary: {result.get('summary', 'MISSING')[:60]}")

if result.get('name') == "Prashant Pal" and len(result.get('skills', [])) > 0:
    print("\n✅ PARSER TEST PASSED! Resume will be generated correctly now.")
else:
    print("\n❌ PARSER TEST FAILED!")
    print(f"Full result keys: {list(result.keys())}")
