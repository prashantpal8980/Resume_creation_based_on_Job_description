"""
Browser AI Service
Automates interaction with AI platforms (ChatGPT, Gemini, Claude, Perplexity)
using Playwright + Chrome DevTools Protocol.

Uses a DEDICATED debug Chrome profile that copies login sessions from the
user's real Chrome profile. This avoids the "non-default data directory"
error that Chrome throws when trying to debug with the main profile.
"""

import subprocess
import shutil
import time
import os
import re
import json
import random
import asyncio
import urllib.request
from typing import Optional, Callable
from playwright.async_api import async_playwright, Page, Browser


# ─────────────────────────────────────────────
# Platform Configurations
# ─────────────────────────────────────────────

PLATFORMS = {
    "chatgpt": {
        "name": "ChatGPT",
        "new_chat_url": "https://chatgpt.com/",
        "input_selector": "#prompt-textarea",
        "send_button_selector": 'button[data-testid="send-button"]',
        "response_selector": '[data-message-author-role="assistant"]',
        "stop_selector": 'button[aria-label="Stop generating"]',
    },
    "gemini": {
        "name": "Gemini",
        "new_chat_url": "https://gemini.google.com/app",
        "input_selector": '.ql-editor, div[contenteditable="true"][role="textbox"], rich-textarea .textarea',
        "send_button_selector": 'button[aria-label="Send message"], button.send-button, button[mat-icon-button][aria-label*="Send"]',
        "response_selector": '.response-container .markdown, .model-response-text, message-content',
        "stop_selector": 'button[aria-label="Stop generating"], button[aria-label="Stop"]',
    },
    "claude": {
        "name": "Claude",
        "new_chat_url": "https://claude.ai/new",
        "input_selector": 'div[contenteditable="true"].ProseMirror, div[contenteditable="true"][aria-label*="Message"], fieldset .ProseMirror',
        "send_button_selector": 'button[aria-label="Send Message"], button[aria-label="Send message"]',
        "response_selector": '.font-claude-message, [data-testid="chat-message-text"]',
        "stop_selector": 'button[aria-label="Stop Response"], button[aria-label="Stop generating"]',
    },
    "perplexity": {
        "name": "Perplexity",
        "new_chat_url": "https://www.perplexity.ai/",
        "input_selector": 'textarea[placeholder*="Ask"], textarea[placeholder*="ask"], textarea',
        "send_button_selector": 'button[aria-label="Submit"], button[aria-label="Send"], button.bg-super',
        "response_selector": '.prose, .markdown-content, [class*="answer"]',
        "stop_selector": 'button[aria-label="Stop"]',
    },
}


# ─────────────────────────────────────────────
# Chrome Management
# ─────────────────────────────────────────────

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEBUG_PROFILE_DIR = os.path.join(BASE_DIR, ".chrome_debug_profile")


def get_chrome_path() -> str:
    """Find Chrome installation on Windows."""
    possible_paths = [
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
    ]
    for path in possible_paths:
        if os.path.exists(path):
            return path
    raise FileNotFoundError("Chrome not found. Please install Google Chrome.")


def get_available_profiles(user_data_dir: str) -> list:
    """List available Chrome profiles with their display names."""
    profiles = []
    if not os.path.exists(user_data_dir):
        return profiles

    for entry in os.listdir(user_data_dir):
        full_path = os.path.join(user_data_dir, entry)
        if not os.path.isdir(full_path):
            continue
        if entry == "Default" or entry.startswith("Profile "):
            # Try to read the profile name from Preferences
            display_name = entry
            prefs_file = os.path.join(full_path, "Preferences")
            if os.path.exists(prefs_file):
                try:
                    with open(prefs_file, "r", encoding="utf-8") as f:
                        prefs = json.load(f)
                    name = prefs.get("profile", {}).get("name", "")
                    if name:
                        display_name = f"{name} ({entry})"
                except Exception:
                    pass
            profiles.append({"dir_name": entry, "display_name": display_name})

    return profiles


