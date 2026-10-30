"use strict";
// PWA do Biony: conversa por texto e voz com o servidor (mesma origem).

const $ = (id) => document.getElementById(id);
const store = {
  get(key) { try { return localStorage.getItem(key); } catch { return null; } },
  set(key, value) { try { value == null ? localStorage.removeItem(key) : localStorage.setItem(key, value); } catch {} },
};

let token = store.get("biony.token");
let session = store.get("biony.sessao") || newSessionId();
let speak = store.get("biony.falar") !== "0";
let busy = false;
const player = new Audio();

function newSessionId() {
  const id = "pwa-" + (crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36) + Math.random().toString(36).slice(2));
  store.set("biony.sessao", id);
  return id;
}

// ------------------------------------------------------------------ API

class AuthError extends Error {}

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (options.json !== undefined) {
    headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(options.json);
  }
  const response = await fetch(path, { ...options, headers });
  if (response.status === 401 && path !== "/login") {
    showLogin();
    throw new AuthError("Sessão expirada. Entre de novo.");
  }
  if (!response.ok) {
    let detail = `erro ${response.status}`;
    try { detail = (await response.json()).detail || detail; } catch {}
    throw new Error(detail);
  }
  return response.status === 204 ? null : response.json();
}

// ------------------------------------------------------------------ telas

function showLogin() {
  token = null;
  store.set("biony.token", null);
  $("chat").hidden = true;
  $("login").hidden = false;
  $("login-password").focus();
}

async function showChat() {
  $("login").hidden = true;
  $("chat").hidden = false;
  updateSpeakToggle();
  refreshStatus();
  await loadHistory();
  $("text").focus();
}

$("login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("login-error").textContent = "";
  const device = /Mobi|Android|iPhone/i.test(navigator.userAgent) ? "celular" : "computador";
  try {
    const result = await api("/login", { method: "POST", json: { senha: $("login-password").value, aparelho: device } });
    token = result.token;
    store.set("biony.token", token);
    $("login-password").value = "";
    await showChat();
  } catch (error) {
    $("login-error").textContent = error.message;
  }
});

$("logout").addEventListener("click", async () => {
  try { await api("/logout", { method: "POST" }); } catch {}
  showLogin();
});

$("new-chat").addEventListener("click", () => {
  session = newSessionId();
  $("messages").replaceChildren();
  setConfirm(false);
  showEmpty();
  $("text").focus();
});

$("speak-toggle").addEventListener("click", () => {
  speak = !speak;
  store.set("biony.falar", speak ? "1" : "0");
  updateSpeakToggle();
});

function updateSpeakToggle() {
  $("speak-toggle").setAttribute("aria-pressed", String(speak));
  $("speak-toggle").textContent = speak ? "🔊" : "🔇";
}

async function refreshStatus() {
  const dot = $("status-dot");
  try {
    const health = await api("/health");
    const ready = health.voz === "pronta";
    dot.className = "dot " + (ready ? "ok" : "warn");
    $("status-text").textContent = ready ? "" : `voz ${health.voz}`;
    $("mic").disabled = !ready;
    if (health.voz === "carregando") setTimeout(refreshStatus, 5000);
  } catch {
    dot.className = "dot off";
    $("status-text").textContent = "sem conexão";
  }
}

// ------------------------------------------------------------------ mensagens

