/**
 * ResumeForge — Frontend Application Logic
 * Handles UI interactions, API calls, drag-drop, theme toggle, and PDF preview.
 */

// ─── State ───
const state = {
    resumeText: '',
    resumeFilename: '',
    selectedPlatform: 'chatgpt',
    selectedProfile: 'Default',
    isGenerating: false,
    currentPreviewUrl: '',
};

// ─── DOM Elements ───
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const els = {
    themeToggle: $('#themeToggle'),
    uploadZone: $('#uploadZone'),
    fileInput: $('#fileInput'),
    loadDefaultBtn: $('#loadDefaultBtn'),
    clearResumeBtn: $('#clearResumeBtn'),
    resumeStatus: $('#resumeStatus'),
    resumePreviewText: $('#resumePreviewText'),
    previewFilename: $('#previewFilename'),
    previewChars: $('#previewChars'),
    previewContent: $('#previewContent'),
    jobDescription: $('#jobDescription'),
    jdCharCount: $('#jdCharCount'),
    jobTitleInput: $('#jobTitleInput'),
    clearJdBtn: $('#clearJdBtn'),
    modelGrid: $('#modelGrid'),
    generateBtn: $('#generateBtn'),
    progressSection: $('#progressSection'),
    progressBar: $('#progressBar'),
    progressMessage: $('#progressMessage'),
    previewEmpty: $('#previewEmpty'),
    previewFrameContainer: $('#previewFrameContainer'),
    previewFrame: $('#previewFrame'),
    previewActions: $('#previewActions'),
    downloadBtn: $('#downloadBtn'),
    copyTextBtn: $('#copyTextBtn'),
    historyList: $('#historyList'),
    refreshHistoryBtn: $('#refreshHistoryBtn'),
    toastContainer: $('#toastContainer'),
    chromeProfileSelect: $('#chromeProfileSelect'),
    profileStatus: $('#profileStatus'),
};

// ─── Theme Toggle ───
function initTheme() {
    const saved = localStorage.getItem('resumeforge-theme') || 'dark';
    document.documentElement.setAttribute('data-theme', saved);
}

els.themeToggle.addEventListener('click', () => {
    const current = document.documentElement.getAttribute('data-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('resumeforge-theme', next);
});

// ─── Toast Notifications ───
function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    els.toastContainer.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
}

// ─── Resume Upload (Drag & Drop) ───
els.uploadZone.addEventListener('click', () => els.fileInput.click());

els.uploadZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    els.uploadZone.classList.add('drag-over');
});

els.uploadZone.addEventListener('dragleave', () => {
    els.uploadZone.classList.remove('drag-over');
});

els.uploadZone.addEventListener('drop', (e) => {
    e.preventDefault();
    els.uploadZone.classList.remove('drag-over');
    const files = e.dataTransfer.files;
    if (files.length > 0) handleFileUpload(files[0]);
});

els.fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) handleFileUpload(e.target.files[0]);
});

async function handleFileUpload(file) {
    if (!file.name.toLowerCase().endsWith('.pdf')) {
        showToast('Please upload a PDF file.', 'error');
        return;
    }

    const formData = new FormData();
    formData.append('file', file);

    try {
        els.uploadZone.classList.add('has-file');
        els.resumeStatus.textContent = 'Uploading...';

        const res = await fetch('/api/upload-resume', { method: 'POST', body: formData });
        const data = await res.json();

        if (data.success) {
            setResumeData(data.text, data.filename, data.char_count);
            showToast(`Resume loaded: ${data.filename}`, 'success');
        } else {
            showToast(data.error || 'Upload failed', 'error');
            els.uploadZone.classList.remove('has-file');
        }
    } catch (err) {
        showToast('Upload failed: ' + err.message, 'error');
        els.uploadZone.classList.remove('has-file');
    }
}

// ─── Load Default Resume ───
els.loadDefaultBtn.addEventListener('click', async () => {
    try {
        els.resumeStatus.textContent = 'Loading...';
        const res = await fetch('/api/load-default-resume');
        const data = await res.json();

        if (data.success) {
            setResumeData(data.text, data.filename, data.char_count);
            els.uploadZone.classList.add('has-file');
            showToast(`Default resume loaded: ${data.filename}`, 'success');
        } else {
            showToast(data.error || 'Failed to load', 'error');
        }
    } catch (err) {
        showToast('Failed to load resume: ' + err.message, 'error');
    }
});

function setResumeData(text, filename, charCount) {
    state.resumeText = text;
    state.resumeFilename = filename;

    els.resumeStatus.textContent = `✓ ${filename}`;
    els.resumeStatus.classList.add('loaded');
    els.clearResumeBtn.disabled = false;

    els.previewFilename.textContent = filename;
    els.previewChars.textContent = `${charCount.toLocaleString()} chars`;
    els.previewContent.textContent = text.substring(0, 800) + (text.length > 800 ? '...' : '');
    els.resumePreviewText.hidden = false;

    updateGenerateBtn();
}

