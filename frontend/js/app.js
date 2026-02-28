/**
 * Main application logic.
 */

// ===== STATE =====
let currentProjectId = null;
let isStreaming = false;
let selectedReportType = null;
let carModeActive = false;
let documentPollInterval = null;

// ===== INIT =====
document.addEventListener('DOMContentLoaded', async () => {
  Voice.init();
  applySettings();
  await loadProjects();
  loadReportTypes();

  // Restore last project
  const lastProject = localStorage.getItem('lastProjectId');
  if (lastProject) {
    selectProject(lastProject);
  }
});

// ===== SETTINGS =====
function applySettings() {
  const dark = localStorage.getItem('darkMode') !== 'false';
  document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
  document.getElementById('setting-dark').checked = dark;
  document.getElementById('setting-autoread').checked = Voice.settings.autoread;
  document.getElementById('setting-server-tts').checked = Voice.settings.serverTts;
}

function saveSetting(key, value) {
  localStorage.setItem(key, value);
  if (key === 'darkMode') {
    document.documentElement.setAttribute('data-theme', value ? 'dark' : 'light');
  }
  if (key in Voice.settings) {
    Voice.settings[key] = value;
  }
}

// ===== PROJECTS =====
async function loadProjects() {
  try {
    const projects = await API.get('/projects');
    renderProjectList(projects);
  } catch (e) {
    showToast('Failed to load projects', 'error');
  }
}

function renderProjectList(projects) {
  const list = document.getElementById('project-list');
  if (projects.length === 0) {
    list.innerHTML = '<li class="subtext" style="padding:12px 10px">No projects yet</li>';
    return;
  }
  list.innerHTML = projects.map(p => `
    <li class="project-item ${p.id === currentProjectId ? 'active' : ''}"
        onclick="selectProject('${p.id}')">
      <div class="project-item-name">${escapeHtml(p.name)}</div>
      <div class="project-item-meta">${p.doc_count} docs · ${p.msg_count} messages</div>
    </li>
  `).join('');
}

async function selectProject(projectId) {
  currentProjectId = projectId;
  localStorage.setItem('lastProjectId', projectId);

  // Update sidebar active state
  document.querySelectorAll('.project-item').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.project-item').forEach(el => {
    if (el.onclick.toString().includes(projectId)) el.classList.add('active');
  });

  // Show chat panel
  showPanel('chat');

  try {
    const project = await API.get(`/projects/${projectId}`);
    document.getElementById('chat-project-name').textContent = project.name;
    document.getElementById('chat-project-desc').textContent = project.description || '';
    document.getElementById('car-project-name').textContent = project.name;
  } catch (e) {}

  // Default to chat tab
  switchTab('chat');
  await loadChatHistory();
}

// ===== PANELS =====
function showPanel(name) {
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  const panel = document.getElementById(`panel-${name}`);
  if (panel) panel.classList.add('active');
}

function goBack() {
  if (currentProjectId) {
    showPanel('chat');
  } else {
    showPanel('welcome');
  }
}

// ===== TABS =====
function switchTab(tab) {
  document.querySelectorAll('.btn-tab').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('[data-tab]').forEach(b => {
    if (b.dataset.tab === tab) b.classList.add('active');
  });
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  const el = document.getElementById(`tab-${tab}`);
  if (el) el.classList.add('active');

  if (tab === 'documents') loadDocuments();
  if (tab === 'reports') loadReports();
}

// ===== CHAT =====
async function loadChatHistory() {
  if (!currentProjectId) return;
  const messagesEl = document.getElementById('messages');
  messagesEl.innerHTML = '<div class="typing-indicator"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div>';

  try {
    const data = await API.get(`/chat/${currentProjectId}/history`);
    messagesEl.innerHTML = '';

    if (data.summary) {
      messagesEl.appendChild(createSummaryBanner(data.summary));
    }

    data.messages.forEach(m => appendMessage(m.role, m.content, false));
    scrollToBottom();
  } catch (e) {
    messagesEl.innerHTML = '';
    showToast('Failed to load conversation history', 'error');
  }
}