def copy_profile_sessions(user_data_dir: str, profile: str):
    """
    Copy login/cookie/session files from the user's real Chrome profile
    to our dedicated debug profile directory.
    
    This lets us reuse their AI platform logins without touching the
    original Chrome profile (which can't be used for debugging directly).
    """
    source_profile = os.path.join(user_data_dir, profile)
    dest_profile = os.path.join(DEBUG_PROFILE_DIR, "Default")

    if not os.path.exists(source_profile):
        raise FileNotFoundError(f"Chrome profile not found: {source_profile}")

    # Create debug profile directory
    os.makedirs(dest_profile, exist_ok=True)
    os.makedirs(os.path.join(dest_profile, "Network"), exist_ok=True)

    # Files to copy for login session persistence
    session_files = [
        # Cookies (stores login sessions for all websites)
        (os.path.join(source_profile, "Network", "Cookies"),
         os.path.join(dest_profile, "Network", "Cookies")),
        (os.path.join(source_profile, "Network", "Cookies-journal"),
         os.path.join(dest_profile, "Network", "Cookies-journal")),
        # Login credentials
        (os.path.join(source_profile, "Login Data"),
         os.path.join(dest_profile, "Login Data")),
        (os.path.join(source_profile, "Login Data-journal"),
         os.path.join(dest_profile, "Login Data-journal")),
        # Preferences (for profile settings)
        (os.path.join(source_profile, "Preferences"),
         os.path.join(dest_profile, "Preferences")),
        (os.path.join(source_profile, "Secure Preferences"),
         os.path.join(dest_profile, "Secure Preferences")),
    ]

    # Also copy Local State from the parent User Data dir
    local_state_src = os.path.join(user_data_dir, "Local State")
    local_state_dst = os.path.join(DEBUG_PROFILE_DIR, "Local State")
    if os.path.exists(local_state_src):
        try:
            shutil.copy2(local_state_src, local_state_dst)
        except Exception as e:
            print(f"[Chrome] Warning: Could not copy Local State: {e}")

    copied = 0
    for src, dst in session_files:
        if os.path.exists(src):
            try:
                shutil.copy2(src, dst)
                copied += 1
            except Exception as e:
                print(f"[Chrome] Warning: Could not copy {os.path.basename(src)}: {e}")

    print(f"[Chrome] Copied {copied} session files from '{profile}' to debug profile.")
    return copied > 0


def is_debug_port_ready(port: int) -> bool:
    """Check if Chrome debug port is responding via HTTP."""
    try:
        url = f"http://localhost:{port}/json/version"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode())
                print(f"[Chrome] Debug endpoint active: {data.get('Browser', 'Unknown')}")
                return True
    except Exception:
        pass
    return False