els.clearResumeBtn.addEventListener('click', () => {
    state.resumeText = '';
    state.resumeFilename = '';
    els.resumeStatus.textContent = 'No resume loaded';
    els.resumeStatus.classList.remove('loaded');
    els.clearResumeBtn.disabled = true;
    els.resumePreviewText.hidden = true;
    els.uploadZone.classList.remove('has-file');
    els.fileInput.value = '';
    updateGenerateBtn();
});

// ─── Job Description ───
els.jobDescription.addEventListener('input', () => {
    const len = els.jobDescription.value.length;
    els.jdCharCount.textContent = `${len.toLocaleString()} chars`;
    updateGenerateBtn();
});

els.clearJdBtn.addEventListener('click', () => {
    els.jobDescription.value = '';
    els.jdCharCount.textContent = '0 chars';
    els.jobTitleInput.value = '';
    updateGenerateBtn();
});

// ─── Model Selection ───
$$('.model-card').forEach((card) => {
    card.addEventListener('click', () => {
        $$('.model-card').forEach((c) => c.classList.remove('active'));
        card.classList.add('active');
        state.selectedPlatform = card.dataset.platform;
    });
});

// ─── Generate Button ───
function updateGenerateBtn() {
    const ready = state.resumeText.length > 50 && els.jobDescription.value.trim().length > 50;
    els.generateBtn.disabled = !ready || state.isGenerating;
}

// ─── Chrome Profile Loading ───
async function loadProfiles() {
    try {
        const res = await fetch('/api/profiles');
        const data = await res.json();
        const profiles = data.profiles || [];
        const current = data.current || 'Default';

        els.chromeProfileSelect.innerHTML = '';
        profiles.forEach(p => {
            const opt = document.createElement('option');
            opt.value = p.dir_name;
            opt.textContent = p.display_name;
            if (p.dir_name === current) opt.selected = true;
            els.chromeProfileSelect.appendChild(opt);
        });

        state.selectedProfile = current;
        els.profileStatus.textContent = `${profiles.length} profiles found`;
        els.profileStatus.classList.add('loaded');
    } catch (err) {
        console.error('Failed to load profiles:', err);
        els.profileStatus.textContent = 'Error loading';
    }
}

els.chromeProfileSelect.addEventListener('change', () => {
    state.selectedProfile = els.chromeProfileSelect.value;
    showToast(`Profile switched to: ${els.chromeProfileSelect.value}`, 'info');
});

els.generateBtn.addEventListener('click', startGeneration);

async function startGeneration() {
    if (state.isGenerating) return;
    state.isGenerating = true;

    const btnText = els.generateBtn.querySelector('.btn-text');
    const btnLoading = els.generateBtn.querySelector('.btn-loading');
    const btnIcon = els.generateBtn.querySelector('.btn-icon');

    btnText.hidden = true;
    btnIcon.hidden = true;
    btnLoading.hidden = false;
    els.generateBtn.disabled = true;

    // Show progress
    els.progressSection.hidden = false;
    els.progressBar.style.width = '0%';
    els.progressBar.classList.add('indeterminate');
    els.progressMessage.textContent = 'Starting...';

    const payload = {
        resume_text: state.resumeText,
        job_description: els.jobDescription.value.trim(),
        platform: state.selectedPlatform,
        job_title: els.jobTitleInput.value.trim() || 'Resume',
        chrome_profile: state.selectedProfile,
    };

    try {
        // Use SSE streaming endpoint
        const res = await fetch('/api/generate-stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.error || 'Generation failed');
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let progressStep = 0;
        const progressSteps = 8;

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const msg = JSON.parse(line.slice(6));

                        if (msg.type === 'progress') {
                            progressStep++;
                            const pct = Math.min(90, (progressStep / progressSteps) * 100);
                            els.progressBar.classList.remove('indeterminate');
                            els.progressBar.style.width = pct + '%';
                            els.progressMessage.textContent = msg.message;
                        } else if (msg.type === 'complete') {
                            els.progressBar.classList.remove('indeterminate');
                            els.progressBar.style.width = '100%';
                            els.progressMessage.textContent = 'Done! Resume ready.';
                            handleGenerationComplete(msg.data);
                        } else if (msg.type === 'error') {
                            throw new Error(msg.message);
                        }
                    } catch (parseErr) {
                        if (parseErr.message && !parseErr.message.includes('JSON')) {
                            throw parseErr;
                        }
                    }
                }
            }
        }
    } catch (err) {
        showToast('Generation failed: ' + err.message, 'error');
        els.progressMessage.textContent = 'Error: ' + err.message;
        els.progressBar.classList.remove('indeterminate');
        els.progressBar.style.width = '0%';
    } finally {
        state.isGenerating = false;
        btnText.hidden = false;
        btnIcon.hidden = false;
        btnLoading.hidden = true;
        updateGenerateBtn();

        setTimeout(() => {
            els.progressSection.hidden = true;
        }, 5000);
    }
}