function createSummaryBanner(summary) {
  const div = document.createElement('div');
  div.style.cssText = 'background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:12px 16px;font-size:12px;color:var(--text2);margin-bottom:8px;';
  div.innerHTML = `<strong>📋 Earlier discussion summary:</strong><br>${escapeHtml(summary).substring(0, 300)}...`;
  return div;
}

function appendMessage(role, content, animate = true) {
  const messagesEl = document.getElementById('messages');

  // Remove typing indicator if present
  const typing = messagesEl.querySelector('.typing-indicator');
  if (typing) typing.remove();

  const div = document.createElement('div');
  div.className = `message ${role}`;
  if (!animate) div.style.animation = 'none';

  const avatar = document.createElement('div');
  avatar.className = 'message-avatar';
  avatar.textContent = role === 'user' ? '👤' : '🤖';

  const body = document.createElement('div');
  body.className = 'message-body';

  if (role === 'assistant') {
    body.innerHTML = marked.parse(content);
  } else {
    body.textContent = content;
  }

  div.appendChild(avatar);
  div.appendChild(body);
  messagesEl.appendChild(div);

  return body; // return for streaming updates
}

function appendToolIndicator(toolName, query) {
  const messagesEl = document.getElementById('messages');
  const div = document.createElement('div');
  div.className = 'tool-indicator';
  div.id = 'tool-indicator';
  const icons = { web_search: '🔍', calculate_yield: '🧮', calculate_development_margin: '📊', calculate_irr: '📈', calculate_loan: '💰', estimate_stamp_duty: '🏛️' };
  const icon = icons[toolName] || '⚙️';
  div.innerHTML = `${icon} <span>${toolName === 'web_search' ? `Searching: "${query}"` : `Calculating: ${toolName.replace(/_/g, ' ')}`}</span>`;
  messagesEl.appendChild(div);
  scrollToBottom();
  return div;
}

async function sendMessage(overrideText = null) {
  if (isStreaming) return;
  if (!currentProjectId) {
    showToast('Select a project first', 'error');
    return;
  }

  const input = document.getElementById('chat-input');
  const message = overrideText || input.value.trim();
  if (!message) return;

  input.value = '';
  autoResizeTextarea(input);
  isStreaming = true;
  document.getElementById('send-btn').disabled = true;

  // Show user message
  appendMessage('user', message);

  // Show typing indicator
  const messagesEl = document.getElementById('messages');
  const typingDiv = document.createElement('div');
  typingDiv.className = 'typing-indicator';
  typingDiv.id = 'typing';
  typingDiv.innerHTML = '<div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>';
  messagesEl.appendChild(typingDiv);
  scrollToBottom();

  // Car mode mirror
  if (carModeActive) {
    appendCarMessage('user', message);
  }

  let assistantBody = null;
  let fullResponse = '';
  let toolIndicator = null;

  API.streamChat(
    currentProjectId,
    message,
    (payload) => {
      const typing = document.getElementById('typing');
      if (typing) typing.remove();

      if (toolIndicator) {
        toolIndicator.remove();
        toolIndicator = null;
      }

      if (payload.type === 'text') {
        if (!assistantBody) {
          assistantBody = appendMessage('assistant', '');
        }
        fullResponse += payload.content;
        assistantBody.innerHTML = marked.parse(fullResponse);
        scrollToBottom();

        if (carModeActive) {
          const carMsgs = document.getElementById('car-messages');
          let lastMsg = carMsgs.querySelector('.car-message.assistant:last-child');
          if (!lastMsg) {
            lastMsg = document.createElement('div');
            lastMsg.className = 'car-message assistant';
            carMsgs.appendChild(lastMsg);
          }
          lastMsg.textContent = fullResponse;
          carMsgs.scrollTop = carMsgs.scrollHeight;
        }
      } else if (payload.type === 'tool_start' || payload.type === 'tool_running') {
        toolIndicator = appendToolIndicator(payload.tool, payload.query || '');
      } else if (payload.type === 'tool_done') {
        if (toolIndicator) { toolIndicator.remove(); toolIndicator = null; }
      }
    },
    () => {
      // Done
      isStreaming = false;
      document.getElementById('send-btn').disabled = false;
      const typing = document.getElementById('typing');
      if (typing) typing.remove();
      if (toolIndicator) toolIndicator.remove();

      if (fullResponse && Voice.settings.autoread) {
        Voice.speak(fullResponse, carModeActive);
      }

      if (carModeActive && fullResponse) {
        document.getElementById('car-status').textContent = 'Tap mic to speak';
      }

      // Refresh project list (message count updated)
      loadProjects();
    },
    (err) => {
      isStreaming = false;
      document.getElementById('send-btn').disabled = false;
      const typing = document.getElementById('typing');
      if (typing) typing.remove();
      showToast('Error: ' + err.message, 'error');
    }
  );

  scrollToBottom();
}

