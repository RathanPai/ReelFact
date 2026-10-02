// ReelFact Modern Frontend Application Logic

let currentVideoId = null;
let pollInterval = null;

// DOM Elements
const urlTabBtn = document.getElementById('tab-url-btn');
const uploadTabBtn = document.getElementById('tab-upload-btn');
const urlView = document.getElementById('url-view');
const uploadView = document.getElementById('upload-view');
const urlForm = document.getElementById('url-form');
const reelUrlInput = document.getElementById('reel-url-input');
const dropzone = document.getElementById('dropzone');
const fileInput = document.getElementById('file-input');

const progressCard = document.getElementById('pipeline-progress-card');
const currentStepLabel = document.getElementById('current-step-label');
const progressPercent = document.getElementById('progress-percent');
const progressBarFill = document.getElementById('progress-bar-fill');
const workspaceGrid = document.getElementById('workspace-grid');

const reelVideo = document.getElementById('reel-video');
const metaTitle = document.getElementById('meta-title');
const metaAuthor = document.getElementById('meta-author');
const transcriptContainer = document.getElementById('transcript-container');
const transcriptCount = document.getElementById('transcript-count');

const scoreCircle = document.getElementById('score-circle');
const scoreNumber = document.getElementById('score-number');
const overallVerdictBadge = document.getElementById('overall-verdict-badge');
const executiveSummaryText = document.getElementById('executive-summary-text');
const claimsStatsBar = document.getElementById('claims-stats-bar');
const claimsTotalCount = document.getElementById('claims-total-count');
const claimsList = document.getElementById('claims-list');

const chatMessagesBox = document.getElementById('chat-messages-box');
const chatForm = document.getElementById('chat-form');
const chatInput = document.getElementById('chat-input');
const suggestedChips = document.getElementById('suggested-chips');

const historyBtn = document.getElementById('history-btn');
const historyModal = document.getElementById('history-modal');
const modalCloseBtn = document.getElementById('modal-close-btn');
const historyList = document.getElementById('history-list');

// Tab Switching
urlTabBtn.addEventListener('click', () => {
  urlTabBtn.classList.add('active');
  uploadTabBtn.classList.remove('active');
  urlView.style.display = 'block';
  uploadView.style.display = 'none';
});

uploadTabBtn.addEventListener('click', () => {
  uploadTabBtn.classList.add('active');
  urlTabBtn.classList.remove('active');
  uploadView.style.display = 'block';
  urlView.style.display = 'none';
});

// Dropzone file upload handlers
dropzone.addEventListener('click', () => fileInput.click());
dropzone.addEventListener('dragover', (e) => {
  e.preventDefault();
  dropzone.classList.add('dragover');
});
dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
dropzone.addEventListener('drop', (e) => {
  e.preventDefault();
  dropzone.classList.remove('dragover');
  if (e.dataTransfer.files.length > 0) {
    handleFileUpload(e.dataTransfer.files[0]);
  }
});

fileInput.addEventListener('change', (e) => {
  if (e.target.files.length > 0) {
    handleFileUpload(e.target.files[0]);
  }
});

// URL Form Submission
urlForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const url = reelUrlInput.value.trim();
  if (!url) return;

  startProcessingUI();

  try {
    const res = await fetch('/api/check/url', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url })
    });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    currentVideoId = data.video_id;
    startPolling(currentVideoId);
  } catch (err) {
    alert('Error starting fact check: ' + err.message);
    resetProgressUI();
  }
});

async function handleFileUpload(file) {
  startProcessingUI();

  const formData = new FormData();
  formData.append('file', file);

  try {
    const res = await fetch('/api/check/upload', {
      method: 'POST',
      body: formData
    });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    currentVideoId = data.video_id;
    startPolling(currentVideoId);
  } catch (err) {
    alert('Upload error: ' + err.message);
    resetProgressUI();
  }
}

function startProcessingUI() {
  progressCard.style.display = 'block';
  workspaceGrid.style.display = 'none';
  updateProgress(5, 'Initializing Ingestion Pipeline...');
  resetSteppers();
}

function resetProgressUI() {
  progressCard.style.display = 'none';
  if (pollInterval) clearInterval(pollInterval);
}

function resetSteppers() {
  for (let i = 1; i <= 5; i++) {
    const step = document.getElementById(`step-${i}`);
    if (step) {
      step.className = 'step-pill';
    }
  }
}

