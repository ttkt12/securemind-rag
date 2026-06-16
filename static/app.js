"use strict";

/* SecureMind RAG — premium web client.
 * Backend contract is unchanged: POST /chat and GET /documents/count, with an
 * optional X-App-Access-Token header. Rendering is XSS-safe (textContent / DOM
 * nodes only) and never exposes debug metadata, prompts, chunks, or tokens. */

const els = {
  shell: document.getElementById("app-shell"),
  sidebar: document.getElementById("sidebar"),
  sidebarToggle: document.getElementById("sidebar-toggle"),
  sidebarScrim: document.getElementById("sidebar-scrim"),
  documentCount: document.getElementById("document-count"),
  corpusNote: document.getElementById("corpus-note"),
  themeToggle: document.getElementById("theme-toggle"),
  introScreen: document.getElementById("intro-screen"),
  introEnter: document.getElementById("intro-enter"),
  introStats: document.getElementById("intro-stats"),
  introTotal: document.getElementById("intro-total"),
  newChat: document.getElementById("new-chat"),
  clearSessions: document.getElementById("clear-sessions"),
  sessionList: document.getElementById("session-list"),
  sessionCount: document.getElementById("session-count"),
  accessToggle: document.getElementById("access-toggle"),
  accessState: document.getElementById("access-state"),
  accessFields: document.getElementById("access-fields"),
  accessToken: document.getElementById("access-token"),
  saveToken: document.getElementById("save-token"),
  clearToken: document.getElementById("clear-token"),
  messages: document.getElementById("messages"),
  form: document.getElementById("chat-form"),
  input: document.getElementById("question"),
  send: document.getElementById("send"),
  statusPill: document.getElementById("status-pill"),
  errorBanner: document.getElementById("error-banner"),
  errorText: document.getElementById("error-text"),
  errorRetry: document.getElementById("error-retry"),
};

const STORAGE_KEY = "securemind-rag:sessions:v2";
const TOKEN_KEY = "securemind-rag:access-token";
const MAX_HISTORY = 10;
const MAX_SESSIONS = 40;
const SAFE_ERROR = "Không lấy được câu trả lời lúc này. Vui lòng thử lại.";
const DOC_CODE_RE = /\b[A-Z]{2,5}(?:-[A-Z]{2,5}){0,2}-\d{1,4}\b/g;

let sessions = [];
let activeSessionId = "";
let lastQuestion = "";
let sending = false;

/* ----------------------------------------------------------- utilities */
function appHeaders(extra = {}) {
  const headers = { ...extra };
  const token = sessionStorage.getItem(TOKEN_KEY);
  if (token) {
    headers["X-App-Access-Token"] = token;
  }
  return headers;
}