window.sendMessage = sendMessage;

function handleChatKeydown(event) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
}

function autoResizeTextarea(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 160) + 'px';
}

function scrollToBottom() {
  const el = document.getElementById('messages');
  if (el) el.scrollTop = el.scrollHeight;
}

async function clearChatHistory() {
  if (!currentProjectId) return;
  if (!confirm('Clear all conversation history for this project?')) return;
  try {
    await API.del(`/chat/${currentProjectId}/history`);
    document.getElementById('messages').innerHTML = '';
    showToast('Conversation cleared');
  } catch (e) {
    showToast('Failed to clear history', 'error');
  }
}

// ===== VOICE =====
function toggleVoiceInput(isCarMode = false) {
  Voice.toggleListening(isCarMode);
}

// ===== CAR MODE =====
function toggleCarMode() {
  carModeActive = !carModeActive;
  const overlay = document.getElementById('car-mode');
  overlay.classList.toggle('hidden', !carModeActive);
  if (carModeActive) {
    Voice.stopSpeaking();
    // Mirror last few messages
    const carMsgs = document.getElementById('car-messages');
    carMsgs.innerHTML = '';
    document.querySelectorAll('#messages .message').forEach(m => {
      const role = m.classList.contains('user') ? 'user' : 'assistant';
      const text = m.querySelector('.message-body').textContent;
      appendCarMessage(role, text.substring(0, 500));
    });
    carMsgs.scrollTop = carMsgs.scrollHeight;
  }
}

function appendCarMessage(role, content) {
  const carMsgs = document.getElementById('car-messages');
  const div = document.createElement('div');
  div.className = `car-message ${role}`;
  div.textContent = content;
  carMsgs.appendChild(div);
  carMsgs.scrollTop = carMsgs.scrollHeight;
}

// ===== DOCUMENTS =====
async function loadDocuments() {
  if (!currentProjectId) return;
  try {
    const docs = await API.get(`/documents/${currentProjectId}`);
    renderDocuments(docs);

    // Poll if any docs are still indexing
    const indexing = docs.some(d => d.status === 'indexing');
    clearInterval(documentPollInterval);
    if (indexing) {
      documentPollInterval = setInterval(async () => {
        const updated = await API.get(`/documents/${currentProjectId}`);
        renderDocuments(updated);
        if (!updated.some(d => d.status === 'indexing')) {
          clearInterval(documentPollInterval);
        }
      }, 3000);
    }
  } catch (e) {
    showToast('Failed to load documents', 'error');
  }
}

