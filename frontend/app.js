document.addEventListener("DOMContentLoaded", () => {
    // DOM Elements
    const topicInput = document.getElementById("topicInput");
    const startResearchBtn = document.getElementById("startResearchBtn");
    const docFileInput = document.getElementById("docFileInput");
    const uploadTriggerBtn = document.getElementById("uploadTriggerBtn");
    const uploadBtnText = document.getElementById("uploadBtnText");
    const docBadge = document.getElementById("docBadge");
    const docBadgeName = document.getElementById("docBadgeName");
    const removeDocBtn = document.getElementById("removeDocBtn");
    const historyList = document.getElementById("historyList");
    const refreshHistoryBtn = document.getElementById("refreshHistoryBtn");
    const newResearchBtn = document.getElementById("newResearchBtn");
    const currentTopicTitle = document.getElementById("currentTopicTitle");
    const sessionStatusChip = document.getElementById("sessionStatusChip");
    const downloadReportBtn = document.getElementById("downloadReportBtn");
    const timelineContainer = document.getElementById("timelineContainer");
    const agentTimeline = document.getElementById("agentTimeline");
    const reportContainer = document.getElementById("reportContainer");
    const reportBody = document.getElementById("reportBody");
    const copyReportBtn = document.getElementById("copyReportBtn");
    const tagBtns = document.querySelectorAll(".tag-btn");

    // State Variables
    let activeDocSessionId = null;
    let currentSessionId = null;
    let rawReportMarkdown = "";

    // Configure marked options
    if (window.marked) {
        marked.setOptions({
            gfm: true,
            breaks: true,
            headerIds: true
        });
    }

    // --- Quick Tags ---
    tagBtns.forEach(btn => {
        btn.addEventListener("click", () => {
            topicInput.value = btn.innerText;
            topicInput.focus();
        });
    });

    // --- Document Upload ---
    uploadTriggerBtn.addEventListener("click", () => docFileInput.click());

    docFileInput.addEventListener("change", async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        uploadBtnText.innerText = "Processing...";
        uploadTriggerBtn.disabled = true;

        const formData = new FormData();
        formData.append("file", file);

        try {
            const resp = await fetch("/api/upload-document", {
                method: "POST",
                body: formData
            });

            const data = await resp.json();
            if (resp.ok && data.status === "success") {
                activeDocSessionId = data.doc_session_id;
                docBadgeName.innerText = file.name;
                docBadge.classList.remove("hidden");
                uploadTriggerBtn.classList.add("hidden");
            } else {
                alert("Upload failed: " + (data.detail || "Unknown error"));
            }
        } catch (err) {
            alert("Error uploading file: " + err.message);
        } finally {
            uploadBtnText.innerText = "Upload Document";
            uploadTriggerBtn.disabled = false;
        }
    });

    removeDocBtn.addEventListener("click", () => {
        activeDocSessionId = null;
        docFileInput.value = "";
        docBadge.classList.add("hidden");
        uploadTriggerBtn.classList.remove("hidden");
    });

    // --- Research Execution & Streaming ---
    startResearchBtn.addEventListener("click", () => initiateResearch());
    topicInput.addEventListener("keypress", (e) => {
        if (e.key === "Enter") initiateResearch();
    });

    async function initiateResearch() {
        const topic = topicInput.value.trim();
        if (!topic) {
            alert("Please enter a research topic.");
            return;
        }

        // Reset UI State
        startResearchBtn.disabled = true;
        currentTopicTitle.innerText = topic;
        sessionStatusChip.innerText = "Running...";
        sessionStatusChip.className = "status-chip running";
        downloadReportBtn.classList.add("hidden");
        agentTimeline.innerHTML = "";
        reportBody.innerHTML = "<p><i>Synthesizing research report...</i></p>";
        timelineContainer.classList.remove("hidden");
        reportContainer.classList.remove("hidden");
        rawReportMarkdown = "";

        addTimelineItem("planner", "Planner Node", "Analyzing research topic and breaking down into sub-questions...", "active");

        try {
            const response = await fetch("/api/research/stream", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    topic: topic,
                    doc_session_id: activeDocSessionId
                })
            });

            if (!response.ok) {
                throw new Error(`Server returned HTTP ${response.status}`);
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder("utf-8");
            let buffer = "";

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split("\n\n");
                buffer = lines.pop() || "";

                for (const chunk of lines) {
                    parseSSEEvent(chunk);
                }
            }

        } catch (err) {
            console.error("Streaming error:", err);
            sessionStatusChip.innerText = "Error";
            sessionStatusChip.className = "status-chip";
            addTimelineItem("error", "System Error", err.message, "completed");
        } finally {
            startResearchBtn.disabled = false;
        }
    }

    function parseSSEEvent(rawChunk) {
        let eventType = "message";
        let eventData = "";

        const lines = rawChunk.split("\n");
        for (const line of lines) {
            if (line.startsWith("event:")) {
                eventType = line.replace("event:", "").trim();
            } else if (line.startsWith("data:")) {
                eventData = line.replace("data:", "").trim();
            }
        }

        if (!eventData) return;

        try {
            const payload = JSON.parse(eventData);

            if (eventType === "sub_questions_planned") {
                updateTimelineItem("planner", "Planned Sub-Questions:", "completed");
                const listHtml = payload.sub_questions.map(q => `<li>${q}</li>`).join("");
                appendTimelineContent("planner", `<ul>${listHtml}</ul>`);
                addTimelineItem("researcher", "Researcher Node", "Selecting tools and gathering evidence...", "active");

            } else if (eventType === "tool_activity") {
                const toolChipHtml = `
                    <div style="margin-top: 0.5rem;">
                        <strong>Sub-question:</strong> ${payload.sub_question}<br>
                        <span class="tool-chip"><i class="fa-solid fa-wrench"></i> ${payload.tool_used}</span>
                        <div style="font-size: 0.8rem; color: var(--text-secondary); margin-top: 0.2rem;">${payload.tool_reason}</div>
                    </div>
                `;
                appendTimelineContent("researcher", toolChipHtml);

            } else if (eventType === "critic_review") {
                updateTimelineItem("researcher", "Research gathered.", "completed");
                const isSuff = payload.is_sufficient;
                const statusText = isSuff ? "Approved (Sufficient)" : `Retry Needed (Loop ${payload.retry_count}/2)`;
                addTimelineItem(
                    "critic",
                    `Critic Node — ${statusText}`,
                    `Feedback: ${payload.feedback}`,
                    isSuff ? "completed" : "active"
                );
                if (isSuff) {
                    addTimelineItem("writer", "Writer Node", "Synthesizing full markdown report...", "active");
                }

            } else if (eventType === "report_chunk") {
                updateTimelineItem("writer", "Report synthesis streaming...", "active");
                rawReportMarkdown += payload.chunk;
                if (window.marked) {
                    reportBody.innerHTML = marked.parse(rawReportMarkdown);
                } else {
                    reportBody.innerText = rawReportMarkdown;
                }

            } else if (eventType === "complete") {
                currentSessionId = payload.session_id;
                sessionStatusChip.innerText = "Completed";
                sessionStatusChip.className = "status-chip completed";
                updateTimelineItem("writer", "Report saved successfully.", "completed");
                downloadReportBtn.classList.remove("hidden");
                fetchHistory();

            } else if (eventType === "error") {
                sessionStatusChip.innerText = "Failed";
                addTimelineItem("error", "Error", payload.message, "completed");
            }

        } catch (e) {
            console.warn("Could not parse SSE payload:", e, eventData);
        }
    }

    // --- Timeline Helpers ---
    function addTimelineItem(id, title, initialMessage, stateClass) {
        let existing = document.getElementById(`tl-${id}`);
        if (!existing) {
            const item = document.createElement("div");
            item.id = `tl-${id}`;
            item.className = `timeline-item ${stateClass}`;
            item.innerHTML = `
                <div class="timeline-dot"></div>
                <div class="timeline-header">
                    <span class="timeline-node-title">${title}</span>
                </div>
                <div class="timeline-body" id="tl-body-${id}">${initialMessage}</div>
            `;
            agentTimeline.appendChild(item);
        } else {
            existing.className = `timeline-item ${stateClass}`;
            document.getElementById(`tl-body-${id}`).innerHTML = initialMessage;
        }
    }

    function updateTimelineItem(id, message, stateClass) {
        const item = document.getElementById(`tl-${id}`);
        if (item) {
            item.className = `timeline-item ${stateClass}`;
            const body = document.getElementById(`tl-body-${id}`);
            if (body && message) body.innerHTML = message;
        }
    }

    function appendTimelineContent(id, htmlContent) {
        const body = document.getElementById(`tl-body-${id}`);
        if (body) {
            body.innerHTML += htmlContent;
        }
    }

    // --- Report Export & Copy ---
    downloadReportBtn.addEventListener("click", async () => {
        if (!currentSessionId) return;
        try {
            const resp = await fetch(`/api/reports/${currentSessionId}/download`);
            const data = await resp.json();
            if (data.download_url) {
                window.open(data.download_url, "_blank");
            } else {
                window.location.href = `/api/reports/${currentSessionId}/download`;
            }
        } catch (err) {
            window.location.href = `/api/reports/${currentSessionId}/download`;
        }
    });

    copyReportBtn.addEventListener("click", () => {
        if (!rawReportMarkdown) return;
        navigator.clipboard.writeText(rawReportMarkdown).then(() => {
            const orig = copyReportBtn.innerHTML;
            copyReportBtn.innerHTML = `<i class="fa-solid fa-check"></i> Copied!`;
            setTimeout(() => copyReportBtn.innerHTML = orig, 2000);
        });
    });

    // --- History Sidebar ---
    refreshHistoryBtn.addEventListener("click", fetchHistory);
    newResearchBtn.addEventListener("click", resetToNewResearch);

    function resetToNewResearch() {
        topicInput.value = "";
        currentSessionId = null;
        rawReportMarkdown = "";
        currentTopicTitle.innerText = "Autonomous Multi-Agent Studio";
        sessionStatusChip.innerText = "Idle";
        sessionStatusChip.className = "status-chip";
        downloadReportBtn.classList.add("hidden");
        timelineContainer.classList.add("hidden");
        reportContainer.classList.add("hidden");
        agentTimeline.innerHTML = "";
        reportBody.innerHTML = "";
        topicInput.focus();
    }

    async function fetchHistory() {
        try {
            const resp = await fetch("/api/sessions");
            const data = await resp.json();
            if (resp.ok && data.sessions) {
                renderHistoryList(data.sessions);
            }
        } catch (err) {
            console.error("Failed to load history:", err);
        }
    }

    function renderHistoryList(sessions) {
        if (!sessions || sessions.length === 0) {
            historyList.innerHTML = `<div class="empty-history">No past sessions found</div>`;
            return;
        }

        historyList.innerHTML = sessions.map(s => {
            const dateStr = s.created_at ? new Date(s.created_at).toLocaleDateString() : "";
            return `
                <div class="history-item" data-session-id="${s.session_id}">
                    <div class="history-topic">${s.original_topic || "Untitled Session"}</div>
                    <div class="history-date">${dateStr} • ${s.sub_questions ? s.sub_questions.length : 0} questions</div>
                </div>
            `;
        }).join("");

        document.querySelectorAll(".history-item").forEach(item => {
            item.addEventListener("click", () => {
                const sid = item.getAttribute("data-session-id");
                loadPastSession(sid);
            });
        });
    }

    async function loadPastSession(sessionId) {
        try {
            const resp = await fetch(`/api/sessions/${sessionId}`);
            const data = await resp.json();
            if (resp.ok && data.session) {
                const session = data.session;
                currentSessionId = session.session_id;
                rawReportMarkdown = session.final_report || "";
                currentTopicTitle.innerText = session.original_topic || "Saved Research Report";
                sessionStatusChip.innerText = "Saved Report";
                sessionStatusChip.className = "status-chip completed";
                downloadReportBtn.classList.remove("hidden");
                
                timelineContainer.classList.add("hidden");
                reportContainer.classList.remove("hidden");

                if (window.marked) {
                    reportBody.innerHTML = marked.parse(rawReportMarkdown);
                } else {
                    reportBody.innerText = rawReportMarkdown;
                }
            }
        } catch (err) {
            alert("Could not load session: " + err.message);
        }
    }

    // Initial Load
    fetchHistory();
});