function updateProgress(percent, label) {
  progressPercent.textContent = `${percent}%`;
  progressBarFill.style.width = `${percent}%`;
  currentStepLabel.textContent = label;

  const step1 = document.getElementById('step-1');
  const step2 = document.getElementById('step-2');
  const step3 = document.getElementById('step-3');
  const step4 = document.getElementById('step-4');
  const step5 = document.getElementById('step-5');

  if (percent >= 10) step1.className = 'step-pill active';
  if (percent >= 25) { step1.className = 'step-pill completed'; step2.className = 'step-pill active'; }
  if (percent >= 55) { step2.className = 'step-pill completed'; step3.className = 'step-pill active'; }
  if (percent >= 75) { step3.className = 'step-pill completed'; step4.className = 'step-pill active'; }
  if (percent >= 88) { step4.className = 'step-pill completed'; step5.className = 'step-pill active'; }
  if (percent >= 100) { step5.className = 'step-pill completed'; }
}

function startPolling(videoId) {
  if (pollInterval) clearInterval(pollInterval);

  pollInterval = setInterval(async () => {
    try {
      const res = await fetch(`/api/status/${videoId}`);
      if (!res.ok) return;
      const data = await res.json();

      updateProgress(data.progress || 0, data.step || 'Processing...');

      if (data.status === 'done') {
        clearInterval(pollInterval);
        setTimeout(() => loadCompletedReel(videoId), 600);
      } else if (data.status === 'error') {
        clearInterval(pollInterval);
        alert('Fact-checking failed: ' + (data.error || 'Unknown error'));
        resetProgressUI();
      }
    } catch (e) {
      console.error('Polling error', e);
    }
  }, 1500);
}

async function loadCompletedReel(videoId) {
  currentVideoId = videoId;
  progressCard.style.display = 'none';

  try {
    const res = await fetch(`/api/reels/${videoId}`);
    if (!res.ok) throw new Error('Failed to load reel details');
    const data = await res.json();

    renderDossier(data.dossier);
    if (data.transcript) {
      renderTranscript(data.transcript);
    }
    if (data.chat_history) {
      renderChatHistory(data.chat_history);
    }

    // Set video source
    reelVideo.src = `/api/media/${videoId}`;
    workspaceGrid.style.display = 'grid';
    workspaceGrid.scrollIntoView({ behavior: 'smooth' });
  } catch (err) {
    alert('Error loading dossier: ' + err.message);
  }
}

