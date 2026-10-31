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
const face = BionyFace.create($("face"));
let faceMode = store.get("biony.rosto") === "1";
let lastActivity = Date.now();
let audioCtx = null;
let analyser = null;
let levelLoop = 0;

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
  $("agenda").hidden = true;
  store.set("biony.token", null);
  $("chat").hidden = true;
  $("login").hidden = false;
  $("login-password").focus();
}

async function showChat() {
  $("login").hidden = true;
  $("chat").hidden = false;
  updateSpeakToggle();
  applyFaceMode();
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

$("face-toggle").addEventListener("click", () => {
  faceMode = !faceMode;
  store.set("biony.rosto", faceMode ? "1" : "0");
  applyFaceMode();
});

function applyFaceMode() {
  $("chat").classList.toggle("face-mode", faceMode);
  $("face-toggle").setAttribute("aria-pressed", String(faceMode));
  $("face-toggle").textContent = faceMode ? "💬" : "🙂";
  $("face-toggle").title = faceMode ? "Mostrar a conversa" : "Modo rosto (tela cheia)";
}

// ------------------------------------------------------------------ agenda

function agendaItem(title, detail, onDone) {
  const item = document.createElement("li");
  const text = document.createElement("div");
  const strong = document.createElement("strong");
  strong.textContent = title;
  text.append(strong);
  if (detail) {
    const small = document.createElement("small");
    small.textContent = detail;
    text.append(small);
  }
  item.append(text);
  if (onDone) {
    const done = document.createElement("button");
    done.className = "icon";
    done.title = "Concluir";
    done.textContent = "✓";
    done.addEventListener("click", onDone);
    item.append(done);
  }
  return item;
}

function emptyItem(text) {
  const item = document.createElement("li");
  item.className = "empty";
  item.textContent = text;
  return item;
}

async function loadAgenda() {
  $("agenda-error").textContent = "";
  try {
    const data = await api("/agenda");
    $("task-list").replaceChildren(...(data.tarefas.length ? data.tarefas.map((task) => {
      const notices = task.avisos.length ? `avisos: ${task.avisos.map((a) => a.quando_texto).join("; ")}` : "";
      const detail = [task.prazo_texto ? `prazo ${task.prazo_texto}` : "sem prazo", task.observacoes, notices]
        .filter(Boolean).join(" · ");
      return agendaItem(task.titulo, detail, async () => {
        try { await api(`/agenda/tarefas/${task.id}/concluir`, { method: "POST" }); await loadAgenda(); }
        catch (error) { $("agenda-error").textContent = error.message; }
      });
    }) : [emptyItem("Nenhuma tarefa aberta.")]));
    $("reminder-list").replaceChildren(...(data.lembretes.length
      ? data.lembretes.map((r) => agendaItem(r.texto, r.quando_texto))
      : [emptyItem("Nenhum lembrete pendente.")]));
  } catch (error) {
    if (!(error instanceof AuthError)) $("agenda-error").textContent = error.message;
  }
}

function showAgenda(open) {
  $("agenda").hidden = !open;
  $("chat").hidden = open;
  if (open) loadAgenda();
}

$("agenda-open").addEventListener("click", () => showAgenda(true));
$("agenda-close").addEventListener("click", () => showAgenda(false));

$("task-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const due = $("task-due").value; // "2026-11-15T14:00" (horário local)
  try {
    await api("/agenda/tarefas", { method: "POST", json: { titulo: $("task-title").value, prazo: due || null } });
    $("task-title").value = "";
    $("task-due").value = "";
    await loadAgenda();
  } catch (error) {
    $("agenda-error").textContent = error.message;
  }
});

// ------------------------------------------------------------------ rosto

// Horário de silêncio (igual ao dos lembretes): de noite ele cochila mais rápido.
function inQuietHours() {
  const now = new Date();
  const minutes = now.getHours() * 60 + now.getMinutes();
  return minutes >= 22 * 60 + 30 || minutes < 7 * 60;
}

function activity() {
  lastActivity = Date.now();
  if (face.state === "sonolento" || face.state === "dormindo") {
    face.setState("ocioso");
    face.react("surpreso", 600);
    face.blink();
  }
}

setInterval(() => {
  if (face.state !== "ocioso" && face.state !== "sonolento") return;
  const idle = (Date.now() - lastActivity) / 1000;
  const [sleepy, asleep] = inQuietHours() ? [40, 90] : [180, 420];
  if (idle > asleep) face.setState("dormindo");
  else if (idle > sleepy && face.state === "ocioso") face.setState("sonolento");
}, 5000);

function showEmotion(emotion, awaiting) {
  face.setState("ocioso");
  // A dúvida (esperando "sim/não") fica até a próxima ação; as outras passam sozinhas.
  face.react(emotion || "neutro", awaiting ? 0 : 2600);
}

