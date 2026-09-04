// Plain fetch() calls to the FastAPI backend - no framework, no build step.
// DOM nodes are built with createElement/textContent (never innerHTML on
// user/model text) so nothing typed or generated can be run as HTML.

let currentVideoId = null;
let videos = [];

const urlInput = document.getElementById("url-input");
const ingestBtn = document.getElementById("ingest-btn");
const ingestStatus = document.getElementById("ingest-status");
const videoListEl = document.getElementById("video-list");
const chatHeader = document.getElementById("chat-header");
const nowPlayingThumb = document.getElementById("now-playing-thumb");
const nowPlayingTitle = document.getElementById("now-playing-title");
const chatLog = document.getElementById("chat-log");
const questionInput = document.getElementById("question-input");
const askBtn = document.getElementById("ask-btn");

function thumbnailUrl(videoId) {
  return `https://img.youtube.com/vi/${videoId}/mqdefault.jpg`;
}

async function loadVideoList(selectVideoId) {
  const res = await fetch("/api/videos");
  videos = await res.json();
  renderVideoList();

  const target = selectVideoId || currentVideoId;
  const match = videos.find((v) => v.video_id === target);
  if (match) {
    setCurrentVideo(match.video_id, match.title);
  }
}

function renderVideoList() {
  videoListEl.replaceChildren();

  if (videos.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty-state small";
    empty.textContent = "No videos yet.";
    videoListEl.appendChild(empty);
    return;
  }

  for (const v of videos) {
    const item = document.createElement("button");
    item.className = "video-item" + (v.video_id === currentVideoId ? " active" : "");
    item.type = "button";

    const thumb = document.createElement("img");
    thumb.src = thumbnailUrl(v.video_id);
    thumb.alt = "";
    item.appendChild(thumb);

    const title = document.createElement("span");
    title.className = "video-item-title";
    title.textContent = v.title || v.video_id;
    item.appendChild(title);

    item.addEventListener("click", () => {
      if (v.video_id === currentVideoId) return;
      setCurrentVideo(v.video_id, v.title);
      resetChatLog("Ask away.");
    });

    videoListEl.appendChild(item);
  }
}

function setCurrentVideo(videoId, title) {
  currentVideoId = videoId;

  nowPlayingThumb.src = thumbnailUrl(videoId);
  nowPlayingTitle.textContent = title || videoId;
  chatHeader.hidden = false;

  questionInput.disabled = false;
  askBtn.disabled = false;

  renderVideoList();
}

function setStatus(el, message, isError) {
  el.textContent = message;
  el.classList.toggle("error", Boolean(isError));
}

async function ingestVideo() {
  const url = urlInput.value.trim();
  if (!url) return;

  ingestBtn.disabled = true;
  setStatus(ingestStatus, "Fetching transcript and building the index...", false);

  try {
    const res = await fetch("/api/ingest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ youtube_url: url }),
    });
    const data = await res.json();

    if (!res.ok) {
      setStatus(ingestStatus, data.detail || "Ingestion failed.", true);
      return;
    }

    setStatus(ingestStatus, `Ready: "${data.title || data.video_id}".`, false);
    urlInput.value = "";
    await loadVideoList(data.video_id);
  } catch (err) {
    setStatus(ingestStatus, "Network error - is the server running?", true);
  } finally {
    ingestBtn.disabled = false;
  }
}

function resetChatLog(message) {
  chatLog.replaceChildren();
  const empty = document.createElement("p");
  empty.className = "empty-state";
  empty.textContent = message;
  chatLog.appendChild(empty);
}

function clearEmptyState() {
  const empty = chatLog.querySelector(".empty-state");
  if (empty) empty.remove();
}

function appendBubble(role, text) {
  clearEmptyState();
  const bubble = document.createElement("div");
  bubble.className = `bubble ${role}`;
  bubble.textContent = text;
  chatLog.appendChild(bubble);
  chatLog.scrollTop = chatLog.scrollHeight;
  return bubble;
}

function appendTypingBubble() {
  clearEmptyState();
  const bubble = document.createElement("div");
  bubble.className = "bubble assistant typing";
  for (let i = 0; i < 3; i++) {
    const dot = document.createElement("span");
    dot.className = "dot";
    bubble.appendChild(dot);
  }
  chatLog.appendChild(bubble);
  chatLog.scrollTop = chatLog.scrollHeight;
  return bubble;
}

// Renders a small safe subset of markdown (bold text + bullet lists) that
// Gemini tends to reply with. Everything is built with createElement /
// createTextNode - never innerHTML - so this stays safe even though the
// text comes from a model response.
function renderFormatted(container, text) {
  container.replaceChildren();
  container.classList.remove("typing");
  let list = null;

  for (const rawLine of text.split("\n")) {
    const line = rawLine.trim();
    if (!line) {
      list = null;
      continue;
    }
    const bulletMatch = line.match(/^[*-]\s+(.*)/);
    if (bulletMatch) {
      if (!list) {
        list = document.createElement("ul");
        container.appendChild(list);
      }
      const li = document.createElement("li");
      appendInline(li, bulletMatch[1]);
      list.appendChild(li);
    } else {
      list = null;
      const p = document.createElement("p");
      appendInline(p, line);
      container.appendChild(p);
    }
  }
}

function appendInline(el, text) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  for (const part of parts) {
    if (!part) continue;
    if (part.startsWith("**") && part.endsWith("**")) {
      const strong = document.createElement("strong");
      strong.textContent = part.slice(2, -2);
      el.appendChild(strong);
    } else {
      el.appendChild(document.createTextNode(part));
    }
  }
}

function appendSources(sources) {
  const el = document.createElement("div");
  el.className = "sources";

  const label = document.createElement("span");
  label.className = "sources-label";
  label.textContent = "Sources";
  el.appendChild(label);

  for (const s of sources) {
    const tag = document.createElement("span");
    tag.className = "source-tag";
    tag.textContent = s.start_label;
    el.appendChild(tag);
  }

  chatLog.appendChild(el);
  chatLog.scrollTop = chatLog.scrollHeight;
}

async function askQuestion() {
  const question = questionInput.value.trim();
  if (!question || !currentVideoId) return;

  appendBubble("user", question);
  questionInput.value = "";
  askBtn.disabled = true;

  const typingBubble = appendTypingBubble();

  try {
    const res = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ video_id: currentVideoId, question }),
    });
    const data = await res.json();

    if (!res.ok) {
      typingBubble.classList.remove("typing");
      typingBubble.textContent = data.detail || "Something went wrong.";
      return;
    }

    renderFormatted(typingBubble, data.answer);
    if (data.sources && data.sources.length) {
      appendSources(data.sources);
    }
  } catch (err) {
    typingBubble.classList.remove("typing");
    typingBubble.textContent = "Network error - is the server running?";
  } finally {
    askBtn.disabled = false;
    questionInput.focus();
  }
}

ingestBtn.addEventListener("click", ingestVideo);
urlInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") ingestVideo();
});

askBtn.addEventListener("click", askQuestion);
questionInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") askQuestion();
});

loadVideoList();