function makeId() {
  if (window.crypto && window.crypto.randomUUID) {
    return window.crypto.randomUUID();
  }
  return `s-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function nowIso() {
  return new Date().toISOString();
}

function formatTime(iso) {
  try {
    return new Intl.DateTimeFormat(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(iso));
  } catch (_error) {
    return "";
  }
}

function titleFromQuestion(question) {
  const title = question.replace(/\s+/g, " ").trim();
  if (!title) return "New chat";
  return title.length > 46 ? `${title.slice(0, 43)}…` : title;
}

/* ----------------------------------------------------------- sessions */
function createSession(title = "New chat") {
  const timestamp = nowIso();
  return { session_id: makeId(), title, created_at: timestamp, updated_at: timestamp, messages: [] };
}

function loadSessions() {
  try {
    const payload = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
    if (Array.isArray(payload.sessions)) {
      sessions = payload.sessions.filter((s) => s && Array.isArray(s.messages));
      activeSessionId = payload.activeSessionId || "";
    }
  } catch (_error) {
    sessions = [];
    activeSessionId = "";
  }
  if (!sessions.length) {
    const session = createSession();
    sessions = [session];
    activeSessionId = session.session_id;
  }
  if (!sessions.some((s) => s.session_id === activeSessionId)) {
    activeSessionId = sessions[0].session_id;
  }
}

function saveSessions() {
  localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({ activeSessionId, sessions: sessions.slice(0, MAX_SESSIONS) })
  );
}

function activeSession() {
  return sessions.find((s) => s.session_id === activeSessionId) || sessions[0];
}

function historyForRequest(session) {
  return session.messages
    .filter((m) => (m.role === "user" || m.role === "assistant") && m.status !== "error")
    .slice(-MAX_HISTORY)
    .map((m) => ({ role: m.role, content: m.content }));
}

/* ----------------------------------------------------------- rendering */
function appendCodes(parent, text) {
  const value = String(text);
  let last = 0;
  for (const match of value.matchAll(DOC_CODE_RE)) {
    const index = match.index;
    if (index > last) {
      parent.appendChild(document.createTextNode(value.slice(last, index)));
    }
    const code = document.createElement("code");
    code.className = "doc-code";
    code.textContent = match[0];
    parent.appendChild(code);
    last = index + match[0].length;
  }
  if (last < value.length) {
    parent.appendChild(document.createTextNode(value.slice(last)));
  }
}

function appendInline(parent, text) {
  const parts = String(text).split(/(\*\*[^*]+\*\*)/g);
  for (const part of parts) {
    if (!part) continue;
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      const strong = document.createElement("strong");
      appendCodes(strong, part.slice(2, -2));
      parent.appendChild(strong);
    } else {
      appendCodes(parent, part);
    }
  }
}

function createFormattedAnswer(text) {
  const block = document.createElement("div");
  block.className = "message-text";
  const lines = String(text || "").replace(/\r\n?/g, "\n").split("\n");

  let paragraph = [];
  let list = null;
  let listType = null;

  const flushParagraph = () => {
    if (paragraph.length) {
      const p = document.createElement("p");
      appendInline(p, paragraph.join(" "));
      block.appendChild(p);
      paragraph = [];
    }
  };
  const closeList = () => {
    list = null;
    listType = null;
  };

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) {
      flushParagraph();
      closeList();
      continue;
    }
    const ordered = rawLine.match(/^\s*\d+[.)]\s+(.+)$/);
    const unordered = rawLine.match(/^\s*[-*•]\s+(.+)$/);
    if (ordered || unordered) {
      flushParagraph();
      const type = ordered ? "ol" : "ul";
      if (!list || listType !== type) {
        list = document.createElement(type);
        listType = type;
        block.appendChild(list);
      }
      const li = document.createElement("li");
      appendInline(li, (ordered ? ordered[1] : unordered[1]).trim());
      list.appendChild(li);
      continue;
    }
    closeList();
    paragraph.push(line);
  }
  flushParagraph();

  if (!block.childNodes.length) {
    block.textContent = "Không có nội dung trả lời.";
  }
  return block;
}

function extractDocumentCode(text) {
  const match = String(text || "").match(/\b[A-Z]{2,5}(?:-[A-Z]{2,5}){0,2}-\d{1,4}\b/);
  return match ? match[0].toUpperCase() : "";
}

function normalizeSource(source) {
  if (source && typeof source === "object") {
    const filename = source.filename ? String(source.filename).split(/[\\/]/).pop() : "";
    const page = Number.isInteger(source.page) ? source.page : null;
    const label = source.label ? String(source.label) : filename;
    const score = typeof source.score === "number" ? source.score : null;
    return {
      filename: filename || label || "Tài liệu",
      page,
      label: label || filename || "Tài liệu",
      code: source.code || extractDocumentCode(`${filename} ${label}`),
      score,
    };
  }
  const label = String(source || "Tài liệu");
  return {
    filename: label.split(/[\\/]/).pop(),
    page: null,
    label,
    code: extractDocumentCode(label),
    score: null,
  };
}

function uniqueSources(list) {
  const seen = new Set();
  const out = [];
  (Array.isArray(list) ? list : []).map(normalizeSource).forEach((source) => {
    const key = `${source.filename}|${source.page ?? ""}|${source.code}`;
    if (seen.has(key)) return;
    seen.add(key);
    out.push(source);
  });
  return out;
}

function appendSources(bubble, sources) {
  const items = uniqueSources(sources);
  if (!items.length) return;

  const wrap = document.createElement("section");
  wrap.className = "sources";
  wrap.setAttribute("aria-label", "Nguồn tài liệu");

  const title = document.createElement("p");
  title.className = "sources-title";
  title.textContent = items.length > 1 ? `Nguồn (${items.length})` : "Nguồn";
  wrap.appendChild(title);

  const list = document.createElement("div");
  list.className = "source-list";
  wrap.appendChild(list);

  let expanded = false;
  const render = () => {
    list.replaceChildren();
    const visible = expanded ? items : items.slice(0, 3);
    visible.forEach((source, i) => {
      const card = document.createElement("div");
      card.className = "source-card";
      card.tabIndex = 0;
      card.setAttribute("role", "group");

      const idx = document.createElement("span");
      idx.className = "source-index";
      idx.textContent = String(i + 1);

      const body = document.createElement("div");
      body.className = "source-body";

      const name = document.createElement("div");
      name.className = "source-name";
      name.textContent = source.filename || source.label;
      body.appendChild(name);

      const meta = document.createElement("div");
      meta.className = "source-meta";
      if (source.code) {
        const code = document.createElement("code");
        code.className = "doc-code";
        code.textContent = source.code;
        meta.appendChild(code);
      }
      if (source.page) {
        const page = document.createElement("span");
        page.textContent = `trang ${source.page}`;
        meta.appendChild(page);
      }
      if (typeof source.score === "number") {
        const score = document.createElement("span");
        score.textContent = `score ${source.score.toFixed(2)}`;
        meta.appendChild(score);
      }
      if (meta.childNodes.length) body.appendChild(meta);

      const labelBits = [source.filename || source.label, source.code, source.page ? `trang ${source.page}` : ""].filter(Boolean);
      card.setAttribute("aria-label", `Nguồn: ${labelBits.join(", ")}`);
      card.append(idx, body);
      list.appendChild(card);
    });
  };
  render();

  if (items.length > 3) {
    const toggle = document.createElement("button");
    toggle.className = "source-toggle";
    toggle.type = "button";
    const setLabel = () => {
      toggle.textContent = expanded ? "Thu gọn nguồn" : `Xem thêm ${items.length - 3} nguồn`;
    };
    setLabel();
    toggle.addEventListener("click", () => {
      expanded = !expanded;
      render();
      setLabel();
    });
    wrap.appendChild(toggle);
  }

  bubble.appendChild(wrap);
}

function answerBadge(answerType, metadata) {
  const source = metadata && metadata.metadata_source;
  if (answerType === "metadata" || source === "document_evidence") {
    const badge = document.createElement("span");
    badge.className = "answer-badge";
    badge.textContent = "Evidence-based";
    return badge;
  }
  if (answerType === "catalog") {
    const badge = document.createElement("span");
    badge.className = "answer-badge catalog";
    badge.textContent = "Catalog";
    return badge;
  }
  return null;
}

function addAnswerToolbar(bubble, content, answerType, metadata) {
  const toolbar = document.createElement("div");
  toolbar.className = "answer-toolbar";

  const badge = answerBadge(answerType, metadata);
  if (badge) toolbar.appendChild(badge);

  const copy = document.createElement("button");
  copy.type = "button";
  copy.className = "copy-answer";
  copy.textContent = "Copy";
  copy.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(content);
    } catch (_error) {
      const range = document.createRange();
      range.selectNodeContents(bubble);
      const selection = window.getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
    }
    copy.textContent = "Đã copy";
    copy.classList.add("copied");
    setTimeout(() => {
      copy.textContent = "Copy";
      copy.classList.remove("copied");
    }, 1600);
  });
  toolbar.appendChild(copy);
  bubble.appendChild(toolbar);
}

function clearMessages() {
  els.messages.replaceChildren();
}

function renderEmptyState() {
  const state = document.createElement("div");
  state.className = "empty-state";

  const mark = document.createElement("div");
  mark.className = "empty-mark";
  mark.setAttribute("aria-hidden", "true");
  mark.textContent = "Z";

  const heading = document.createElement("h2");
  heading.textContent = "GRC Assistant";

  const copy = document.createElement("p");
  copy.textContent =
    "Trợ lý tri thức GRC của ZaloPay. Tra cứu chính sách, quy trình, tiêu chuẩn bảo mật và tuân thủ — câu trả lời được trích dẫn từ tài liệu ISMS đã lập chỉ mục.";

  state.append(mark, heading, copy);

  const total = Number(els.documentCount.textContent);
  if (Number.isFinite(total) && total > 0) {
    const status = document.createElement("p");
    status.className = "empty-status";
    status.textContent = `${total} tài liệu trong cơ sở tri thức`;
    state.appendChild(status);
  }
  els.messages.appendChild(state);
}

function appendMessage(message) {
  els.messages.querySelector(".empty-state")?.remove();

  const row = document.createElement("article");
  row.className = `message-row ${message.role}`;
  if (message.status === "error") row.classList.add("error");

  const bubble = document.createElement("div");
  bubble.className = "bubble";

  if (message.status === "loading") {
    const dots = document.createElement("span");
    dots.className = "loading-dots";
    dots.setAttribute("aria-label", "Đang tìm câu trả lời");
    dots.append(document.createElement("i"), document.createElement("i"), document.createElement("i"));
    bubble.appendChild(dots);
  } else if (message.role === "assistant" && message.status !== "error") {
    addAnswerToolbar(bubble, message.content || "", message.answer_type, message.metadata);
    bubble.appendChild(createFormattedAnswer(message.content));
    if (message.answer_type !== "catalog") {
      appendSources(bubble, message.sources || []);
    }
  } else {
    bubble.appendChild(createFormattedAnswer(message.content));
  }

  row.appendChild(bubble);
  els.messages.appendChild(row);
  scrollToLatest();
  return row;
}

function renderMessages() {
  clearMessages();
  const session = activeSession();
  if (!session || !session.messages.length) {
    renderEmptyState();
    return;
  }
  session.messages.forEach(appendMessage);
  scrollToLatest();
}

function scrollToLatest() {
  els.messages.scrollTop = els.messages.scrollHeight;
}

function renderSessions() {
  els.sessionList.replaceChildren();
  els.sessionCount.textContent = String(sessions.length);
  sessions
    .slice()
    .sort((a, b) => String(b.updated_at).localeCompare(String(a.updated_at)))
    .forEach((session) => {
      const item = document.createElement("button");
      item.type = "button";
      item.className = "session-item";
      if (session.session_id === activeSessionId) item.classList.add("active");

      const title = document.createElement("span");
      title.className = "session-title";
      title.textContent = session.title || "New chat";

      const meta = document.createElement("span");
      meta.className = "session-meta";
      meta.textContent = `${session.messages.length} tin nhắn · ${formatTime(session.updated_at)}`;

      item.append(title, meta);
      item.addEventListener("click", () => {
        activeSessionId = session.session_id;
        saveSessions();
        renderSessions();
        renderMessages();
        closeSidebar();
        els.input.focus();
      });
      els.sessionList.appendChild(item);
    });
}

/* ----------------------------------------------------------- state ui */
function setStatus(label, state) {
  els.statusPill.textContent = label;
  els.statusPill.dataset.state = state;
}

function showError(message) {
  const text = (message || "").trim();
  if (!text) {
    hideError();
    return;
  }
  els.errorText.textContent = text;
  els.errorBanner.hidden = false;
  els.errorRetry.hidden = !lastQuestion;
}

function hideError() {
  els.errorBanner.hidden = true;
}

function updateSendState() {
  els.send.disabled = sending || els.input.value.trim().length === 0;
}

function autoResize() {
  els.input.style.height = "auto";
  els.input.style.height = `${Math.min(els.input.scrollHeight, 200)}px`;
}

/* ----------------------------------------------------------- networking */
function renderOverview(payload) {
  const total = Number(payload && payload.total_documents);
  if (els.introTotal && Number.isFinite(total)) els.introTotal.textContent = String(total);
  if (!els.introStats) return;
  const byType = Array.isArray(payload && payload.by_type) ? payload.by_type : [];
  els.introStats.replaceChildren();
  byType.forEach((entry) => {
    const card = document.createElement("div");
    card.className = "intro-stat";
    const num = document.createElement("span");
    num.className = "intro-stat-num";
    num.textContent = String(entry.count);
    const label = document.createElement("span");
    label.className = "intro-stat-label";
    label.textContent = entry.label || entry.type || "";
    card.append(num, label);
    els.introStats.appendChild(card);
  });
}

async function loadDocumentCount() {
  try {
    const response = await fetch("/documents/count", { headers: appHeaders() });
    if (response.status === 401 || response.status === 403) {
      els.corpusNote.textContent = "Cần access token để xem trạng thái catalog.";
      openAccessPanel();
      return;
    }
    if (!response.ok) throw new Error("count unavailable");
    const payload = await response.json();
    const total = Number(payload.total_documents);
    els.documentCount.textContent = Number.isFinite(total) ? String(total) : "--";
    els.corpusNote.textContent = "Cơ sở tri thức sẵn sàng.";
    renderOverview(payload);
    if (!activeSession().messages.length) renderMessages();
  } catch (_error) {
    els.documentCount.textContent = "--";
    els.corpusNote.textContent = "Không lấy được trạng thái catalog.";
  }
}

async function ask(question) {
  if (sending) return;
  const session = activeSession();
  const previousHistory = historyForRequest(session);
  lastQuestion = question;
  hideError();

  if (!session.messages.length || session.title === "New chat") {
    session.title = titleFromQuestion(question);
  }
  session.messages.push({ role: "user", content: question });
  session.updated_at = nowIso();
  saveSessions();
  renderSessions();
  renderMessages();

  const loadingRow = appendMessage({ role: "assistant", status: "loading" });

  sending = true;
  els.input.disabled = true;
  updateSendState();
  setStatus("Đang tìm", "searching");

  try {
    const response = await fetch("/chat", {
      method: "POST",
      headers: appHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ question, session_id: session.session_id, history: previousHistory }),
    });

    let payload = {};
    try {
      payload = await response.json();
    } catch (_error) {
      payload = {};
    }

    if (response.status === 401 || response.status === 403) {
      openAccessPanel();
      throw new Error("Cần access token. Nhập token ở thanh bên rồi thử lại.");
    }
    if (!response.ok) {
      throw new Error(payload.error || SAFE_ERROR);
    }

    loadingRow.remove();
    session.messages.push({
      role: "assistant",
      content: payload.answer || "Không có nội dung trả lời.",
      sources: payload.sources || [],
      answer_type: payload.answer_type || (payload.metadata && payload.metadata.answer_type) || "rag",
      metadata: payload.metadata || {},
    });
    session.updated_at = nowIso();
    saveSessions();
    renderSessions();
    renderMessages();
    setStatus("Ready", "ready");
  } catch (error) {
    loadingRow.remove();
    renderMessages();
    setStatus("Lỗi", "error");
    showError(error.message || SAFE_ERROR);
  } finally {
    sending = false;
    els.input.disabled = false;
    updateSendState();
    els.input.focus();
  }
}

/* ----------------------------------------------------------- access token */
function openAccessPanel() {
  els.accessFields.hidden = false;
  els.accessToggle.setAttribute("aria-expanded", "true");
}

function updateAccessState() {
  const token = sessionStorage.getItem(TOKEN_KEY);
  els.accessState.textContent = token ? "Set" : "Not set";
  els.accessState.dataset.set = token ? "true" : "false";
  els.accessToken.value = token || "";
  els.clearToken.hidden = !token;
}

/* ----------------------------------------------------------- sidebar */
function openSidebar() {
  els.shell.classList.add("rail-open");
  els.sidebarScrim.hidden = false;
  els.sidebarToggle.setAttribute("aria-expanded", "true");
}
function closeSidebar() {
  els.shell.classList.remove("rail-open");
  els.sidebarScrim.hidden = true;
  els.sidebarToggle.setAttribute("aria-expanded", "false");
}

/* ----------------------------------------------------------- events */
els.form.addEventListener("submit", (event) => {
  event.preventDefault();
  const question = els.input.value.trim();
  if (!question || sending) return;
  els.input.value = "";
  autoResize();
  updateSendState();
  ask(question);
});

els.input.addEventListener("input", () => {
  autoResize();
  updateSendState();
  if (!els.errorBanner.hidden) hideError();
});

els.input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    if (!sending) els.form.requestSubmit();
  }
});

els.newChat.addEventListener("click", () => {
  const session = createSession();
  sessions.unshift(session);
  activeSessionId = session.session_id;
  lastQuestion = "";
  hideError();
  saveSessions();
  renderSessions();
  renderMessages();
  els.input.value = "";
  autoResize();
  updateSendState();
  closeSidebar();
  els.input.focus();
});

els.clearSessions.addEventListener("click", () => {
  if (!window.confirm("Xoá tất cả phiên chat lưu trên trình duyệt này?")) return;
  const session = createSession();
  sessions = [session];
  activeSessionId = session.session_id;
  lastQuestion = "";
  hideError();
  saveSessions();
  renderSessions();
  renderMessages();
  updateSendState();
});

const retry = () => {
  if (lastQuestion && !sending) ask(lastQuestion);
};
els.errorRetry.addEventListener("click", retry);

els.accessToggle.addEventListener("click", () => {
  const expanded = els.accessToggle.getAttribute("aria-expanded") === "true";
  els.accessFields.hidden = expanded;
  els.accessToggle.setAttribute("aria-expanded", String(!expanded));
});

els.saveToken.addEventListener("click", () => {
  const token = els.accessToken.value.trim();
  if (token) sessionStorage.setItem(TOKEN_KEY, token);
  updateAccessState();
  loadDocumentCount();
});

els.clearToken.addEventListener("click", () => {
  sessionStorage.removeItem(TOKEN_KEY);
  updateAccessState();
  loadDocumentCount();
});

els.sidebarToggle.addEventListener("click", () => {
  if (els.shell.classList.contains("rail-open")) closeSidebar();
  else openSidebar();
});
els.sidebarScrim.addEventListener("click", closeSidebar);

/* ----------------------------------------------------------- theme */
const THEME_KEY = "grc-theme";
function applyTheme(theme) {
  if (theme === "dark") document.documentElement.dataset.theme = "dark";
  else delete document.documentElement.dataset.theme;
}
function initTheme() {
  const stored = localStorage.getItem(THEME_KEY);
  if (stored === "dark" || stored === "light") return applyTheme(stored);
  applyTheme(window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
}
els.themeToggle?.addEventListener("click", () => {
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  applyTheme(next);
  localStorage.setItem(THEME_KEY, next);
});

/* ----------------------------------------------------------- intro */
const INTRO_KEY = "grc-entered";
function enterApp() {
  if (els.introScreen) els.introScreen.hidden = true;
  sessionStorage.setItem(INTRO_KEY, "1");
  document.getElementById("question")?.focus();
}
els.introEnter?.addEventListener("click", enterApp);

/* ----------------------------------------------------------- boot */
initTheme();
if (els.introScreen && sessionStorage.getItem(INTRO_KEY)) els.introScreen.hidden = true;
loadSessions();
updateAccessState();
renderSessions();
renderMessages();
updateSendState();
autoResize();
loadDocumentCount();