function renderDossier(dossier) {
  metaTitle.textContent = dossier.title || 'Instagram Reel Fact-Check';
  metaAuthor.textContent = `Creator: ${dossier.author || 'Unknown'}`;

  // Trust Score Gauge
  const score = dossier.overall_trust_score;
  scoreNumber.textContent = score;

  let scoreColor = 'var(--verdict-true)';
  let verdictClass = 'true';

  if (score < 40) {
    scoreColor = 'var(--verdict-false)';
    verdictClass = 'false';
  } else if (score < 75) {
    scoreColor = 'var(--verdict-misleading)';
    verdictClass = 'misleading';
  }

  scoreCircle.style.borderColor = scoreColor;
  scoreCircle.style.boxShadow = `0 0 20px ${scoreColor}40`;

  overallVerdictBadge.className = `verdict-badge ${verdictClass}`;
  overallVerdictBadge.textContent = dossier.overall_verdict.replace('_', ' ');

  executiveSummaryText.textContent = dossier.executive_summary;

  // Stats bar
  claimsStatsBar.innerHTML = `
    <span class="stat-pill" style="background: var(--verdict-true-bg); color: var(--verdict-true);">${dossier.true_count} True</span>
    <span class="stat-pill" style="background: var(--verdict-misleading-bg); color: var(--verdict-misleading);">${dossier.misleading_count} Misleading</span>
    <span class="stat-pill" style="background: var(--verdict-false-bg); color: var(--verdict-false);">${dossier.false_count} False</span>
  `;

  claimsTotalCount.textContent = dossier.claims.length;

  // Render Claims
  claimsList.innerHTML = '';
  dossier.claims.forEach((claim, idx) => {
    const claimEl = document.createElement('div');
    claimEl.className = 'claim-card';

    let badgeType = claim.verdict.toLowerCase();
    if (badgeType === 'mostly_true') badgeType = 'mostly_true';

    const sourcesHtml = claim.sources.map(src => {
      let tierClass = 'tier_3';
      let tierText = 'GENERAL';
      if (src.credibility_tier.includes('TIER_1')) { tierClass = 'tier_1'; tierText = 'TIER 1 • AUTHORITATIVE'; }
      else if (src.credibility_tier.includes('TIER_2')) { tierClass = 'tier_2'; tierText = 'TIER 2 • REPUTABLE'; }

      return `
        <a href="${src.url}" target="_blank" rel="noopener noreferrer" class="source-card-link">
          <div class="source-domain-row">
            <span class="source-domain-name">${src.domain}</span>
            <span class="tier-badge ${tierClass}">${tierText}</span>
          </div>
          <div class="source-article-title">${escapeHtml(src.title)}</div>
          <div class="source-snippet">${escapeHtml(src.snippet || src.relevant_quote || '')}</div>
        </a>
      `;
    }).join('');

    claimEl.innerHTML = `
      <div class="claim-header">
        <h4 class="claim-text-title">"${escapeHtml(claim.claim_text)}"</h4>
        <span class="verdict-badge ${badgeType}">${claim.verdict.replace('_', ' ')}</span>
      </div>

      <div class="claim-meta-row">
        <span class="timestamp-pill" data-time="${claim.timestamp_start}">
          ⏱ ${formatTimestamp(claim.timestamp_start)} - ${formatTimestamp(claim.timestamp_end)}
        </span>
        <span class="confidence-meter">Confidence: ${claim.confidence_score}%</span>
      </div>

      <div class="claim-rationale-box">
        <strong>Verdict Summary:</strong> ${escapeHtml(claim.summary_rationale)}
      </div>

      <div class="claim-detailed-body">
        ${escapeHtml(claim.detailed_analysis)}
        ${claim.key_nuances ? `<p style="margin-top: 0.5rem; color: #a5b4fc;"><strong>Nuance:</strong> ${escapeHtml(claim.key_nuances)}</p>` : ''}
      </div>

      ${claim.sources.length > 0 ? `
        <div class="sources-group-title">Credible Source Evidence (${claim.sources.length})</div>
        <div class="sources-grid">
          ${sourcesHtml}
        </div>
      ` : ''}
    `;

    // Timestamp seek event
    const tsBtn = claimEl.querySelector('.timestamp-pill');
    if (tsBtn) {
      tsBtn.addEventListener('click', () => {
        reelVideo.currentTime = claim.timestamp_start;
        reelVideo.play();
      });
    }

    claimsList.appendChild(claimEl);
  });
}

function renderTranscript(transcript) {
  transcriptContainer.innerHTML = '';
  transcriptCount.textContent = `${transcript.segments.length} segments`;

  transcript.segments.forEach(seg => {
    const row = document.createElement('div');
    row.className = 'transcript-row';
    
    let content = '';
    if (seg.audio_text) content += `<span style="color: #e2e8f0;">${escapeHtml(seg.audio_text)}</span>`;
    if (seg.ocr_text) content += ` <span style="color: #a5b4fc; font-style: italic;">[OCR: ${escapeHtml(seg.ocr_text)}]</span>`;

    row.innerHTML = `
      <span class="ts-tag">${formatTimestamp(seg.start)}</span>
      <div>${content}</div>
    `;

    row.addEventListener('click', () => {
      reelVideo.currentTime = seg.start;
      reelVideo.play();
    });

    transcriptContainer.appendChild(row);
  });
}

// Chat follow-up handling
chatForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const text = chatInput.value.trim();
  if (!text || !currentVideoId) return;

  chatInput.value = '';
  appendChatMessage('user', text);

  // Add temporary typing bubble
  const typingBubble = document.createElement('div');
  typingBubble.className = 'chat-bubble assistant';
  typingBubble.innerHTML = '<span style="color: var(--text-subtle);">Searching evidence & reasoning...</span>';
  chatMessagesBox.appendChild(typingBubble);
  chatMessagesBox.scrollTop = chatMessagesBox.scrollHeight;

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ video_id: currentVideoId, message: text })
    });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    typingBubble.remove();
    appendChatMessage('assistant', data.answer);
  } catch (err) {
    typingBubble.innerHTML = `<span style="color: var(--verdict-false);">Error: ${err.message}</span>`;
  }
});

