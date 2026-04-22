"""
ResumeForge — AI-Powered Resume Builder
Flask application entry point.

Uses browser automation to leverage your existing AI subscriptions
(ChatGPT, Gemini, Claude, Perplexity) for resume optimization.
"""

import os
import json
import threading
import queue
import time
from datetime import datetime
from flask import (
    Flask, render_template, request, jsonify, send_file,
    send_from_directory, Response, stream_with_context
)
from dotenv import load_dotenv
from werkzeug.utils import secure_filename

# Load environment variables
load_dotenv()

# Import services
from services.pdf_parser import extract_text_from_pdf, extract_text_from_bytes
from services.browser_ai import run_ai_prompt, launch_chrome_debug, PLATFORMS, get_available_profiles
from services.response_parser import parse_ai_response, validate_resume_data
from services.pdf_generator import generate_resume_pdf, get_generation_history

# ─────────────────────────────────────────────
# App Configuration
# ─────────────────────────────────────────────

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "resumeforge-secret-2024")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
GENERATED_DIR = os.path.join(BASE_DIR, "generated")
DEFAULT_RESUME = os.path.join(BASE_DIR, "Prashant resume.pdf")

# Ensure directories exist
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(GENERATED_DIR, exist_ok=True)

# Chrome config from .env
CHROME_USER_DATA_DIR = os.getenv("CHROME_USER_DATA_DIR", "")
CHROME_PROFILE = os.getenv("CHROME_PROFILE", "Default")
CHROME_DEBUG_PORT = int(os.getenv("CHROME_DEBUG_PORT", "9222"))
AI_TIMEOUT = int(os.getenv("AI_RESPONSE_TIMEOUT", "120"))

# Global progress tracking (simple in-memory for single user)
progress_queues = {}


# ─────────────────────────────────────────────
# Routes — Pages
# ─────────────────────────────────────────────

@app.route("/")
def index():
    """Serve the main dashboard."""
    return render_template("index.html")


# ─────────────────────────────────────────────
# Routes — API
# ─────────────────────────────────────────────

@app.route("/api/load-default-resume", methods=["GET"])
def load_default_resume():
    """Load and parse the default saved resume (Prashant resume.pdf)."""
    if not os.path.exists(DEFAULT_RESUME):
        return jsonify({"error": "Default resume not found. Please upload a resume."}), 404
    
    try:
        text = extract_text_from_pdf(DEFAULT_RESUME)
        return jsonify({
            "success": True,
            "text": text,
            "filename": os.path.basename(DEFAULT_RESUME),
            "char_count": len(text),
        })
    except Exception as e:
        return jsonify({"error": f"Failed to parse PDF: {str(e)}"}), 500


@app.route("/api/upload-resume", methods=["POST"])
def upload_resume():
    """Upload a new resume PDF and extract its text."""
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "No file selected"}), 400
    
    if not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Only PDF files are supported"}), 400
    
    try:
        # Save the uploaded file
        filename = secure_filename(file.filename)
        filepath = os.path.join(UPLOAD_DIR, filename)
        file.save(filepath)
        
        # Extract text
        text = extract_text_from_pdf(filepath)
        
        return jsonify({
            "success": True,
            "text": text,
            "filename": filename,
            "char_count": len(text),
        })
    except Exception as e:
        return jsonify({"error": f"Failed to process PDF: {str(e)}"}), 500


@app.route("/api/platforms", methods=["GET"])
def get_platforms():
    """Return available AI platforms."""
    platforms = []
    for key, config in PLATFORMS.items():
        platforms.append({
            "key": key,
            "name": config["name"],
            "url": config["new_chat_url"],
        })
    return jsonify({"platforms": platforms})


@app.route("/api/profiles", methods=["GET"])
def list_profiles():
    """Return available Chrome profiles so user can pick which one has AI logins."""
    profiles = get_available_profiles(CHROME_USER_DATA_DIR)
    return jsonify({
        "profiles": profiles,
        "current": CHROME_PROFILE,
    })


