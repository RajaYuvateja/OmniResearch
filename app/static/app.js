// OmniResearch — Minimalist Web Client with File Upload, Interactive Chatbot & Production API Config
document.addEventListener("DOMContentLoaded", () => {
  // DOM Elements
  const form = document.getElementById("research-form");
  const objectiveInput = document.getElementById("objective-input");
  const submitBtn = document.getElementById("submit-btn");
  const submitBtnText = document.getElementById("submit-btn-text");
  const heroSection = document.getElementById("hero-section");
  const workspaceSection = document.getElementById("workspace-section");
  const activeObjectiveTitle = document.getElementById("active-objective-title");
  const currentJobIdTag = document.getElementById("current-job-id-tag");
  const engineStatusText = document.getElementById("engine-status-text");
  const workspaceFileTag = document.getElementById("workspace-file-tag");
  const workspaceFileName = document.getElementById("workspace-file-name");

  // File Upload Elements
  const fileDropZone = document.getElementById("file-drop-zone");
  const fileInput = document.getElementById("file-input");
  const fileBrowseBtn = document.getElementById("file-browse-btn");
  const fileDropIdle = document.getElementById("file-drop-idle");
  const fileSelectedBadge = document.getElementById("file-selected-badge");
  const fileNameDisplay = document.getElementById("file-name-display");
  const fileSizeDisplay = document.getElementById("file-size-display");
  const fileRemoveBtn = document.getElementById("file-remove-btn");

  // Telemetry & Stepper
  const telemetryLogs = document.getElementById("telemetry-logs");
  const toggleLogsBtn = document.getElementById("toggle-logs-btn");

  // Exports
  const exportActionsBar = document.getElementById("export-actions-bar");
  const exportPdfBtn = document.getElementById("export-pdf-btn");
  const exportDocxBtn = document.getElementById("export-docx-btn");
  const exportPptxBtn = document.getElementById("export-pptx-btn");

  // Chat Elements
  const chatForm = document.getElementById("chat-form");
  const chatInput = document.getElementById("chat-input");
  const chatSendBtn = document.getElementById("chat-send-btn");
  const chatMessagesContainer = document.getElementById("chat-messages-container");
  const tabChatBtn = document.getElementById("tab-chat-btn");
  const jumpToChatBtn = document.getElementById("jump-to-chat-btn");
  const clearChatViewBtn = document.getElementById("clear-chat-view-btn");

  // History Drawer
  const historyDrawer = document.getElementById("history-drawer");
  const drawerBackdrop = document.getElementById("drawer-backdrop");
  const historyToggleBtn = document.getElementById("history-toggle-btn");
  const drawerCloseBtn = document.getElementById("drawer-close-btn");
  const historyItemsContainer = document.getElementById("history-items-container");
  const newResearchBtn = document.getElementById("new-research-btn");
  const toast = document.getElementById("toast");

  // API Settings Modal Elements
  const apiSettingsBtn = document.getElementById("api-settings-btn");
  const apiModalBackdrop = document.getElementById("api-modal-backdrop");
  const apiModalCloseBtn = document.getElementById("api-modal-close-btn");
  const apiBaseInput = document.getElementById("api-base-input");
  const apiProbeResult = document.getElementById("api-probe-result");
  const apiTestBtn = document.getElementById("api-test-btn");
  const apiSaveBtn = document.getElementById("api-save-btn");
  const apiStatusPill = document.getElementById("api-status-pill");

  // State
  let activeJobId = null;
  let activeJobData = null;
  let pollInterval = null;
  let currentReportMd = "";
  let attachedFile = null;
  let isSendingChat = false;

  const STAGES_ORDER = ["planner", "retriever", "verifier", "analyst", "visualizer", "writer"];

  // ----------------- CONFIGURABLE API BASE URL -----------------
  function getApiBase() {
    // 1. Check window.OMNI_API_BASE (set via config.js on static hosting like Vercel)
    if (window.OMNI_API_BASE && window.OMNI_API_BASE.trim()) {
      return window.OMNI_API_BASE.trim().replace(/\/+$/, "");
    }
    // 2. Check localStorage (custom user override)
    const stored = localStorage.getItem("omni_api_base");
    if (stored && stored.trim()) {
      return stored.trim().replace(/\/+$/, "");
    }
    // 3. Fallback to same-origin relative endpoints
    return "";
  }

  function apiUrl(endpoint) {
    const base = getApiBase();
    if (!base) return endpoint;
    const cleanEndpoint = endpoint.startsWith("/") ? endpoint : `/${endpoint}`;
    return `${base}${cleanEndpoint}`;
  }

  // Probe backend health to update UI indicator
  async function checkBackendHealth() {
    const base = getApiBase();
    if (apiStatusPill) {
      apiStatusPill.textContent = base ? "Connecting..." : "Backend: Local";
    }
    try {
      const res = await fetch(apiUrl("/health"));
      if (res.ok) {
        const data = await res.json();
        const dbType = data.database ? ` (${data.database})` : "";
        if (apiStatusPill) {
          apiStatusPill.textContent = base ? `Backend: Online${dbType}` : `Backend: Local${dbType}`;
          apiStatusPill.style.color = "#16a34a";
        }
      } else {
        if (apiStatusPill) {
          apiStatusPill.textContent = "Backend: HTTP " + res.status;
          apiStatusPill.style.color = "#dc2626";
        }
      }
    } catch (err) {
      if (apiStatusPill) {
        apiStatusPill.textContent = base ? "Backend: Offline" : "Backend: Disconnected";
        apiStatusPill.style.color = "#dc2626";
      }
    }
  }

  // Show Toast
  function showToast(msg) {
    toast.textContent = msg;
    toast.classList.add("show");
    setTimeout(() => toast.classList.remove("show"), 3500);
  }

  // ----------------- API SETTINGS MODAL -----------------
  if (apiSettingsBtn && apiModalBackdrop) {
    apiSettingsBtn.addEventListener("click", () => {
      apiBaseInput.value = localStorage.getItem("omni_api_base") || window.OMNI_API_BASE || "";
      apiProbeResult.innerHTML = `Current Base: <code>${getApiBase() || "(Same Origin)"}</code>`;
      apiProbeResult.style.color = "inherit";
      apiModalBackdrop.classList.remove("hidden");
    });

    apiModalCloseBtn.addEventListener("click", () => {
      apiModalBackdrop.classList.add("hidden");
    });

    apiModalBackdrop.addEventListener("click", (e) => {
      if (e.target === apiModalBackdrop) {
        apiModalBackdrop.classList.add("hidden");
      }
    });

    apiTestBtn.addEventListener("click", async () => {
      const testBase = apiBaseInput.value.trim().replace(/\/+$/, "");
      const testUrl = testBase ? `${testBase}/health` : "/health";
      apiProbeResult.innerHTML = "Pinging <code>" + testUrl + "</code>...";
      apiProbeResult.style.color = "inherit";
      try {
        const start = performance.now();
        const res = await fetch(testUrl);
        const elapsed = Math.round(performance.now() - start);
        if (res.ok) {
          const data = await res.json();
          apiProbeResult.innerHTML = `<strong>Connected (${elapsed}ms):</strong> Status: ${data.status || "healthy"}, DB: ${data.database || "ok"}`;
          apiProbeResult.style.color = "#16a34a";
        } else {
          apiProbeResult.innerHTML = `<strong>HTTP ${res.status}:</strong> Server returned an error.`;
          apiProbeResult.style.color = "#dc2626";
        }
      } catch (err) {
        apiProbeResult.innerHTML = `<strong>Connection Failed:</strong> ${err.message}. Check CORS or URL.`;
        apiProbeResult.style.color = "#dc2626";
      }
    });

    apiSaveBtn.addEventListener("click", () => {
      const newBase = apiBaseInput.value.trim().replace(/\/+$/, "");
      if (newBase) {
        localStorage.setItem("omni_api_base", newBase);
        showToast("Backend URL saved: " + newBase);
      } else {
        localStorage.removeItem("omni_api_base");
        showToast("Using default same-origin / config.js backend URL");
      }
      apiModalBackdrop.classList.add("hidden");
      checkBackendHealth();
    });
  }

  // File Upload Handlers
  fileBrowseBtn.addEventListener("click", () => fileInput.click());

  fileInput.addEventListener("change", (e) => {
    if (e.target.files && e.target.files[0]) {
      setAttachedFile(e.target.files[0]);
    }
  });

  // Drag and drop
  fileDropZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    fileDropZone.classList.add("dragover");
  });

  fileDropZone.addEventListener("dragleave", () => {
    fileDropZone.classList.remove("dragover");
  });

  fileDropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    fileDropZone.classList.remove("dragover");
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      setAttachedFile(e.dataTransfer.files[0]);
    }
  });

  function setAttachedFile(file) {
    attachedFile = file;
    fileNameDisplay.textContent = file.name;
    fileSizeDisplay.textContent = `(${formatBytes(file.size)})`;
    fileDropIdle.classList.add("hidden");
    fileSelectedBadge.classList.remove("hidden");
    showToast(`Attached ${file.name}`);
  }

  function clearAttachedFile() {
    attachedFile = null;
    fileInput.value = "";
    fileDropIdle.classList.remove("hidden");
    fileSelectedBadge.classList.add("hidden");
  }

  fileRemoveBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    clearAttachedFile();
  });

  function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  }

  // Prompt Chips
  document.querySelectorAll(".chip").forEach(chip => {
    chip.addEventListener("click", () => {
      objectiveInput.value = chip.dataset.prompt;
      objectiveInput.focus();
    });
  });

  // Tab Navigation
  const tabButtons = document.querySelectorAll(".tab-item");
  const tabPanels = document.querySelectorAll(".tab-panel");

  tabButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      switchTab(btn.dataset.tab);
    });
  });

  function switchTab(tabId) {
    tabButtons.forEach(b => b.classList.toggle("active", b.dataset.tab === tabId));
    tabPanels.forEach(p => p.classList.toggle("active", p.id === tabId));
    if (tabId === "tab-chat") {
      setTimeout(() => chatInput.focus(), 100);
    }
  }

  if (jumpToChatBtn) {
    jumpToChatBtn.addEventListener("click", () => {
      switchTab("tab-chat");
    });
  }

  // Toggle Telemetry Logs
  toggleLogsBtn.addEventListener("click", () => {
    const isHidden = telemetryLogs.classList.toggle("hidden-logs");
    toggleLogsBtn.textContent = isHidden ? "Show Logs" : "Hide Logs";
  });

  // Copy Markdown
  document.getElementById("copy-markdown-btn").addEventListener("click", () => {
    if (!currentReportMd) return;
    navigator.clipboard.writeText(currentReportMd).then(() => {
      showToast("Report Markdown copied to clipboard");
    });
  });

  // Start Fresh Research Session
  newResearchBtn.addEventListener("click", () => {
    if (pollInterval) clearInterval(pollInterval);
    activeJobId = null;
    activeJobData = null;
    objectiveInput.value = "";
    clearAttachedFile();
    workspaceSection.classList.add("hidden");
    heroSection.classList.remove("hidden");
    engineStatusText.textContent = "Ready";
    submitBtn.disabled = false;
    submitBtnText.textContent = "Start Research";
    heroSection.scrollIntoView({ behavior: "smooth" });
  });

  // Form Submit: Initiate Research
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const objective = objectiveInput.value.trim();

    if (!objective && !attachedFile) {
      showToast("Please enter a research objective or attach a document.");
      objectiveInput.focus();
      return;
    }

    submitBtn.disabled = true;
    submitBtnText.textContent = "Dispatching...";

    try {
      let res;
      if (attachedFile) {
        // Upload with multipart form data
        const formData = new FormData();
        formData.append("file", attachedFile);
        if (objective) formData.append("objective", objective);

        res = await fetch(apiUrl("/research/upload"), {
          method: "POST",
          body: formData
        });
      } else {
        // Standard JSON query
        res = await fetch(apiUrl("/research"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ objective })
        });
      }

      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson.detail || `Server error ${res.status}`);
      }

      const data = await res.json();
      activeJobId = data.id;

      prepareWorkspace(activeJobId, objective || (attachedFile ? `Analyze ${attachedFile.name}` : "Research"), attachedFile ? attachedFile.name : null);
      startPolling(activeJobId);
      showToast(`Job #${activeJobId} initialized.`);
    } catch (err) {
      showToast(`Error: ${err.message}`);
      submitBtn.disabled = false;
      submitBtnText.textContent = "Start Research";
    }
  });

  function prepareWorkspace(jid, objective, fileName) {
    workspaceSection.classList.remove("hidden");
    activeObjectiveTitle.textContent = objective;
    currentJobIdTag.textContent = `JOB #${jid}`;
    exportActionsBar.classList.add("hidden");
    engineStatusText.textContent = "Pipeline Running";

    if (fileName) {
      workspaceFileName.textContent = fileName;
      workspaceFileTag.classList.remove("hidden");
    } else {
      workspaceFileTag.classList.add("hidden");
    }

    // Reset Stepper
    STAGES_ORDER.forEach((s, idx) => {
      const item = document.getElementById(`step-${s}`);
      const line = document.getElementById(`line-${idx + 1}`);
      if (item) item.className = "step-item";
      if (line) line.className = "step-connector";
    });

    telemetryLogs.innerHTML = `<div class="log-entry">[0.0s] Registered in pipeline queue.</div>`;
    document.getElementById("report-markdown-container").innerHTML = `
      <div class="empty-state">
        <div class="spinner"></div>
        <p>Synthesizing research findings across verified sources...</p>
      </div>`;
    document.getElementById("claims-stack-container").innerHTML = `<div class="empty-state">Verification stage in progress...</div>`;
    document.getElementById("chart-display-container").innerHTML = `<div class="empty-state">Chart will render during Visualizer stage.</div>`;
    document.getElementById("sources-grid-container").innerHTML = `<div class="empty-state">Retriever agent querying web and documents...</div>`;

    // Reset Chat Messages
    chatMessagesContainer.innerHTML = `
      <div class="chat-message assistant">
        <div class="message-avatar">AI</div>
        <div class="message-content">
          <p>Autonomous research is now underway for <strong>${escapeHtml(objective)}</strong>. Feel free to prepare any follow-up questions you'd like to ask once synthesis completes!</p>
        </div>
      </div>
    `;

    // Default to report tab
    switchTab("tab-report");
    workspaceSection.scrollIntoView({ behavior: "smooth" });
  }

  function startPolling(jid) {
    if (pollInterval) clearInterval(pollInterval);
    pollInterval = setInterval(async () => {
      try {
        const res = await fetch(apiUrl(`/research/${jid}`));
        if (!res.ok) return;
        const job = await res.json();
        activeJobData = job;
        updateUI(job);

        if (job.status === "done" || job.status === "failed") {
          clearInterval(pollInterval);
          submitBtn.disabled = false;
          submitBtnText.textContent = "Start Research";
        }
      } catch (err) {
        console.error("Polling error:", err);
      }
    }, 1500);
  }

  function updateUI(job) {
    const currentStage = (job.stage || "").toLowerCase();
    const stageIdx = STAGES_ORDER.indexOf(currentStage);

    // Stepper updates
    STAGES_ORDER.forEach((s, i) => {
      const item = document.getElementById(`step-${s}`);
      const line = document.getElementById(`line-${i + 1}`);

      if (job.status === "done") {
        if (item) item.className = "step-item completed";
        if (line) line.className = "step-connector completed";
      } else if (stageIdx !== -1) {
        if (i < stageIdx) {
          if (item) item.className = "step-item completed";
          if (line) line.className = "step-connector completed";
        } else if (i === stageIdx) {
          if (item) item.className = "step-item active";
          if (line) line.className = "step-connector";
        } else {
          if (item) item.className = "step-item";
          if (line) line.className = "step-connector";
        }
      }
    });

    // Telemetry log updates
    if (job.log && job.log.length > 0) {
      telemetryLogs.innerHTML = job.log.map(l => `<div class="log-entry">&bull; ${escapeHtml(l)}</div>`).join("");
      telemetryLogs.scrollTop = telemetryLogs.scrollHeight;
    }

    if (job.status === "done") {
      engineStatusText.textContent = "Completed";
      renderCompletedResults(job);
    } else if (job.status === "failed") {
      engineStatusText.textContent = "Failed";
      showToast(`Pipeline Failed: ${job.error || "Unknown error"}`);
      document.getElementById("report-markdown-container").innerHTML = `
        <div class="empty-state text-danger">
          <p><strong>Execution Error:</strong> ${escapeHtml(job.error || "An error occurred during pipeline execution.")}</p>
        </div>`;
    }
  }

  function renderCompletedResults(job) {
    currentReportMd = job.report_md || "";

    // 1. Report
    if (currentReportMd) {
      document.getElementById("report-markdown-container").innerHTML = marked.parse(currentReportMd);
      document.getElementById("report-timestamp").textContent = `Generated: ${new Date().toLocaleTimeString()} • Verified Citations`;
    }

    // 2. Export Links
    exportActionsBar.classList.remove("hidden");
    exportPdfBtn.href = apiUrl(`/research/${job.id}/export/pdf`);
    exportDocxBtn.href = apiUrl(`/research/${job.id}/export/docx`);
    exportPptxBtn.href = apiUrl(`/research/${job.id}/export/pptx`);

    // 3. Claims
    const claims = job.claims || [];
    document.getElementById("claims-badge-count").textContent = claims.length;
    document.getElementById("total-claims-count").textContent = claims.length;

    const verifiedCount = claims.filter(c => c.status === "Verified").length;
    const partlyCount = claims.filter(c => c.status === "Partly verified").length;
    const unverifiedCount = claims.filter(c => c.status === "Unverified").length;

    document.getElementById("verified-claims-count").textContent = verifiedCount;
    document.getElementById("partly-claims-count").textContent = partlyCount;
    document.getElementById("unverified-claims-count").textContent = unverifiedCount;

    if (claims.length > 0) {
      document.getElementById("claims-stack-container").innerHTML = claims.map(c => {
        const badgeClass = c.status === "Verified" ? "verified" :
                           c.status === "Partly verified" ? "partly" : "unverified";
        const sourcesText = c.sources && c.sources.length > 0 ? `Citations: [${c.sources.join(", ")}]` : "General finding";

        return `
          <div class="claim-card">
            <div class="claim-top">
              <span class="claim-badge ${badgeClass}">${escapeHtml(c.status)}</span>
              <span class="claim-confidence">Confidence: ${c.confidence}%</span>
            </div>
            <p class="claim-body">${escapeHtml(c.claim)}</p>
            <div class="claim-bottom">
              <span>${sourcesText}</span>
              <span>${escapeHtml(c.note || "")}</span>
            </div>
          </div>
        `;
      }).join("");
    }

    // 4. Analytics & Chart
    const analysis = job.analysis || {};
    const chartDisplay = document.getElementById("chart-display-container");
    const chartSrc = apiUrl(`/research/${job.id}/chart`);
    chartDisplay.innerHTML = `<img src="${chartSrc}" alt="Analytics Chart" class="chart-img" onerror="this.parentElement.innerHTML='<div class=\\'empty-state\\'>No numeric chart generated for this objective.</div>'">`;

    const insights = analysis.insights || [];
    const risks = analysis.risks || [];
    const insightsList = document.getElementById("insights-list");
    const risksList = document.getElementById("risks-list");

    insightsList.innerHTML = insights.length > 0
      ? insights.map(i => `<li>${escapeHtml(i)}</li>`).join("")
      : `<li class="muted-entry">No strategic insights generated.</li>`;

    risksList.innerHTML = risks.length > 0
      ? risks.map(r => `<li>${escapeHtml(r)}</li>`).join("")
      : `<li class="muted-entry">No critical risks identified.</li>`;

    // 5. Sources
    const sources = job.sources || [];
    document.getElementById("sources-badge-count").textContent = sources.length;
    document.getElementById("sources-dedupe-text").textContent = `Deduplication: ${job.duplicates_removed || 0} duplicate or overlapping entries eliminated.`;

    if (sources.length > 0) {
      document.getElementById("sources-grid-container").innerHTML = sources.map(s => `
        <div class="source-item">
          <div>
            <div class="source-badge">Source [${s.id}] &bull; ${escapeHtml(s.domain || "web")}</div>
            <h5 class="source-title">${escapeHtml(s.title || "Document Source")}</h5>
            <p class="source-text">${escapeHtml((s.text || "").slice(0, 220))}...</p>
          </div>
          ${s.url && !s.url.startsWith("attachment://") ? `
            <a href="${escapeHtml(s.url)}" target="_blank" rel="noopener noreferrer" class="source-link">
              Visit Source &rarr;
            </a>` : `<span class="badge badge-mono">Local Attachment</span>`}
        </div>
      `).join("");
    }

    // 6. Load Job Chat History
    loadJobChatHistory(job.id);
  }

  // ----------------- INTERACTIVE CHATBOT -----------------

  async function loadJobChatHistory(jid) {
    try {
      const res = await fetch(apiUrl(`/research/${jid}/chat`));
      if (!res.ok) return;
      const data = await res.json();
      const history = data.history || [];

      if (history.length > 0) {
        chatMessagesContainer.innerHTML = "";
        history.forEach(m => appendChatMessage(m.role, m.content));
      }
    } catch (e) {
      console.error("Failed to load chat history:", e);
    }
  }

  function appendChatMessage(role, content) {
    const isUser = role === "user";
    const msgDiv = document.createElement("div");
    msgDiv.className = `chat-message ${isUser ? "user" : "assistant"}`;

    const avatarDiv = document.createElement("div");
    avatarDiv.className = "message-avatar";
    avatarDiv.textContent = isUser ? "You" : "AI";

    const contentDiv = document.createElement("div");
    contentDiv.className = "message-content";

    if (isUser) {
      contentDiv.textContent = content;
    } else {
      contentDiv.innerHTML = marked.parse(content);
    }

    msgDiv.appendChild(avatarDiv);
    msgDiv.appendChild(contentDiv);
    chatMessagesContainer.appendChild(msgDiv);
    chatMessagesContainer.scrollTop = chatMessagesContainer.scrollHeight;
  }

  function appendTypingIndicator() {
    const typingDiv = document.createElement("div");
    typingDiv.id = "chat-typing-indicator";
    typingDiv.className = "chat-message assistant";
    typingDiv.innerHTML = `
      <div class="message-avatar">AI</div>
      <div class="message-content">
        <span class="typing-dots">Thinking...</span>
      </div>
    `;
    chatMessagesContainer.appendChild(typingDiv);
    chatMessagesContainer.scrollTop = chatMessagesContainer.scrollHeight;
  }

  function removeTypingIndicator() {
    const el = document.getElementById("chat-typing-indicator");
    if (el) el.remove();
  }

  // Chat Form Submit
  chatForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!activeJobId) {
      showToast("Please initiate or select a research job first.");
      return;
    }

    const message = chatInput.value.trim();
    if (!message || isSendingChat) return;

    chatInput.value = "";
    isSendingChat = true;
    chatSendBtn.disabled = true;

    // Render User Message immediately
    appendChatMessage("user", message);
    appendTypingIndicator();

    try {
      const res = await fetch(apiUrl(`/research/${activeJobId}/chat`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message })
      });

      removeTypingIndicator();

      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson.detail || `Chat request failed (${res.status})`);
      }

      const data = await res.json();
      appendChatMessage("assistant", data.reply);
    } catch (err) {
      removeTypingIndicator();
      appendChatMessage("assistant", `*Error:* ${err.message}`);
    } finally {
      isSendingChat = false;
      chatSendBtn.disabled = false;
      chatInput.focus();
    }
  });

  // Quick Chat Chips
  document.querySelectorAll(".chat-chip").forEach(chip => {
    chip.addEventListener("click", () => {
      chatInput.value = chip.dataset.msg;
      chatForm.dispatchEvent(new Event("submit"));
    });
  });

  clearChatViewBtn.addEventListener("click", () => {
    chatMessagesContainer.innerHTML = `
      <div class="chat-message assistant">
        <div class="message-avatar">AI</div>
        <div class="message-content">
          <p>Chat view reset. What would you like to explore regarding this research?</p>
        </div>
      </div>
    `;
  });

  // ----------------- HISTORY DRAWER -----------------

  async function loadHistory() {
    try {
      historyItemsContainer.innerHTML = `<div class="empty-state">Loading history...</div>`;
      const res = await fetch(apiUrl("/research"));
      if (!res.ok) throw new Error("Could not fetch sessions");
      const list = await res.json();

      if (!list || list.length === 0) {
        historyItemsContainer.innerHTML = `<div class="empty-state">No research sessions recorded yet.</div>`;
        return;
      }

      historyItemsContainer.innerHTML = list.map(item => `
        <div class="history-card" data-id="${item.id}">
          <div class="history-card-title">${escapeHtml(item.objective)}</div>
          <div class="history-card-meta">
            <span>#${item.id} ${item.file_name ? `&bull; 📎 ${escapeHtml(item.file_name)}` : ""}</span>
            <span class="badge ${item.status === 'done' ? 'badge-mono' : ''}">${escapeHtml(item.status)}</span>
          </div>
        </div>
      `).join("");

      document.querySelectorAll(".history-card").forEach(el => {
        el.addEventListener("click", () => {
          const jid = el.dataset.id;
          closeDrawer();
          loadPastJob(jid);
        });
      });
    } catch (e) {
      historyItemsContainer.innerHTML = `<div class="empty-state">Error loading history: ${escapeHtml(e.message)}</div>`;
    }
  }

  async function loadPastJob(jid) {
    try {
      showToast(`Loading research #${jid}...`);
      const res = await fetch(apiUrl(`/research/${jid}`));
      if (!res.ok) throw new Error("Job not found");
      const job = await res.json();
      activeJobId = job.id;
      activeJobData = job;
      prepareWorkspace(job.id, job.objective, job.file_name);
      updateUI(job);
    } catch (err) {
      showToast(`Failed to load #${jid}: ${err.message}`);
    }
  }

  function openDrawer() {
    historyDrawer.classList.add("open");
    drawerBackdrop.classList.add("show");
    loadHistory();
  }

  function closeDrawer() {
    historyDrawer.classList.remove("open");
    drawerBackdrop.classList.remove("show");
  }

  historyToggleBtn.addEventListener("click", openDrawer);
  drawerCloseBtn.addEventListener("click", closeDrawer);
  drawerBackdrop.addEventListener("click", closeDrawer);

  function escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  // Initial probe to update status
  checkBackendHealth();
});