function renderDocuments(docs) {
  const list = document.getElementById('documents-list');
  if (docs.length === 0) {
    list.innerHTML = '<p class="subtext" style="text-align:center;padding:20px">No documents uploaded yet</p>';
    return;
  }
  const icons = { pdf: '📄', docx: '📝', doc: '📝', xlsx: '📊', xls: '📊', txt: '📃' };
  list.innerHTML = docs.map(d => `
    <div class="document-item">
      <div class="doc-icon">${icons[d.file_type] || '📎'}</div>
      <div class="doc-info">
        <div class="doc-name">${escapeHtml(d.filename)}</div>
        <div class="doc-meta">${formatSize(d.file_size)} · ${d.chunk_count} chunks · ${formatDate(d.created_at)}</div>
      </div>
      <span class="doc-status ${d.status}">${d.status}</span>
      <button class="doc-delete" onclick="deleteDocument('${d.id}')" title="Delete">✕</button>
    </div>
  `).join('');
}

function handleDragOver(e) {
  e.preventDefault();
  document.getElementById('upload-zone').classList.add('dragover');
}

function handleDragLeave(e) {
  document.getElementById('upload-zone').classList.remove('dragover');
}

async function handleDrop(e) {
  e.preventDefault();
  document.getElementById('upload-zone').classList.remove('dragover');
  const files = Array.from(e.dataTransfer.files);
  for (const file of files) await uploadFile(file);
}

async function handleFileSelect(e) {
  const files = Array.from(e.target.files);
  for (const file of files) await uploadFile(file);
  e.target.value = '';
}

async function uploadFile(file) {
  if (!currentProjectId) {
    showToast('Select a project first', 'error');
    return;
  }
  showToast(`Uploading ${file.name}...`);
  try {
    await API.uploadFile(currentProjectId, file);
    showToast(`${file.name} uploaded, indexing...`, 'success');
    loadDocuments();
    loadProjects();
  } catch (e) {
    showToast(`Upload failed: ${e.message}`, 'error');
  }
}

async function deleteDocument(docId) {
  if (!confirm('Delete this document? It will be removed from the knowledge base.')) return;
  try {
    await API.del(`/documents/${docId}`);
    showToast('Document deleted');
    loadDocuments();
    loadProjects();
  } catch (e) {
    showToast('Failed to delete document', 'error');
  }
}

// ===== REPORTS =====
async function loadReportTypes() {
  try {
    const types = await API.get('/reports/types');
    const container = document.getElementById('report-types');
    container.innerHTML = types.map(t => `
      <button class="report-type-btn ${selectedReportType === t.id ? 'selected' : ''}"
              onclick="selectReportType('${t.id}', this)">
        ${t.label}
      </button>
    `).join('');
  } catch (e) {}
}

function selectReportType(type, btn) {
  selectedReportType = type;
  document.querySelectorAll('.report-type-btn').forEach(b => b.classList.remove('selected'));
  btn.classList.add('selected');
}

async function loadReports() {
  if (!currentProjectId) return;
  try {
    const reports = await API.get(`/reports/${currentProjectId}`);
    const list = document.getElementById('reports-list');
    if (reports.length === 0) {
      list.innerHTML = '<p class="subtext" style="text-align:center;padding:20px">No reports generated yet</p>';
      return;
    }
    list.innerHTML = reports.map(r => `
      <div class="report-item">
        <div>
          <div class="report-item-name">${escapeHtml(r.filename)}</div>
          <div class="report-item-meta">${formatSize(r.size)} · ${formatDate(r.created_at)}</div>
        </div>
        <a href="/api/reports/${currentProjectId}/${encodeURIComponent(r.filename)}"
           download="${r.filename}" class="btn-primary" style="font-size:12px;padding:6px 14px">
          Download
        </a>
      </div>
    `).join('');
  } catch (e) {
    showToast('Failed to load reports', 'error');
  }
}