@app.route("/api/generate", methods=["POST"])
def generate_resume():
    """
    Main endpoint: Send resume + JD to AI platform → get optimized resume → generate PDF.
    Returns the result after completion.
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
    
    resume_text = data.get("resume_text", "").strip()
    job_description = data.get("job_description", "").strip()
    platform = data.get("platform", "chatgpt").lower()
    job_title = data.get("job_title", "Resume")
    chrome_profile = data.get("chrome_profile", CHROME_PROFILE)
    
    # Validation
    if not resume_text:
        return jsonify({"error": "Resume text is required. Upload or load a resume first."}), 400
    if not job_description:
        return jsonify({"error": "Job description is required."}), 400
    if platform not in PLATFORMS:
        return jsonify({"error": f"Unknown platform: {platform}. Choose from: {list(PLATFORMS.keys())}"}), 400
    
    # Generate a session ID for progress tracking
    session_id = f"{platform}_{int(time.time())}"
    progress_queue = queue.Queue()
    progress_queues[session_id] = progress_queue
    
    def progress_callback(message):
        progress_queue.put(message)
    
    try:
        progress_callback("Starting resume generation...")
        progress_callback(f"Using {PLATFORMS[platform]['name']}...")
        
        # Step 1: Send to AI via browser automation
        progress_callback("Launching Chrome with your profile...")
        
        raw_response = run_ai_prompt(
            platform_key=platform,
            resume_text=resume_text,
            job_description=job_description,
            user_data_dir=CHROME_USER_DATA_DIR,
            profile=chrome_profile,
            debug_port=CHROME_DEBUG_PORT,
            timeout=AI_TIMEOUT,
            progress_callback=progress_callback,
        )
        
        progress_callback("AI response received! Parsing content...")
        
        # Step 2: Parse the AI response
        resume_data = parse_ai_response(raw_response)
        resume_data = validate_resume_data(resume_data)
        
        validation_issues = resume_data.pop("_validation_issues", [])
        if validation_issues:
            progress_callback(f"Warnings: {', '.join(validation_issues)}")
        
        progress_callback("Generating PDF resume...")
        
        # Step 3: Generate PDF
        result = generate_resume_pdf(
            resume_data=resume_data,
            job_title=job_title,
            platform_used=platform,
        )
        
        progress_callback("Done! Your resume is ready for download.")
        
        # Clean up progress queue
        if session_id in progress_queues:
            del progress_queues[session_id]
        
        return jsonify({
            "success": True,
            "filename": result["filename"],
            "preview_url": result["preview_url"],
            "download_url": result["download_url"],
            "resume_data": resume_data,
            "raw_response_length": len(raw_response),
            "validation_issues": validation_issues,
            "session_id": session_id,
        })
        
    except Exception as e:
        if session_id in progress_queues:
            del progress_queues[session_id]
        return jsonify({"error": str(e)}), 500


@app.route("/api/generate-stream", methods=["POST"])
def generate_resume_stream():
    """
    SSE endpoint for real-time progress during generation.
    Client connects to this for progress updates while /api/generate runs.
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
    
    resume_text = data.get("resume_text", "").strip()
    job_description = data.get("job_description", "").strip()
    platform = data.get("platform", "chatgpt").lower()
    job_title = data.get("job_title", "Resume")
    chrome_profile = data.get("chrome_profile", CHROME_PROFILE)
    
    if not resume_text or not job_description:
        return jsonify({"error": "Resume text and job description are required."}), 400
    if platform not in PLATFORMS:
        return jsonify({"error": f"Unknown platform: {platform}"}), 400
    
    def generate():
        messages = queue.Queue()
        
        def progress_callback(msg):
            messages.put({"type": "progress", "message": msg})
        
        # Run AI generation in a background thread
        result_holder = {"result": None, "error": None}
        
        def run_generation():
            try:
                raw_response = run_ai_prompt(
                    platform_key=platform,
                    resume_text=resume_text,
                    job_description=job_description,
                    user_data_dir=CHROME_USER_DATA_DIR,
                    profile=chrome_profile,
                    debug_port=CHROME_DEBUG_PORT,
                    timeout=AI_TIMEOUT,
                    progress_callback=progress_callback,
                )
                
                progress_callback("Parsing AI response...")
                
                # Save raw response for debugging
                debug_path = os.path.join(BASE_DIR, "last_raw_response.txt")
                with open(debug_path, "w", encoding="utf-8") as f:
                    f.write(raw_response)
                print(f"[DEBUG] Saved raw response to {debug_path} ({len(raw_response)} chars)")
                print(f"[DEBUG] First 500 chars: {raw_response[:500]}")
                
                resume_data = parse_ai_response(raw_response)
                resume_data = validate_resume_data(resume_data)
                resume_data.pop("_validation_issues", [])
                
                progress_callback("Generating PDF...")
                pdf_result = generate_resume_pdf(
                    resume_data=resume_data,
                    job_title=job_title,
                    platform_used=platform,
                )
                
                result_holder["result"] = {
                    "success": True,
                    "filename": pdf_result["filename"],
                    "preview_url": pdf_result["preview_url"],
                    "download_url": pdf_result["download_url"],
                    "resume_data": resume_data,
                }
                messages.put({"type": "complete", "data": result_holder["result"]})
                
            except Exception as e:
                result_holder["error"] = str(e)
                messages.put({"type": "error", "message": str(e)})
        
        thread = threading.Thread(target=run_generation, daemon=True)
        thread.start()
        
        while True:
            try:
                msg = messages.get(timeout=1)
                yield f"data: {json.dumps(msg)}\n\n"
                if msg["type"] in ("complete", "error"):
                    break
            except queue.Empty:
                # Send heartbeat to keep connection alive
                yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
    
    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )


@app.route("/api/download/<filename>")
def download_file(filename):
    """Download a generated resume PDF."""
    filepath = os.path.join(GENERATED_DIR, secure_filename(filename))
    if not os.path.exists(filepath):
        return jsonify({"error": "File not found"}), 404
    return send_file(filepath, as_attachment=True, download_name=filename)


@app.route("/api/preview/<filename>")
def preview_file(filename):
    """Preview a generated resume PDF in the browser."""
    filepath = os.path.join(GENERATED_DIR, secure_filename(filename))
    if not os.path.exists(filepath):
        return jsonify({"error": "File not found"}), 404
    return send_file(filepath, mimetype="application/pdf")


@app.route("/api/history", methods=["GET"])
def get_history():
    """Get list of previously generated resumes."""
    history = get_generation_history()
    return jsonify({"history": history})


@app.route("/api/delete-history/<filename>", methods=["DELETE"])
def delete_history(filename):
    """Delete a generated resume and its history entry."""
    safe_name = secure_filename(filename)
    
    # Delete the PDF
    pdf_path = os.path.join(GENERATED_DIR, safe_name)
    if os.path.exists(pdf_path):
        os.remove(pdf_path)
    
    # Delete the history JSON (find by filename match)
    history_dir = os.path.join(BASE_DIR, "history")
    if os.path.exists(history_dir):
        for hfile in os.listdir(history_dir):
            if hfile.endswith(".json"):
                hpath = os.path.join(history_dir, hfile)
                try:
                    with open(hpath, "r") as f:
                        data = json.load(f)
                    if data.get("filename") == safe_name:
                        os.remove(hpath)
                        break
                except Exception:
                    pass
    
    return jsonify({"success": True})


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("FLASK_PORT", 5000))
    print(f"""
    ╔══════════════════════════════════════════════╗
    ║     🎯 ResumeForge — AI Resume Builder       ║
    ║                                              ║
    ║     http://localhost:{port}                    ║
    ║                                              ║
    ║     Chrome Profile: {CHROME_PROFILE:<24s} ║
    ║     Debug Port: {CHROME_DEBUG_PORT:<28d} ║
    ╚══════════════════════════════════════════════╝
    """)
    app.run(debug=True, port=port, threaded=True)