function handleGenerationComplete(data) {
    showToast('Resume generated successfully! Downloading...', 'success');

    // Auto-download the PDF
    const a = document.createElement('a');
    a.href = data.download_url;
    a.download = data.filename || 'resume.pdf';
    document.body.appendChild(a);
    a.click();
    a.remove();

    // Store download URL for manual re-download
    els.downloadBtn.dataset.url = data.download_url;
    els.downloadBtn.dataset.filename = data.filename;
    els.previewActions.hidden = false;

    // Store resume data for copy
    if (data.resume_data) {
        els.copyTextBtn.dataset.resumeData = JSON.stringify(data.resume_data);
    }

    // Refresh history
    loadHistory();
}

// ─── Download & Copy ───
els.downloadBtn.addEventListener('click', () => {
    const url = els.downloadBtn.dataset.url;
    if (url) {
        const a = document.createElement('a');
        a.href = url;
        a.download = els.downloadBtn.dataset.filename || 'resume.pdf';
        document.body.appendChild(a);
        a.click();
        a.remove();
        showToast('Download started!', 'success');
    }
});

els.copyTextBtn.addEventListener('click', () => {
    const dataStr = els.copyTextBtn.dataset.resumeData;
    if (!dataStr) return;

    try {
        const data = JSON.parse(dataStr);
        let text = `${data.name}\n`;
        const c = data.contact || {};
        text += [c.email, c.phone, c.linkedin, c.github, c.location].filter(Boolean).join(' | ') + '\n\n';

        if (data.summary) text += `PROFESSIONAL SUMMARY\n${data.summary}\n\n`;

        if (data.skills?.length) text += `SKILLS\n${data.skills.join(', ')}\n\n`;

        if (data.experience?.length) {
            text += 'EXPERIENCE\n';
            data.experience.forEach((e) => {
                text += `${e.title} — ${e.company} (${e.dates})\n`;
                e.bullets?.forEach((b) => (text += `• ${b}\n`));
                text += '\n';
            });
        }

        if (data.projects?.length) {
            text += 'PROJECTS\n';
            data.projects.forEach((p) => {
                text += `${p.name}${p.tech ? ' | ' + p.tech : ''}\n`;
                p.bullets?.forEach((b) => (text += `• ${b}\n`));
                text += '\n';
            });
        }

        if (data.education?.length) {
            text += 'EDUCATION\n';
            data.education.forEach((e) => {
                text += `${e.degree} — ${e.institution} (${e.dates})\n`;
                if (e.details) text += `${e.details}\n`;
                text += '\n';
            });
        }

        if (data.certifications?.length) text += `CERTIFICATIONS\n${data.certifications.join(', ')}\n`;

        navigator.clipboard.writeText(text).then(() => showToast('Resume text copied!', 'success'));
    } catch (err) {
        showToast('Failed to copy', 'error');
    }
});

// ─── History ───
async function loadHistory() {
    try {
        const res = await fetch('/api/history');
        const data = await res.json();
        renderHistory(data.history || []);
    } catch (err) {
        console.error('Failed to load history:', err);
    }
}

function renderHistory(history) {
    if (!history.length) {
        els.historyList.innerHTML = '<p class="history-empty">No resumes generated yet.</p>';
        return;
    }

    els.historyList.innerHTML = history
        .map(
            (h) => `
        <div class="history-item">
            <div class="history-info">
                <span class="history-filename" onclick="previewHistoryItem('${h.filename}')">${h.filename}</span>
                <span class="history-meta">${h.platform || 'unknown'} · ${new Date(h.generated_at).toLocaleDateString()}</span>
            </div>
            <div class="history-actions">
                <button class="history-btn" onclick="downloadHistoryItem('${h.filename}')">⬇️</button>
                <button class="history-btn delete" onclick="deleteHistoryItem('${h.filename}')">✕</button>
            </div>
        </div>
    `
        )
        .join('');
}

window.previewHistoryItem = (filename) => {
    els.previewEmpty.hidden = true;
    els.previewFrameContainer.hidden = false;
    els.previewFrame.src = `/api/preview/${filename}`;
    els.previewActions.hidden = false;
    els.downloadBtn.dataset.url = `/api/download/${filename}`;
    els.downloadBtn.dataset.filename = filename;
};

window.downloadHistoryItem = (filename) => {
    const a = document.createElement('a');
    a.href = `/api/download/${filename}`;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
};

window.deleteHistoryItem = async (filename) => {
    if (!confirm(`Delete ${filename}?`)) return;
    try {
        await fetch(`/api/delete-history/${filename}`, { method: 'DELETE' });
        showToast('Deleted', 'info');
        loadHistory();
    } catch (err) {
        showToast('Delete failed', 'error');
    }
};

els.refreshHistoryBtn.addEventListener('click', loadHistory);

// ─── Init ───
initTheme();
loadHistory();
loadProfiles();
updateGenerateBtn();