function render(text) {
  // Markdown mínimo e seguro: escapa tudo e só então formata código e negrito.
  const escape = (s) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  return text.split(/```/).map((part, i) => {
    if (i % 2 === 1) return `<pre><code>${escape(part.replace(/^[\w+-]*\n/, ""))}</code></pre>`;
    return escape(part)
      .replace(/`([^`\n]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
  }).join("")
    // Com white-space: pre-wrap, as quebras em volta do bloco de código viram linhas vazias.
    .replace(/\n+(<pre>)/g, "$1")
    .replace(/(<\/pre>)\n+/g, "$1")
    .trim();
}

function addMessage(role, text, { voice = null, typing = false } = {}) {
  document.querySelector(".empty")?.remove();
  const bubble = document.createElement("div");
  bubble.className = `msg ${role}` + (typing ? " typing" : "");
  if (voice !== null) {
    const label = document.createElement("span");
    label.className = "voice";
    label.textContent = "🎙️ por voz";
    bubble.append(label);
  }
  const body = document.createElement("span");
  if (role === "biony") body.innerHTML = render(text); else body.textContent = text;
  bubble.append(body);
  $("messages").append(bubble);
  bubble.scrollIntoView({ block: "end" });
  return bubble;
}

function showEmpty() {
  const empty = document.createElement("p");
  empty.className = "empty";
  empty.textContent = "Oi, Lucas! Fala ou digita o que precisa.";
  $("messages").append(empty);
}

async function loadHistory() {
  $("messages").replaceChildren();
  try {
    const history = await api(`/sessoes/${encodeURIComponent(session)}/mensagens?limite=60`);
    history.mensagens.forEach((m) => addMessage(m.papel, m.texto));
    if (!history.mensagens.length) showEmpty();
  } catch (error) {
    if (!(error instanceof AuthError)) addMessage("erro", `Não carreguei o histórico: ${error.message}`);
  }
}

function setConfirm(visible) {
  $("confirm").hidden = !visible;
  // Os botões encolhem a área de mensagens; mantém a pergunta do Biony à vista.
  const list = $("messages");
  list.scrollTop = list.scrollHeight;
}

function setBusy(value) {
  busy = value;
  $("send").disabled = value;
  $("mic").disabled = value || $("status-dot").classList.contains("warn");
}

async function handleReply(promise, pending) {
  setBusy(true);
  try {
    const reply = await promise;
    session = reply.sessao;
    store.set("biony.sessao", session);
    pending.remove();
    addMessage("biony", reply.resposta);
    setConfirm(reply.aguardando_confirmacao);
    return reply;
  } catch (error) {
    pending.remove();
    if (!(error instanceof AuthError)) addMessage("erro", error.message);
  } finally {
    setBusy(false);
  }
}

async function sendText(text) {
  text = text.trim();
  if (!text || busy) return;
  setConfirm(false);
  addMessage("usuario", text);
  const pending = addMessage("biony", "", { typing: true });
  await handleReply(api("/texto", { method: "POST", json: { texto: text, sessao: session } }), pending);
}

$("composer").addEventListener("submit", (event) => {
  event.preventDefault();
  const text = $("text").value;
  $("text").value = "";
  autoresize();
  sendText(text);
});

$("text").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    $("composer").requestSubmit();
  }
});

function autoresize() {
  const box = $("text");
  box.style.height = "auto";
  box.style.height = Math.min(box.scrollHeight, 160) + "px";
  box.style.overflowY = box.scrollHeight > 160 ? "auto" : "hidden";
}
$("text").addEventListener("input", autoresize);

$("confirm").addEventListener("click", (event) => {
  const answer = event.target.dataset?.answer;
  if (answer) sendText(answer);
});

// ------------------------------------------------------------------ voz

let recorder = null;
let chunks = [];

function pickMimeType() {
  const options = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];
  return options.find((type) => window.MediaRecorder?.isTypeSupported?.(type)) || "";
}

$("mic").addEventListener("click", async () => {
  if (recorder) { recorder.stop(); return; }
  if (busy) return;
  // Destrava o áudio no iPhone: tocar algo dentro do toque libera o play() depois.
  player.src = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YQAAAAA=";
  player.play().catch(() => {});
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
  } catch (error) {
    addMessage("erro", window.isSecureContext
      ? `Sem acesso ao microfone: ${error.message}`
      : "O microfone só funciona por HTTPS (use o endereço do tailscale serve).");
    return;
  }
  const mimeType = pickMimeType();
  recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
  chunks = [];
  recorder.ondataavailable = (event) => event.data.size && chunks.push(event.data);
  recorder.onstop = () => {
    stream.getTracks().forEach((track) => track.stop());
    $("mic").classList.remove("recording");
    const type = recorder.mimeType || mimeType || "audio/webm";
    recorder = null;
    sendVoice(new Blob(chunks, { type }));
  };
  recorder.start();
  $("mic").classList.add("recording");
  setConfirm(false);
});

async function sendVoice(blob) {
  if (blob.size < 2000) return; // toque sem fala
  const extension = blob.type.includes("mp4") ? "m4a" : blob.type.includes("ogg") ? "ogg" : "webm";
  const form = new FormData();
  form.append("audio", blob, `fala.${extension}`);
  form.append("sessao", session);
  form.append("responder_com_audio", String(speak));
  const mine = addMessage("usuario", "…", { voice: true });
  const pending = addMessage("biony", "", { typing: true });
  const reply = await handleReply(api("/voz", { method: "POST", body: form }), pending);
  if (!reply) { mine.remove(); return; }
  mine.lastChild.textContent = reply.transcricao || "(não entendi nada)";
  if (reply.audio_wav_base64) {
    player.src = "data:audio/wav;base64," + reply.audio_wav_base64;
    player.play().catch(() => {});
  }
}

// ------------------------------------------------------------------ início

if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
if (token) showChat(); else showLogin();