function setCaption(text) {
  $("caption").textContent = text.replace(/```[\s\S]*?```/g, "[código]").replace(/[*`#]/g, "").slice(0, 240);
}

$("face-panel").addEventListener("click", () => {
  const sleeping = face.state === "sonolento" || face.state === "dormindo";
  activity();
  if (!sleeping && !busy) face.poke();
});

// Web Audio para medir o volume da fala e animar os olhos. Precisa nascer num toque (iPhone).
function ensureAudioGraph() {
  if (audioCtx) { audioCtx.resume().catch(() => {}); return; }
  const Context = window.AudioContext || window.webkitAudioContext;
  if (!Context) return;
  audioCtx = new Context();
  analyser = audioCtx.createAnalyser();
  analyser.fftSize = 512;
  audioCtx.createMediaElementSource(player).connect(analyser);
  analyser.connect(audioCtx.destination);
}

function playReply(base64, emotion, awaiting) {
  const bytes = Uint8Array.from(atob(base64), (c) => c.charCodeAt(0));
  const url = URL.createObjectURL(new Blob([bytes], { type: "audio/wav" }));
  const samples = new Uint8Array(analyser ? analyser.fftSize : 0);
  player.src = url;
  face.setState("falando");
  if (emotion && emotion !== "neutro") face.react(emotion, 0);
  cancelAnimationFrame(levelLoop);
  const tick = () => {
    if (analyser) {
      analyser.getByteTimeDomainData(samples);
      let sum = 0;
      for (const v of samples) sum += ((v - 128) / 128) ** 2;
      face.setLevel((Math.sqrt(sum / samples.length) - 0.015) * 7);
    } else {
      face.setLevel(0.35 + 0.3 * Math.sin(performance.now() / 90)); // sem Web Audio: fala genérica
    }
    levelLoop = requestAnimationFrame(tick);
  };
  tick();
  let finished = false;
  const done = () => {
    if (finished) return;
    finished = true;
    cancelAnimationFrame(levelLoop);
    face.setLevel(0);
    showEmotion(emotion, awaiting);
    URL.revokeObjectURL(url);
    activity();
  };
  player.onended = done;
  player.onerror = done;
  player.play().catch(done);
}

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
    const lastReply = history.mensagens.filter((m) => m.papel === "biony").pop();
    setCaption(lastReply ? lastReply.texto : "");
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
    setCaption(reply.resposta);
    setConfirm(reply.aguardando_confirmacao);
    return reply;
  } catch (error) {
    pending.remove();
    showEmotion("triste");
    if (!(error instanceof AuthError)) {
      addMessage("erro", error.message);
      setCaption(error.message);
    }
  } finally {
    setBusy(false);
  }
}

async function sendText(text) {
  text = text.trim();
  if (!text || busy) return;
  activity();
  setConfirm(false);
  addMessage("usuario", text);
  face.setState("pensando");
  setCaption("…");
  const pending = addMessage("biony", "", { typing: true });
  const reply = await handleReply(api("/texto", { method: "POST", json: { texto: text, sessao: session } }), pending);
  if (reply) showEmotion(reply.emocao, reply.aguardando_confirmacao);
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
$("text").addEventListener("input", () => {
  autoresize();
  activity();
});

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
  activity();
  // Destrava o áudio no iPhone: tocar algo dentro do toque libera o play() depois.
  ensureAudioGraph();
  player.src = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YQAAAAA=";
  player.play().catch(() => {});
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
  } catch (error) {
    addMessage("erro", window.isSecureContext
      ? `Sem acesso ao microfone: ${error.message}`
      : "O microfone só funciona por HTTPS (use o endereço do tailscale serve).");
    showEmotion("triste");
    return;
  }
  const mimeType = pickMimeType();
  recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
  chunks = [];
  recorder.ondataavailable = (event) => event.data.size && chunks.push(event.data);
  recorder.onstop = () => {
    stream.getTracks().forEach((track) => track.stop());
    $("mic").classList.remove("recording");
    face.setState("pensando");
    const type = recorder.mimeType || mimeType || "audio/webm";
    recorder = null;
    sendVoice(new Blob(chunks, { type }));
  };
  recorder.start();
  $("mic").classList.add("recording");
  face.setState("ouvindo");
  setCaption("Ouvindo…");
  setConfirm(false);
});

async function sendVoice(blob) {
  if (blob.size < 2000) { face.setState("ocioso"); setCaption(""); return; } // toque sem fala
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
  if (reply.audio_wav_base64) playReply(reply.audio_wav_base64, reply.emocao, reply.aguardando_confirmacao);
  else showEmotion(reply.emocao, reply.aguardando_confirmacao);
}

// ------------------------------------------------------------------ início

if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
if (token) showChat(); else showLogin();
