/* ==========================================================================
   FRONTLINE Client Logic & API Orchestration
   ========================================================================== */

document.addEventListener("DOMContentLoaded", () => {
    // API Endpoints
    const API_MESSAGES = "/api/messages";
    const API_TRIAGE = "/api/triage";
    const API_TRIAGE_ALL = "/api/triage-all";
    const API_EVALUATE = "/api/evaluate";

    // App State Caches
    let presetMessages = [];
    let triagedResults = [];

    // DOM Elements
    const presetMessagesList = document.getElementById("preset-messages-list");
    const playgroundForm = document.getElementById("playground-form");
    const messageInput = document.getElementById("message-input");
    const formatInput = document.getElementById("format-input");
    const btnSubmitTriage = document.getElementById("btn-submit-triage");
    
    // Playground Results
    const playgroundResult = document.getElementById("playground-result");
    const resCategory = document.getElementById("res-category");
    const resPriority = document.getElementById("res-priority");
    const resNeedsHuman = document.getElementById("res-needs-human");
    const resLang = document.getElementById("res-lang");
    const resConfidence = document.getElementById("res-confidence");
    const resSummary = document.getElementById("res-summary");
    const resAction = document.getElementById("res-action");
    const resRawJson = document.getElementById("res-raw-json");

    // Action Buttons
    const btnTriageAll = document.getElementById("btn-triage-all");
    const btnRunEval = document.getElementById("btn-run-eval");

    // Evaluation scoreboard
    const evalMetricsContainer = document.getElementById("eval-metrics-container");
    const evalPlaceholderText = document.getElementById("eval-placeholder-text");
    const accCategory = document.getElementById("accuracy-category");
    const accPriority = document.getElementById("accuracy-priority");
    const accEscalation = document.getElementById("accuracy-escalation");
    const barCategory = document.getElementById("bar-category");
    const barPriority = document.getElementById("bar-priority");
    const barEscalation = document.getElementById("bar-escalation");
    const statLatency = document.getElementById("stat-latency");
    const statTokens = document.getElementById("stat-tokens");
    const statCost = document.getElementById("stat-cost");

    // Dashboard Table
    const dashboardTbody = document.getElementById("dashboard-tbody");
    const dashboardSearch = document.getElementById("dashboard-search");
    const filterCategory = document.getElementById("filter-category");
    const filterHuman = document.getElementById("filter-human");

    // Details Drawer
    const detailsDrawerOverlay = document.getElementById("details-drawer-overlay");
    const btnCloseDrawer = document.getElementById("btn-close-drawer");
    const detailsDrawerBody = document.getElementById("details-drawer-body");

    // ── Initial Setup ────────────────────────────────────────────────────────
    loadPresetMessages();

    // Hide evaluation scores until evaluated
    evalMetricsContainer.style.display = "none";

    // ── Event Listeners ──────────────────────────────────────────────────────
    playgroundForm.addEventListener("submit", handlePlaygroundSubmit);
    btnTriageAll.addEventListener("click", handleBatchTriage);
    btnRunEval.addEventListener("click", handleRunEvaluation);
    
    // Real-time filtering
    dashboardSearch.addEventListener("input", renderFilteredTable);
    filterCategory.addEventListener("change", renderFilteredTable);
    filterHuman.addEventListener("change", renderFilteredTable);

    // Close Drawer
    btnCloseDrawer.addEventListener("click", closeDrawer);
    detailsDrawerOverlay.addEventListener("click", (e) => {
        if (e.target === detailsDrawerOverlay) closeDrawer();
    });

    // ── Preset Messages Loader ───────────────────────────────────────────────
    async function loadPresetMessages() {
        try {
            const res = await fetch(API_MESSAGES);
            if (!res.ok) throw new Error("Failed to load preset messages");
            presetMessages = await res.json();
            
            presetMessagesList.innerHTML = "";
            presetMessages.forEach(msg => {
                const li = document.createElement("li");
                li.className = "message-item";
                li.innerHTML = `
                    <div class="message-item-header">
                        <span class="message-id">${msg.id}</span>
                        <span class="message-format">${msg.format || 'text'}</span>
                    </div>
                    <div class="message-preview">${escapeHtml(msg.raw_input || '')}</div>
                `;
                li.addEventListener("click", () => {
                    // Update active classes
                    document.querySelectorAll(".message-item").forEach(item => item.classList.remove("active"));
                    li.classList.add("active");
                    
                    // Autofill playground form
                    messageInput.value = msg.raw_input;
                    formatInput.value = msg.format || "text";
                    messageInput.focus();
                });
                presetMessagesList.appendChild(li);
            });
        } catch (err) {
            presetMessagesList.innerHTML = `<li class="loading-item text-danger">⚠️ Error: ${err.message}</li>`;
        }
    }

    // ── Triage Playground Submission ─────────────────────────────────────────
    async function handlePlaygroundSubmit(e) {
        e.preventDefault();
        const text = messageInput.value.trim();
        const format = formatInput.value;

        if (!text) return;

        // Toggle Loading Button State
        btnSubmitTriage.disabled = true;
        btnSubmitTriage.textContent = "Analyzing...";

        try {
            const res = await fetch(API_TRIAGE, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ text, format })
            });

            if (!res.ok) throw new Error("Triage pipeline failed");
            const result = await res.json();

            // Populate Result Block
            resCategory.textContent = result.category.toUpperCase();
            resCategory.className = `badge cat-${result.category.toLowerCase()}`;
            
            resPriority.textContent = result.priority;
            resPriority.className = `badge pri-${result.priority.toLowerCase()}`;

            resNeedsHuman.textContent = result.needs_human ? "⚠️ Needs Human" : "✓ Auto-Resolved";
            resNeedsHuman.className = `badge ${result.needs_human ? 'human-yes' : 'human-no'}`;

            resLang.textContent = result.language_detected;
            resConfidence.textContent = `${Math.round(result.confidence * 100)}%`;
            resSummary.textContent = result.summary;
            resAction.textContent = result.suggested_action;
            resRawJson.textContent = JSON.stringify(result, null, 2);

            // ── API Quota / Rate Limit Warning ────────────────────────────────
            const existingWarning = document.getElementById('api-rate-limit-banner');
            if (existingWarning) existingWarning.remove();

            if (result.confidence === 0.0) {
                const banner = document.createElement('div');
                banner.id = 'api-rate-limit-banner';
                banner.style.cssText = [
                    'background: rgba(244, 63, 94, 0.12)',
                    'border: 1px solid rgba(244, 63, 94, 0.4)',
                    'border-radius: 8px',
                    'padding: 12px 16px',
                    'margin-top: 12px',
                    'font-size: 0.82rem',
                    'color: #f87171',
                    'display: flex',
                    'gap: 10px',
                    'align-items: flex-start'
                ].join(';');
                banner.innerHTML = `
                    <span style="font-size:1.1rem;line-height:1">&#x26A0;&#xFE0F;</span>
                    <div>
                        <strong>Gemini API Quota Exhausted</strong> &mdash;
                        The triage engine returned a safe fallback (confidence = 0%). 
                        This happens when the free-tier daily limit (1,500 req/day) is reached.
                        <br><strong>Fix:</strong> Get a new API key at 
                        <a href="https://aistudio.google.com/app/apikey" target="_blank" 
                           style="color:#60a5fa">aistudio.google.com</a>, 
                        update <code>.env</code>, and restart the server.
                    </div>
                `;
                playgroundResult.appendChild(banner);
            }

            // Display Results
            playgroundResult.classList.remove("hidden");
            playgroundResult.scrollIntoView({ behavior: "smooth", block: "nearest" });

            // Dynamically add to dashboard session if not exists
            const tempResult = { ...result, id: "playground_test", raw_input: text, format };
            // Prepend new results
            triagedResults = [tempResult, ...triagedResults.filter(r => r.id !== "playground_test")];
            renderFilteredTable();
        } catch (err) {
            alert(`Triage Error: ${err.message}`);
        } finally {
            btnSubmitTriage.disabled = false;
            btnSubmitTriage.textContent = "Analyze Message";
        }
    }

    // ── Batch Triage All Messages ────────────────────────────────────────────
    async function handleBatchTriage() {
        btnTriageAll.disabled = true;
        btnTriageAll.textContent = "Processing Batch...";
        
        // Show loading state in table
        dashboardTbody.innerHTML = `
            <tr>
                <td colspan="7" class="text-center" style="padding: 40px 0;">
                    <div style="display: flex; flex-direction: column; align-items: center; gap: 8px;">
                        <span class="loading-spinner">⚙️</span>
                        <p>Triage engine is processing all 40 messages sequentially...</p>
                    </div>
                </td>
            </tr>
        `;

        try {
            const res = await fetch(API_TRIAGE_ALL);
            if (!res.ok) throw new Error("Batch processing failed");
            const data = await res.json();

            // Bind raw inputs back for details rendering from preset list
            triagedResults = data.map(result => {
                const match = presetMessages.find(m => m.id === result.id);
                return {
                    ...result,
                    raw_input: match ? match.raw_input : result._raw_input || "",
                    format: match ? match.format : result.input_format_detected || "text"
                };
            });

            renderFilteredTable();
        } catch (err) {
            dashboardTbody.innerHTML = `
                <tr>
                    <td colspan="7" class="text-center text-danger" style="padding: 40px 0;">
                        ⚠️ Error triaging dataset: ${err.message}
                    </td>
                </tr>
            `;
        } finally {
            btnTriageAll.disabled = false;
            btnTriageAll.textContent = "🚀 Run All (Batch)";
        }
    }

    // ── Run Evaluation Metrics ────────────────────────────────────────────────
    async function handleRunEvaluation() {
        btnRunEval.disabled = true;
        btnRunEval.textContent = "Scoring metrics...";

        try {
            const res = await fetch(API_EVALUATE);
            if (!res.ok) throw new Error("Evaluation failed");
            const report = await res.json();

            // Hide placeholder, display dashboard metrics
            evalPlaceholderText.style.display = "none";
            evalMetricsContainer.style.display = "flex";

            // Update Metric Values
            accCategory.textContent = `${report.summary.category_accuracy_pct}%`;
            accPriority.textContent = `${report.summary.priority_accuracy_pct}%`;
            accEscalation.textContent = `${report.summary.needs_human_accuracy_pct}%`;

            // Update Progress Bar widths
            barCategory.style.width = `${report.summary.category_accuracy_pct}%`;
            barPriority.style.width = `${report.summary.priority_accuracy_pct}%`;
            barEscalation.style.width = `${report.summary.needs_human_accuracy_pct}%`;

            // Populate Aggregate Stats
            statLatency.textContent = `${report.performance.avg_latency_s.toFixed(2)}s`;
            statTokens.textContent = `${Math.round(report.performance.avg_input_tokens + report.performance.avg_output_tokens)}`;
            statCost.textContent = `$${report.performance.avg_cost_usd.toFixed(4)}`;

        } catch (err) {
            alert(`Evaluation Error: ${err.message}`);
        } finally {
            btnRunEval.disabled = false;
            btnRunEval.textContent = "📈 Run Evaluation";
        }
    }

    // ── Render Triage Table with Client-Side Filters ──────────────────────────
    function renderFilteredTable() {
        const query = dashboardSearch.value.toLowerCase().trim();
        const catFilter = filterCategory.value;
        const humanFilter = filterHuman.value;

        // Filter the cached results list
        const filtered = triagedResults.filter(item => {
            // Search query matches ID, Category, Summary, or Raw input
            const matchesQuery = !query || 
                item.id.toLowerCase().includes(query) ||
                item.category.toLowerCase().includes(query) ||
                item.summary.toLowerCase().includes(query) ||
                (item.raw_input && item.raw_input.toLowerCase().includes(query));

            // Category select matches
            const matchesCat = catFilter === "all" || item.category.toLowerCase() === catFilter.toLowerCase();

            // Needs human select matches
            const matchesHuman = humanFilter === "all" ||
                (humanFilter === "human" && item.needs_human) ||
                (humanFilter === "auto" && !item.needs_human);

            return matchesQuery && matchesCat && matchesHuman;
        });

        if (filtered.length === 0) {
            dashboardTbody.innerHTML = `
                <tr class="empty-row-placeholder">
                    <td colspan="7">
                        <div class="table-empty-state">
                            <span>📋</span>
                            <p>${triagedResults.length === 0 ? 'No messages triaged in this session yet. Run batch triage above or test via the playground.' : 'No matching results found. Modify search parameters.'}</p>
                        </div>
                    </td>
                </tr>
            `;
            return;
        }

        dashboardTbody.innerHTML = "";
        filtered.forEach(item => {
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td style="font-family: monospace; font-weight: 600; color: var(--accent-blue);">${item.id}</td>
                <td><span class="cat-badge cat-${item.category.toLowerCase()}">${item.category}</span></td>
                <td><span class="pri-pill pri-${item.priority.toLowerCase()}">${item.priority}</span></td>
                <td class="human-indicator ${item.needs_human ? 'human-yes' : 'human-no'}">
                    ${item.needs_human ? '⚠️ YES' : '✓ NO'}
                </td>
                <td style="font-weight: 600;">${Math.round(item.confidence * 100)}%</td>
                <td class="lang-cell">${item.language_detected}</td>
                <td class="summary-cell" title="${escapeHtml(item.summary)}">${escapeHtml(item.summary)}</td>
            `;

            // Open analytics drawer on row click
            tr.addEventListener("click", () => openDrawer(item));
            dashboardTbody.appendChild(tr);
        });
    }

    // ── Details Drawer Controls ──────────────────────────────────────────────
    function openDrawer(item) {
        // Build analytical visual components inside the drawer
        const meta = item._meta || {};
        
        detailsDrawerBody.innerHTML = `
            <div class="detail-section">
                <h4>Message ID & Format</h4>
                <div class="detail-grid">
                    <div class="detail-meta-item">
                        <div class="detail-meta-label">ID</div>
                        <div class="detail-meta-value text-accent">${item.id}</div>
                    </div>
                    <div class="detail-meta-item">
                        <div class="detail-meta-label">Input Format</div>
                        <div class="detail-meta-value" style="text-transform: uppercase;">${item.format || item.input_format_detected || 'text'}</div>
                    </div>
                </div>
            </div>

            <div class="detail-section">
                <h4>Raw Message Content</h4>
                <div class="detail-text-box">${escapeHtml(item.raw_input || '[Content not cached]')}</div>
            </div>

            <div class="detail-section">
                <h4>Classification Output</h4>
                <div class="detail-grid">
                    <div class="detail-meta-item">
                        <div class="detail-meta-label">Category</div>
                        <div class="detail-meta-value"><span class="cat-badge cat-${item.category.toLowerCase()}">${item.category}</span></div>
                    </div>
                    <div class="detail-meta-item">
                        <div class="detail-meta-label">Priority</div>
                        <div class="detail-meta-value"><span class="pri-pill pri-${item.priority.toLowerCase()}">${item.priority}</span></div>
                    </div>
                    <div class="detail-meta-item">
                        <div class="detail-meta-label">Confidence</div>
                        <div class="detail-meta-value">${Math.round(item.confidence * 100)}%</div>
                    </div>
                    <div class="detail-meta-item">
                        <div class="detail-meta-label">Escalation State</div>
                        <div class="detail-meta-value ${item.needs_human ? 'human-yes' : 'human-no'}">
                            ${item.needs_human ? '⚠️ Needs Human' : '✓ Auto-Resolved'}
                        </div>
                    </div>
                </div>
            </div>

            <div class="detail-section">
                <h4>Issue Summary</h4>
                <div class="detail-text-box" style="font-style: italic;">"${escapeHtml(item.summary)}"</div>
            </div>

            <div class="detail-section">
                <h4>Suggested Support Action</h4>
                <div class="detail-text-box" style="border-color: var(--accent-blue-glow); background-color: rgba(96, 165, 250, 0.01);">${escapeHtml(item.suggested_action)}</div>
            </div>

            ${Object.keys(meta).length > 0 ? `
            <div class="detail-section">
                <h4>Execution Metadata</h4>
                <div class="detail-grid" style="grid-template-columns: repeat(3, 1fr); font-size: 0.8rem;">
                    <div class="detail-meta-item">
                        <div class="detail-meta-label">Model</div>
                        <div class="detail-meta-value" style="font-size: 0.75rem;">${meta.model || 'Gemini'}</div>
                    </div>
                    <div class="detail-meta-item">
                        <div class="detail-meta-label">Latency</div>
                        <div class="detail-meta-value">${meta.latency_s}s</div>
                    </div>
                    <div class="detail-meta-item">
                        <div class="detail-meta-label">Tokens</div>
                        <div class="detail-meta-value" style="font-size: 0.75rem;">${meta.input_tokens}in / ${meta.output_tokens}out</div>
                    </div>
                </div>
            </div>
            ` : ''}
        `;

        // Slide Drawer in
        detailsDrawerOverlay.classList.remove("hidden");
    }

    function closeDrawer() {
        detailsDrawerOverlay.classList.add("hidden");
    }

    // ── Helper: Escape HTML strings ──────────────────────────────────────────
    function escapeHtml(str) {
        return str
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }
});