async function generateReport() {
  if (!currentProjectId) {
    showToast('Select a project first', 'error');
    return;
  }
  if (!selectedReportType) {
    showToast('Select a report type first', 'error');
    return;
  }

  const instructions = document.getElementById('report-instructions').value.trim();
  showToast('Generating report... this may take a minute', 'success');

  try {
    const result = await API.post('/reports/generate', {
      project_id: currentProjectId,
      report_type: selectedReportType,
      custom_instructions: instructions || null,
    });
    showToast('Report generated!', 'success');
    loadReports();

    // Show report in chat tab as a message
    switchTab('chat');
    appendMessage('assistant', `## Report Generated: ${selectedReportType.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}\n\n${result.content.substring(0, 3000)}...\n\n*Full report available in the Reports tab*`);
    scrollToBottom();
  } catch (e) {
    showToast('Report generation failed: ' + e.message, 'error');
  }
}

// ===== PROJECT MODALS =====
function showNewProjectModal() {
  document.getElementById('modal-new-project').style.display = 'flex';
  document.getElementById('modal-edit-project').style.display = 'none';
  document.getElementById('modal-overlay').classList.remove('hidden');
  setTimeout(() => document.getElementById('new-project-name').focus(), 50);
}

async function createProject() {
  const name = document.getElementById('new-project-name').value.trim();
  if (!name) {
    showToast('Project name is required', 'error');
    return;
  }
  const desc = document.getElementById('new-project-desc').value.trim();
  try {
    const project = await API.post('/projects', { name, description: desc });
    closeModal();
    document.getElementById('new-project-name').value = '';
    document.getElementById('new-project-desc').value = '';
    await loadProjects();
    selectProject(project.id);
    showToast(`Project "${name}" created`, 'success');
  } catch (e) {
    showToast('Failed to create project: ' + e.message, 'error');
  }
}

function showProjectSettings() {
  if (!currentProjectId) return;
  const nameEl = document.getElementById('chat-project-name');
  const descEl = document.getElementById('chat-project-desc');
  document.getElementById('edit-project-name').value = nameEl.textContent;
  document.getElementById('edit-project-desc').value = descEl.textContent;
  document.getElementById('modal-new-project').style.display = 'none';
  document.getElementById('modal-edit-project').style.display = 'flex';
  document.getElementById('modal-overlay').classList.remove('hidden');
}

async function saveProjectEdit() {
  const name = document.getElementById('edit-project-name').value.trim();
  const desc = document.getElementById('edit-project-desc').value.trim();
  if (!name) { showToast('Name is required', 'error'); return; }
  try {
    await API.put(`/projects/${currentProjectId}`, { name, description: desc });
    closeModal();
    document.getElementById('chat-project-name').textContent = name;
    document.getElementById('chat-project-desc').textContent = desc;
    await loadProjects();
    showToast('Project updated', 'success');
  } catch (e) {
    showToast('Failed to update project', 'error');
  }
}

async function deleteCurrentProject() {
  if (!confirm('Delete this project and all its data? This cannot be undone.')) return;
  try {
    await API.del(`/projects/${currentProjectId}`);
    closeModal();
    currentProjectId = null;
    localStorage.removeItem('lastProjectId');
    showPanel('welcome');
    await loadProjects();
    showToast('Project deleted');
  } catch (e) {
    showToast('Failed to delete project', 'error');
  }
}

function closeModal(event) {
  if (event && event.target !== document.getElementById('modal-overlay')) return;
  document.getElementById('modal-overlay').classList.add('hidden');
}

// ===== TOAST =====
let toastTimer = null;
function showToast(msg, type = '') {
  const toast = document.getElementById('toast');
  toast.textContent = msg;
  toast.className = `toast ${type}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.add('hidden'), 3500);
}

// ===== UTILS =====
function escapeHtml(str) {
  const div = document.createElement('div');
  div.appendChild(document.createTextNode(str || ''));
  return div.innerHTML;
}

function formatSize(bytes) {
  if (!bytes) return '0 B';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1048576) return `${(bytes/1024).toFixed(1)} KB`;
  return `${(bytes/1048576).toFixed(1)} MB`;
}

function formatDate(ts) {
  if (!ts) return '';
  const d = typeof ts === 'number' ? new Date(ts * 1000) : new Date(ts);
  return d.toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' });
}
