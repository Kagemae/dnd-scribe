/* ===================================================================
   D&D Scribe — Client-side JavaScript
   SSE progress tracking, speaker identification, tabs, and interactions.
   =================================================================== */

// ── Upload form: toggle between file upload and recording selection ──

function initUploadForm() {
    const form = document.getElementById('upload-form');
    if (!form) return;

    const sourceRadios = form.querySelectorAll('input[name="source"]');
    const uploadGroup = document.getElementById('upload-group');
    const recordingGroup = document.getElementById('recording-group');

    function toggleSource() {
        const source = form.querySelector('input[name="source"]:checked')?.value;
        if (uploadGroup) uploadGroup.style.display = source === 'upload' ? 'block' : 'none';
        if (recordingGroup) recordingGroup.style.display = source === 'recording' ? 'block' : 'none';
    }

    sourceRadios.forEach(r => r.addEventListener('change', toggleSource));
    toggleSource();
}

// ── SSE Progress tracking ──

function initProgress() {
    const container = document.getElementById('progress-container');
    if (!container) return;

    const jobId = container.dataset.jobId;
    if (!jobId) return;

    const percentEl = document.getElementById('progress-percent');
    const stageEl = document.getElementById('progress-stage');
    const messageEl = document.getElementById('progress-message');
    const barFill = document.getElementById('progress-bar-fill');
    const logEl = document.getElementById('progress-log');

    const evtSource = new EventSource(`/api/jobs/${jobId}/events`);

    evtSource.addEventListener('progress', (e) => {
        const data = JSON.parse(e.data);

        if (percentEl) percentEl.textContent = data.percent + '%';
        if (stageEl) stageEl.textContent = formatStage(data.status);
        if (messageEl) messageEl.textContent = data.message;
        if (barFill) barFill.style.width = data.percent + '%';

        appendLog(logEl, data.message);

        // If awaiting speakers, redirect to speaker identification
        if (data.status === 'awaiting_speakers' && data.speakers_url) {
            evtSource.close();
            window.location.href = data.speakers_url;
        }
    });

    evtSource.addEventListener('completed', (e) => {
        const data = JSON.parse(e.data);
        evtSource.close();

        if (percentEl) percentEl.textContent = '100%';
        if (stageEl) stageEl.textContent = 'Complete';
        if (barFill) barFill.style.width = '100%';
        appendLog(logEl, 'Processing complete!');

        // Redirect to session page after a brief pause
        if (data.session_url) {
            setTimeout(() => { window.location.href = data.session_url; }, 1500);
        }
    });

    evtSource.addEventListener('failed', (e) => {
        const data = JSON.parse(e.data);
        evtSource.close();

        if (stageEl) stageEl.textContent = 'Failed';
        if (stageEl) stageEl.style.color = 'var(--accent-red)';
        if (messageEl) messageEl.textContent = data.error || 'An error occurred';
        appendLog(logEl, 'ERROR: ' + (data.error || 'Unknown error'));
    });

    evtSource.addEventListener('error', () => {
        // EventSource will auto-reconnect; if the job is done this is expected
    });
}

function formatStage(status) {
    const names = {
        'queued': 'Queued',
        'loading_model': 'Loading Model',
        'loading_audio': 'Loading Audio',
        'transcribing': 'Transcribing',
        'aligning': 'Aligning',
        'diarizing': 'Diarizing Speakers',
        'awaiting_speakers': 'Awaiting Speaker Names',
        'saving': 'Saving',
        'generating_recap': 'Generating Recap',
        'pushing_to_wiki': 'Pushing to Wiki',
        'completed': 'Complete',
        'failed': 'Failed',
    };
    return names[status] || status;
}

function appendLog(logEl, message) {
    if (!logEl || !message) return;
    const entry = document.createElement('div');
    entry.className = 'log-entry';
    entry.textContent = message;
    logEl.appendChild(entry);
    logEl.scrollTop = logEl.scrollHeight;
}

// ── Speaker identification form ──

function initSpeakers() {
    const form = document.getElementById('speakers-form');
    if (!form) return;

    const jobId = form.dataset.jobId;
    const submitBtn = form.querySelector('button[type="submit"]');

    form.addEventListener('submit', async (e) => {
        e.preventDefault();

        const speakers = {};
        form.querySelectorAll('.speaker-name-input').forEach(input => {
            const speakerId = input.dataset.speakerId;
            const name = input.value.trim();
            if (name) speakers[speakerId] = name;
        });

        const skipRecap = form.querySelector('#skip-recap')?.checked || false;

        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<span class="spinner"></span> Saving...';
        }

        try {
            const resp = await fetch(`/api/jobs/${jobId}/speakers`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ speakers, skip_recap: skipRecap }),
            });

            if (!resp.ok) {
                const err = await resp.json();
                throw new Error(err.detail || 'Failed to submit speaker names');
            }

            // Go back to progress page to watch save/recap
            window.location.href = `/jobs/${jobId}`;

        } catch (err) {
            alert('Error: ' + err.message);
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.textContent = 'Save & Continue';
            }
        }
    });
}

