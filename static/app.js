const form = document.getElementById("chat-form");
const input = document.getElementById("question");
const button = document.getElementById("send");
const messages = document.getElementById("messages");
const statusPill = document.getElementById("status-pill");
const newChatButton = document.getElementById("new-chat");
const clearSessionsButton = document.getElementById("clear-sessions");
const sessionList = document.getElementById("session-list");

const storageKey = "securemind-rag:sessions:v1";
const maxHistoryMessages = 10;
const safeError = "I could not get an answer right now. Please try again.";
const exampleQuestions = [
  "can you tell me scope of ZION-QT-08",
  "quy dinh ve mat khau la gi?",
  "password policy requirements la gi?",
];

let sessions = [];
let activeSessionId = "";

function setStatus(label) {
  statusPill.textContent = label;
}

function nowIso() {
  return new Date().toISOString();
}

function makeId() {
  if (window.crypto && window.crypto.randomUUID) {
    return window.crypto.randomUUID();
  }
  return `session-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function titleFromQuestion(question) {
  const title = question.replace(/\s+/g, " ").trim();
  if (!title) {
    return "New chat";
  }
  return title.length > 46 ? `${title.slice(0, 43)}...` : title;
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

function createSession(title = "New chat") {
  const timestamp = nowIso();
  return {
    session_id: makeId(),
    title,
    created_at: timestamp,
    updated_at: timestamp,
    messages: [],
  };
}

function loadSessions() {
  try {
    const payload = JSON.parse(localStorage.getItem(storageKey) || "{}");
    if (Array.isArray(payload.sessions)) {
      sessions = payload.sessions.filter((session) => session && Array.isArray(session.messages));
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

  if (!sessions.some((session) => session.session_id === activeSessionId)) {
    activeSessionId = sessions[0].session_id;
  }
}

function saveSessions() {
  localStorage.setItem(
    storageKey,
    JSON.stringify({
      activeSessionId,
      sessions: sessions.slice(0, 30),
    }),
  );
}

function activeSession() {
  return sessions.find((session) => session.session_id === activeSessionId) || sessions[0];
}

function updateButtonState() {
  button.disabled = input.value.trim().length === 0 || button.dataset.loading === "true";
}

function appendInlineMarkdown(parent, text) {
  const parts = String(text).split(/(\*\*[^*]+\*\*)/g);
  parts.forEach((part) => {
    if (!part) {
      return;
    }
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      const strong = document.createElement("strong");
      strong.textContent = part.slice(2, -2);
      parent.appendChild(strong);
      return;
    }
    parent.appendChild(document.createTextNode(part));
  });
}

function createParagraph(lines) {
  const paragraph = document.createElement("p");
  appendInlineMarkdown(paragraph, lines.join(" "));
  return paragraph;
}

function createFormattedAnswer(text) {
  const block = document.createElement("div");
  block.className = "message-text formatted-answer";

  const lines = String(text || "").replace(/\r\n?/g, "\n").split("\n");
  let paragraphLines = [];
  const listStack = [];

  function flushParagraph() {
    if (paragraphLines.length) {
      block.appendChild(createParagraph(paragraphLines));
      paragraphLines = [];
    }
  }

  function closeLists() {
    listStack.length = 0;
  }

  function currentList() {
    return listStack[listStack.length - 1] || null;
  }

  function ensureList(indent) {
    while (listStack.length && indent < currentList().indent) {
      listStack.pop();
    }

    if (listStack.length && indent === currentList().indent) {
      return currentList();
    }

    const list = document.createElement("ul");
    const parent = currentList()?.lastItem || block;
    parent.appendChild(list);
    const entry = { indent, list, lastItem: null };
    listStack.push(entry);
    return entry;
  }

  lines.forEach((rawLine) => {
    const line = rawLine.trim();
    if (!line) {
      flushParagraph();
      closeLists();
      return;
    }

    const bullet = rawLine.match(/^(\s*)(?:[-*\u2022]|\d+[.)])\s+(.+)$/);
    if (bullet) {
      flushParagraph();
      const listEntry = ensureList(bullet[1].length);
      const item = document.createElement("li");
      appendInlineMarkdown(item, bullet[2].trim());
      listEntry.list.appendChild(item);
      listEntry.lastItem = item;
      return;
    }

    closeLists();
    paragraphLines.push(line);
  });

  flushParagraph();

  if (!block.childNodes.length) {
    block.textContent = "No response returned.";
  }

  return block;
}

function normalizeSource(source) {
  if (source && typeof source === "object") {
    const filename = source.filename ? String(source.filename) : "";
    const page = Number.isInteger(source.page) ? source.page : null;
    const label = source.label ? String(source.label) : `${filename}${page ? ` page ${page}` : ""}`.trim();
    return { filename, page, label: label || "Unknown source" };
  }

  return {
    filename: "",
    page: null,
    label: String(source || "Unknown source"),
  };
}

function appendSources(bubble, sources) {
  if (!Array.isArray(sources) || sources.length === 0) {
    return;
  }

  const normalizedSources = sources.map(normalizeSource);
  let expanded = false;
  const sourceWrap = document.createElement("section");
  sourceWrap.className = "sources";
  sourceWrap.setAttribute("aria-label", "Sources");

  const title = document.createElement("p");
  title.className = "sources-title";
  title.textContent = "Sources";
  sourceWrap.appendChild(title);

  const list = document.createElement("div");
  list.className = "source-list";

  function renderList() {
    list.replaceChildren();
    const visibleSources = expanded ? normalizedSources : normalizedSources.slice(0, 3);
    visibleSources.forEach((source) => {
      const card = document.createElement("div");
      card.className = "source-card";
      card.textContent = source.label;
      list.appendChild(card);
    });
  }

  renderList();
  sourceWrap.appendChild(list);

  if (normalizedSources.length > 3) {
    const moreButton = document.createElement("button");
    moreButton.className = "source-toggle";
    moreButton.type = "button";
    moreButton.textContent = `Show more sources (${normalizedSources.length - 3})`;
    moreButton.addEventListener("click", () => {
      expanded = !expanded;
      renderList();
      moreButton.textContent = expanded ? "Show fewer sources" : `Show more sources (${normalizedSources.length - 3})`;
    });
    sourceWrap.appendChild(moreButton);
  }

  bubble.appendChild(sourceWrap);
}

function createEmptyState() {
  const state = document.createElement("div");
  state.className = "empty-state";

  const title = document.createElement("p");
  title.className = "empty-title";
  title.textContent = "Ask about an ISMS, policy, procedure, or security document.";

  const copy = document.createElement("p");
  copy.className = "empty-copy";
  copy.textContent = "Answers come from retrieved document context and include source references when available.";

  const exampleWrap = document.createElement("div");
  exampleWrap.className = "empty-examples";
  exampleWrap.setAttribute("aria-label", "Example questions");
  exampleQuestions.forEach((question) => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "example-chip";
    chip.textContent = question;
    chip.addEventListener("click", () => {
      input.value = question;
      updateButtonState();
      input.focus();
    });
    exampleWrap.appendChild(chip);
  });

  state.append(title, copy, exampleWrap);
  return state;
}

function removeEmptyState() {
  messages.querySelector(".empty-state")?.remove();
}

function appendCatalogLabel(bubble, metadata = {}) {
  const label = document.createElement("div");
  label.className = "answer-label";
  const total = Number.isInteger(metadata.total_documents) ? ` - ${metadata.total_documents} documents` : "";
  label.textContent = `Document catalog${total}`;
  bubble.appendChild(label);
}

function appendMessage({ role, content, sources = [], status = "sent", answer_type = "rag", metadata = {} }) {
  removeEmptyState();

  const row = document.createElement("article");
  row.className = `message-row ${role}`;
  if (status === "error") {
    row.classList.add("error");
  }

  const bubble = document.createElement("div");
  bubble.className = "bubble";

  if (status === "loading") {
    const loading = document.createElement("span");
    loading.className = "loading-text";

    const dot = document.createElement("span");
    dot.className = "loading-dot";
    dot.setAttribute("aria-hidden", "true");

    const label = document.createElement("span");
    label.textContent = content;

    loading.append(dot, label);
    bubble.appendChild(loading);
  } else {
    if (role === "assistant" && answer_type === "catalog") {
      appendCatalogLabel(bubble, metadata);
    }
    bubble.appendChild(createFormattedAnswer(content));
    if (answer_type !== "catalog") {
      appendSources(bubble, sources);
    }
  }

  row.appendChild(bubble);
  messages.appendChild(row);
  messages.scrollTop = messages.scrollHeight;
  return row;
}

function renderMessages() {
  messages.replaceChildren();
  const session = activeSession();
  if (!session || !session.messages.length) {
    messages.appendChild(createEmptyState());
    return;
  }

  session.messages.forEach((message) => appendMessage(message));
  messages.scrollTop = messages.scrollHeight;
}

function renderSessions() {
  sessionList.replaceChildren();
  sessions
    .slice()
    .sort((a, b) => String(b.updated_at).localeCompare(String(a.updated_at)))
    .forEach((session) => {
      const item = document.createElement("button");
      item.type = "button";
      item.className = "session-item";
      if (session.session_id === activeSessionId) {
        item.classList.add("active");
      }

      const title = document.createElement("span");
      title.className = "session-title";
      title.textContent = session.title || "New chat";

      const meta = document.createElement("span");
      meta.className = "session-meta";
      meta.textContent = `${session.messages.length} messages - ${formatTime(session.updated_at)}`;

      item.append(title, meta);
      item.addEventListener("click", () => {
        activeSessionId = session.session_id;
        saveSessions();
        renderSessions();
        renderMessages();
        input.focus();
      });
      sessionList.appendChild(item);
    });
}

function createAndActivateSession() {
  const session = createSession();
  sessions.unshift(session);
  activeSessionId = session.session_id;
  saveSessions();
  renderSessions();
  renderMessages();
  input.value = "";
  updateButtonState();
  input.focus();
}

function historyForRequest(session) {
  return session.messages
    .filter((message) => message.role === "user" || message.role === "assistant")
    .slice(-maxHistoryMessages)
    .map((message) => ({
      role: message.role,
      content: message.content,
    }));
}

async function ask(question) {
  const session = activeSession();
  const previousHistory = historyForRequest(session);

  if (!session.messages.length || session.title === "New chat") {
    session.title = titleFromQuestion(question);
  }

  session.messages.push({ role: "user", content: question });
  session.updated_at = nowIso();
  saveSessions();
  renderSessions();
  renderMessages();

  const loadingRow = appendMessage({
    role: "assistant",
    content: "Searching documents...",
    status: "loading",
  });

  button.dataset.loading = "true";
  updateButtonState();
  setStatus("Searching");

  try {
    const response = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question,
        session_id: session.session_id,
        history: previousHistory,
      }),
    });

    let payload = {};
    try {
      payload = await response.json();
    } catch (_error) {
      payload = {};
    }

    if (!response.ok) {
      throw new Error(payload.error || safeError);
    }

    loadingRow.remove();
    session.messages.push({
      role: "assistant",
      content: payload.answer || "No response returned.",
      sources: payload.sources || [],
      answer_type: payload.answer_type || payload.metadata?.answer_type || "rag",
      metadata: payload.metadata || {},
    });
    session.updated_at = nowIso();
    saveSessions();
    renderSessions();
    renderMessages();
    setStatus("Ready");
  } catch (error) {
    loadingRow.remove();
    session.messages.push({
      role: "assistant",
      content: error.message || safeError,
      status: "error",
    });
    session.updated_at = nowIso();
    saveSessions();
    renderSessions();
    renderMessages();
    setStatus("Error");
  } finally {
    button.dataset.loading = "false";
    updateButtonState();
    input.focus();
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const question = input.value.trim();
  if (!question || button.dataset.loading === "true") {
    return;
  }
  input.value = "";
  updateButtonState();
  ask(question);
});

input.addEventListener("input", updateButtonState);

input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});

newChatButton.addEventListener("click", createAndActivateSession);

clearSessionsButton.addEventListener("click", () => {
  if (!window.confirm("Clear all local chat sessions?")) {
    return;
  }
  const session = createSession();
  sessions = [session];
  activeSessionId = session.session_id;
  saveSessions();
  renderSessions();
  renderMessages();
  input.focus();
});

button.dataset.loading = "false";
loadSessions();
renderSessions();
renderMessages();
updateButtonState();