function appendChatMessage(role, content) {
  const bubble = document.createElement('div');
  bubble.className = `chat-bubble ${role}`;
  // Simple markdown conversion for paragraphs & lists
  bubble.innerHTML = formatMarkdown(content);
  chatMessagesBox.appendChild(bubble);
  chatMessagesBox.scrollTop = chatMessagesBox.scrollHeight;
}

function renderChatHistory(messages) {
  chatMessagesBox.innerHTML = '';
  if (messages.length === 0) {
    appendChatMessage('assistant', "Hello! I've fact-checked this reel against peer-reviewed journals, official agencies, and verified news. Feel free to ask any follow-up questions!");
    return;
  }
  messages.forEach(m => appendChatMessage(m.role, m.content));
}

// Suggested prompt chips
suggestedChips.addEventListener('click', (e) => {
  if (e.target.classList.contains('chip-btn')) {
    const query = e.target.getAttribute('data-query');
    chatInput.value = query;
    chatForm.dispatchEvent(new Event('submit'));
  }
});

// History Modal
historyBtn.addEventListener('click', async () => {
  historyModal.classList.add('open');
  try {
    const res = await fetch('/api/reels');
    const items = await res.json();
    if (items.length === 0) {
      historyList.innerHTML = '<p style="color: var(--text-subtle);">No fact-checked reels found yet.</p>';
      return;
    }
    historyList.innerHTML = items.map(item => `
      <div class="transcript-row" style="justify-content: space-between; align-items: center;" onclick="loadHistoryItem('${item.id}')">
        <div>
          <div style="font-weight: 600; color: #f8fafc;">${escapeHtml(item.title)}</div>
          <div style="font-size: 0.75rem; color: var(--text-subtle);">${escapeHtml(item.author)} • ${new Date(item.created_at).toLocaleDateString()}</div>
        </div>
        <span class="stat-pill" style="background: var(--verdict-true-bg); color: var(--verdict-true);">${item.trust_score}/100</span>
      </div>
    `).join('');
  } catch (err) {
    historyList.innerHTML = `<p style="color: var(--verdict-false);">Failed to load history.</p>`;
  }
});

window.loadHistoryItem = (id) => {
  historyModal.classList.remove('open');
  loadCompletedReel(id);
};

modalCloseBtn.addEventListener('click', () => historyModal.classList.remove('open'));
historyModal.addEventListener('click', (e) => {
  if (e.target === historyModal) historyModal.classList.remove('open');
});

// Utilities
function formatTimestamp(seconds) {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs < 10 ? '0' : ''}${secs}`;
}

function escapeHtml(text) {
  if (!text) return '';
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function formatMarkdown(text) {
  if (!text) return '';
  let formatted = escapeHtml(text);
  // Bold **text**
  formatted = formatted.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  // URLs
  formatted = formatted.replace(/(https?:\/\/[^\s]+)/g, '<a href="$1" target="_blank" style="color: #a5b4fc;">$1</a>');
  // Newlines to breaks
  return formatted.replace(/\n/g, '<br>');
}

// -------------------------------------------------------------
// PWA Service Worker Registration & Web Share Target Receiver
// -------------------------------------------------------------
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js')
      .then((reg) => console.log('ReelFact PWA Service Worker active:', reg.scope))
      .catch((err) => console.debug('Service worker registration note:', err));
  });
}

// Intercept incoming Web Share Target URLs (from native Instagram Share Sheet)
window.addEventListener('DOMContentLoaded', () => {
  const params = new URLSearchParams(window.location.search);
  const sharedUrl = params.get('url');
  const sharedText = params.get('text');
  const sharedTitle = params.get('title');

  const combined = `${sharedUrl || ''} ${sharedText || ''} ${sharedTitle || ''}`.trim();
  if (!combined) return;

  // Extract valid URL from shared string
  const urlMatch = combined.match(/(https?:\/\/[^\s]+)/i);
  const targetUrl = urlMatch ? urlMatch[0] : (sharedUrl || null);

  if (targetUrl && reelUrlInput) {
    reelUrlInput.value = targetUrl;
    
    // Clean up address bar query params without reloading
    const cleanUrl = window.location.protocol + "//" + window.location.host + window.location.pathname;
    window.history.replaceState({ path: cleanUrl }, '', cleanUrl);

    // Auto-trigger analysis
    setTimeout(() => {
      if (urlForm) {
        urlForm.dispatchEvent(new Event('submit', { cancelable: true }));
      }
    }, 300);
  }
});