def kill_chrome_processes():
    """Kill all running Chrome processes to free the profile lock."""
    try:
        result = subprocess.run(
            ["taskkill", "/F", "/IM", "chrome.exe", "/T"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            print("[Chrome] Killed existing Chrome processes.")
            time.sleep(2)
        else:
            print("[Chrome] No Chrome processes to kill.")
    except Exception as e:
        print(f"[Chrome] Warning: Could not kill Chrome: {e}")


def launch_chrome_debug(user_data_dir: str, profile: str, debug_port: int) -> Optional[subprocess.Popen]:
    """
    Launch Chrome with remote debugging using a DEDICATED debug profile.
    
    Chrome refuses to enable remote debugging on its default User Data
    directory. So we create a separate debug profile directory and copy
    the user's login sessions (cookies) into it.
    """
    # Step 1: Check if debug port is already active
    if is_debug_port_ready(debug_port):
        print(f"[Chrome] Debug port {debug_port} already active — reusing.")
        return None

    # Step 2: Kill any existing Chrome (it locks the profile)
    print("[Chrome] Closing any existing Chrome instances...")
    kill_chrome_processes()

    # Step 3: Copy login sessions from user's real profile
    print(f"[Chrome] Copying sessions from profile '{profile}'...")
    try:
        copy_profile_sessions(user_data_dir, profile)
    except Exception as e:
        print(f"[Chrome] Warning: Session copy failed: {e}")
        print("[Chrome] You may need to log in to AI platforms manually.")

    # Step 4: Launch Chrome with the debug profile
    chrome_path = get_chrome_path()
    cmd = [
        chrome_path,
        f"--remote-debugging-port={debug_port}",
        f"--user-data-dir={DEBUG_PROFILE_DIR}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
    ]

    print(f"[Chrome] Launching with debug port {debug_port}...")
    print(f"[Chrome] Debug profile: {DEBUG_PROFILE_DIR}")

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0,
    )

    # Step 5: Wait for debug endpoint to respond
    print(f"[Chrome] Waiting for debug endpoint...")
    for attempt in range(60):
        time.sleep(1)

        # Check process is still alive
        if process.poll() is not None:
            stderr = ""
            try:
                stderr = process.stderr.read().decode(errors='replace')
            except Exception:
                pass
            raise RuntimeError(
                f"Chrome exited with code {process.returncode}. "
                f"Stderr: {stderr[:500]}"
            )

        if is_debug_port_ready(debug_port):
            print(f"[Chrome] Ready! (took {attempt + 1}s)")
            return process

        if attempt % 10 == 9:
            print(f"[Chrome] Still waiting... ({attempt + 1}s)")

    stderr = ""
    try:
        process.terminate()
        stderr = process.stderr.read().decode(errors='replace')
    except Exception:
        pass

    raise TimeoutError(
        f"Chrome debug port did not respond within 60s. "
        f"Stderr: {stderr[:300] if stderr else 'none'}"
    )


# ─────────────────────────────────────────────
# Prompt Builder
# ─────────────────────────────────────────────

def build_prompt(resume_text: str, job_description: str) -> str:
    """Build the ATS optimization prompt to send to the AI."""
    return f"""You are an expert ATS resume writer. I will provide my current resume and a job description.

Your task:
- Rewrite my resume to align with the job description
- Keep all information truthful — do not fabricate any experience or skills
- Add relevant ATS keywords naturally from the job description
- Improve grammar, impact, and readability
- Make it concise and professional — must fit on one page
- Use strong action verbs and clean bullet points
- Focus on skills/projects most relevant to the role
- Write a compelling professional summary
- Optimize section ordering for maximum impact

CRITICAL: Return your response as a JSON object with this EXACT structure, and NOTHING else (no markdown fences, no explanation, just raw JSON):

{{
  "name": "Full Name",
  "contact": {{
    "email": "email@example.com",
    "phone": "+1-XXX-XXX-XXXX",
    "linkedin": "linkedin.com/in/username",
    "github": "github.com/username",
    "location": "City, State"
  }},
  "summary": "2-3 sentence professional summary tailored to the job",
  "skills": ["Skill 1", "Skill 2", "Skill 3"],
  "experience": [
    {{
      "title": "Job Title",
      "company": "Company Name",
      "dates": "Start Date - End Date",
      "bullets": [
        "Achievement with metrics and action verbs...",
        "Another achievement..."
      ]
    }}
  ],
  "projects": [
    {{
      "name": "Project Name",
      "tech": "Technologies used",
      "bullets": [
        "What you built and impact...",
        "Technical details..."
      ]
    }}
  ],
  "education": [
    {{
      "degree": "Degree Name",
      "institution": "University Name",
      "dates": "Graduation Year",
      "details": "GPA, honors, relevant coursework"
    }}
  ],
  "certifications": ["Certification 1", "Certification 2"]
}}

=== MY CURRENT RESUME ===
{resume_text}

=== TARGET JOB DESCRIPTION ===
{job_description}"""


# ─────────────────────────────────────────────
# Browser Interaction
# ─────────────────────────────────────────────

async def _human_delay(min_s: float = 0.3, max_s: float = 1.2):
    """Add a random human-like delay."""
    await asyncio.sleep(random.uniform(min_s, max_s))


async def _paste_text_to_element(page: Page, selector: str, text: str):
    """
    Paste text into an element. Works for textarea and contenteditable divs.
    Uses multiple strategies with fallbacks.
    """
    # Focus the element
    try:
        await page.click(selector, timeout=5000)
        await _human_delay(0.3, 0.6)
    except Exception:
        pass

    element = await page.query_selector(selector)
    if not element:
        raise Exception(f"Could not find input element: {selector}")

    tag = await element.evaluate("el => el.tagName.toLowerCase()")
    is_ce = await element.evaluate("el => el.getAttribute('contenteditable') === 'true'")

    # Strategy 1: fill() for standard textarea/input
    if tag in ('textarea', 'input') and not is_ce:
        try:
            await element.fill(text)
            return
        except Exception:
            pass

    # Strategy 2: Set innerText for contenteditable
    if is_ce:
        try:
            await element.evaluate("""(el, text) => {
                el.focus();
                el.innerText = text;
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
            }""", text)
            return
        except Exception:
            pass

    # Strategy 3: Clipboard paste
    try:
        await page.evaluate("(text) => { navigator.clipboard.writeText(text); }", text)
        await element.click()
        await page.keyboard.press("Control+A")
        await page.keyboard.press("Control+V")
    except Exception:
        # Strategy 4: Direct type (slow but reliable)
        await element.click()
        await element.type(text, delay=1)


async def _wait_for_response(page: Page, platform_key: str, timeout: int = 120) -> str:
    """
    Wait for the AI to finish generating and extract the response text.
    Detects completion via stop-button disappearance + content stabilization.
    """
    config = PLATFORMS[platform_key]
    response_selector = config["response_selector"]
    stop_selector = config.get("stop_selector", "")

    print(f"[{config['name']}] Waiting for response (timeout: {timeout}s)...")

    start_time = time.time()

    # Phase 1: Wait for response element to appear
    while time.time() - start_time < timeout:
        try:
            elements = await page.query_selector_all(response_selector)
            if elements and len(elements) > 0:
                break
        except Exception:
            pass
        await asyncio.sleep(1)
    else:
        await asyncio.sleep(10)  # Extra wait if no element found

    # Phase 2: Wait for content to stabilize
    print(f"[{config['name']}] Response started, waiting for completion...")
    stable_count = 0
    last_text = ""

    while time.time() - start_time < timeout:
        # Check if still generating (stop button visible)
        if stop_selector:
            try:
                stop_btn = await page.query_selector(stop_selector)
                if stop_btn and await stop_btn.is_visible():
                    stable_count = 0
                    await asyncio.sleep(2)
                    continue
            except Exception:
                pass

        # Get current text
        try:
            elements = await page.query_selector_all(response_selector)
            if elements:
                last_el = elements[-1]
                current_text = await last_el.inner_text()

                if current_text and current_text == last_text and len(current_text) > 50:
                    stable_count += 1
                    if stable_count >= 3:
                        print(f"[{config['name']}] Response stabilized ({len(current_text)} chars)")
                        return current_text
                else:
                    stable_count = 0
                    last_text = current_text
        except Exception:
            pass

        await asyncio.sleep(2)

    if last_text:
        print(f"[{config['name']}] Timeout, returning partial ({len(last_text)} chars)")
        return last_text

    raise TimeoutError(f"No response from {config['name']} within {timeout}s")


async def send_prompt_to_ai(
    platform_key: str,
    prompt: str,
    debug_port: int = 9222,
    timeout: int = 120,
    progress_callback: Optional[Callable] = None,
) -> str:
    """
    Send a prompt to the AI platform and return the response.
    Opens a NEW chat tab each time. Includes retry logic for CDP connection.
    """
    if platform_key not in PLATFORMS:
        raise ValueError(f"Unknown platform: {platform_key}")

    config = PLATFORMS[platform_key]

    def progress(msg):
        print(f"[{config['name']}] {msg}")
        if progress_callback:
            progress_callback(msg)

    progress("Connecting to Chrome...")

    # Retry CDP connection up to 3 times
    browser = None
    last_error = None
    async with async_playwright() as p:
        for attempt in range(3):
            try:
                browser = await p.chromium.connect_over_cdp(
                    f"http://localhost:{debug_port}",
                    timeout=15000,
                )
                progress("Connected to Chrome!")
                break
            except Exception as e:
                last_error = e
                progress(f"Connection attempt {attempt + 1}/3 failed: {str(e)[:100]}")
                if attempt < 2:
                    await asyncio.sleep(3)

        if browser is None:
            raise ConnectionError(
                f"Cannot connect to Chrome after 3 attempts. "
                f"Last error: {last_error}"
            )

        progress("Opening new chat...")

        context = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = await context.new_page()

        try:
            await page.goto(config["new_chat_url"], wait_until="domcontentloaded", timeout=30000)
            await _human_delay(3.0, 5.0)

            progress("Page loaded. Finding input field...")

            # Try each selector
            selectors = [s.strip() for s in config["input_selector"].split(",")]
            input_found = False

            for selector in selectors:
                try:
                    await page.wait_for_selector(selector, timeout=8000)
                    progress("Found input field. Pasting prompt...")
                    await _paste_text_to_element(page, selector, prompt)
                    input_found = True
                    break
                except Exception:
                    continue

            if not input_found:
                # Take a screenshot for debugging
                try:
                    screenshot_path = os.path.join(BASE_DIR, "debug_screenshot.png")
                    await page.screenshot(path=screenshot_path)
                    progress(f"Saved debug screenshot to {screenshot_path}")
                except Exception:
                    pass
                raise Exception(
                    f"Could not find input on {config['name']}. "
                    f"You may need to log in first in the debug Chrome window."
                )

            await _human_delay(1.0, 2.0)

            # Click send
            progress("Sending prompt...")
            send_selectors = [s.strip() for s in config["send_button_selector"].split(",")]
            sent = False

            for selector in send_selectors:
                try:
                    btn = await page.query_selector(selector)
                    if btn:
                        await btn.click()
                        sent = True
                        break
                except Exception:
                    continue

            if not sent:
                progress("Send button not found, pressing Enter...")
                await page.keyboard.press("Enter")

            await _human_delay(1.0, 2.0)

            progress("Waiting for AI response...")
            response_text = await _wait_for_response(page, platform_key, timeout)

            progress(f"Response received! ({len(response_text)} characters)")

            # Log first 300 chars for debugging
            print(f"[{config['name']}] Response preview: {response_text[:300]}")

            await page.close()
            return response_text

        except Exception as e:
            progress(f"Error: {str(e)}")
            raise


# ─────────────────────────────────────────────
# Main Entry Point
# ─────────────────────────────────────────────

# Track if Chrome was already launched this session
_chrome_process = None


def run_ai_prompt(
    platform_key: str,
    resume_text: str,
    job_description: str,
    user_data_dir: str,
    profile: str,
    debug_port: int = 9222,
    timeout: int = 120,
    progress_callback: Optional[Callable] = None,
) -> str:
    """
    High-level function: Launch Chrome → send prompt → return response.
    Main entry point called by app.py.
    
    Chrome is launched ONCE and reused across requests.
    """
    global _chrome_process

    def progress(msg):
        if progress_callback:
            progress_callback(msg)

    # Only launch Chrome if not already running
    if not is_debug_port_ready(debug_port):
        progress("Launching Chrome with your profile...")
        _chrome_process = launch_chrome_debug(user_data_dir, profile, debug_port)
    else:
        progress("Chrome already running — reusing connection...")

    prompt = build_prompt(resume_text, job_description)

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        response = loop.run_until_complete(
            send_prompt_to_ai(platform_key, prompt, debug_port, timeout, progress_callback)
        )
        loop.close()
        return response
    except Exception as e:
        raise RuntimeError(f"Failed to get response from {PLATFORMS[platform_key]['name']}: {e}")