// ── Tabs ──

function initTabs() {
    const tabButtons = document.querySelectorAll('.tab');
    if (!tabButtons.length) return;

    tabButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            const target = btn.dataset.tab;

            // Deactivate all
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

            // Activate selected
            btn.classList.add('active');
            const panel = document.getElementById('tab-' + target);
            if (panel) panel.classList.add('active');
        });
    });
}

// ── Recap regeneration ──

function initRecapRegenerate() {
    const btn = document.getElementById('regenerate-recap-btn');
    if (!btn) return;

    const sessionId = btn.dataset.sessionId;
    const recapContainer = document.getElementById('recap-content');

    btn.addEventListener('click', async () => {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner"></span> Regenerating...';

        try {
            const resp = await fetch(`/api/sessions/${sessionId}/recap`, { method: 'POST' });
            if (!resp.ok) {
                const err = await resp.json();
                throw new Error(err.detail || 'Recap generation failed');
            }

            const data = await resp.json();
            if (recapContainer) recapContainer.innerHTML = data.html;

        } catch (err) {
            alert('Error: ' + err.message);
        } finally {
            btn.disabled = false;
            btn.textContent = 'Regenerate Recap';
        }
    });
}

// ── Edit speakers (session detail page) ──

function initEditSpeakers() {
    const form = document.getElementById('edit-speakers-form');
    if (!form) return;

    const sessionId = form.dataset.sessionId;
    const statusEl = document.getElementById('speakers-save-status');
    const submitBtn = form.querySelector('button[type="submit"]');

    form.addEventListener('submit', async (e) => {
        e.preventDefault();

        const speakers = {};
        form.querySelectorAll('.speaker-edit-input').forEach(input => {
            const speakerId = input.dataset.speakerId;
            const name = input.value.trim();
            if (name) speakers[speakerId] = name;
        });

        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<span class="spinner"></span> Saving...';
        }
        if (statusEl) statusEl.textContent = '';

        try {
            const resp = await fetch(`/api/sessions/${sessionId}/speakers`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ speakers }),
            });

            if (!resp.ok) {
                const err = await resp.json();
                throw new Error(err.detail || 'Failed to update speakers');
            }

            const data = await resp.json();

            // Update the transcript viewer with re-named lines
            const viewer = document.querySelector('.transcript-viewer');
            if (viewer && data.transcript_lines) {
                viewer.innerHTML = data.transcript_lines
                    .map(line => `<div class="transcript-line">${escapeHtml(line)}</div>`)
                    .join('');
            }

            // Update the speaker list in the header
            const metaSpan = document.querySelector('.session-meta .speaker-names');
            if (metaSpan) {
                metaSpan.textContent = Object.values(speakers).join(', ');
            }

            if (statusEl) {
                statusEl.style.color = 'var(--accent-green)';
                statusEl.textContent = 'Saved!';
                setTimeout(() => { statusEl.textContent = ''; }, 3000);
            }

        } catch (err) {
            if (statusEl) {
                statusEl.style.color = 'var(--accent-red)';
                statusEl.textContent = 'Error: ' + err.message;
            }
        } finally {
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.textContent = 'Update Names';
            }
        }
    });
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ── Push to Wiki ──

function initPushToWiki() {
    const btn = document.getElementById('push-to-wiki-btn');
    if (!btn) return;

    const sessionId = btn.dataset.sessionId;
    const statusEl = document.getElementById('push-status');

    btn.addEventListener('click', async () => {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner"></span> Pushing...';
        if (statusEl) statusEl.textContent = '';

        try {
            const resp = await fetch(`/api/sessions/${sessionId}/push`, { method: 'POST' });
            const data = await resp.json();

            if (!resp.ok) {
                throw new Error(data.detail || 'Push failed');
            }

            if (statusEl) {
                statusEl.style.color = 'var(--accent-green)';
                statusEl.textContent = 'Pushed!';
            }
        } catch (err) {
            if (statusEl) {
                statusEl.style.color = 'var(--accent-red)';
                statusEl.textContent = err.message;
            }
        } finally {
            btn.disabled = false;
            btn.textContent = 'Push to Wiki';
        }
    });
}

// ── Init ──

document.addEventListener('DOMContentLoaded', () => {
    initUploadForm();
    initProgress();
    initSpeakers();
    initTabs();
    initRecapRegenerate();
    initEditSpeakers();
    initPushToWiki();
});
