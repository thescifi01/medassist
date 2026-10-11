(() => {
  const API = ((window.APP_CONFIG || {}).API_URL || "").replace(/\/+$/, "");
  const MAX_BYTES = 10 * 1024 * 1024;
  const themeToggle = document.getElementById("theme-toggle");
  const savedTheme = localStorage.getItem("medassist_theme");
  document.documentElement.dataset.theme = savedTheme === "dark" ? "dark" : "light";
  themeToggle?.addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("medassist_theme", next); } catch {}
    themeToggle.setAttribute("aria-label", next === "dark" ? "Switch to light theme" : "Switch to dark theme");
  });
  const $ = (id) => document.getElementById(id);

  const els = {
    form: $("form"), file: $("file"), preview: $("preview"), dropText: $("drop-text"),
    symptoms: $("symptoms"), submit: $("submit"), msg: $("msg"), status: $("server-status"),
    results: $("results"), heatmap: $("heatmap"), camLabel: $("cam-label"),
    findings: $("findings"), report: $("report"),
    history: $("history"), historyEmpty: $("history-empty"),
    chatLog: $("chat-log"), chatForm: $("chat-form"), chatInput: $("chat-input"),
    chatSend: $("chat-send"), chips: $("chips"),
  };

  let chosen = null;
  let currentId = null;
  let chatBusy = false;

  const randomId = () =>
    (crypto.randomUUID && crypto.randomUUID()) ||
    Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, "0")).join("");
  let memoryId = null;
  function getClientId() {
    try {
      let id = localStorage.getItem("medassist_client_id");
      if (!id) { id = randomId(); localStorage.setItem("medassist_client_id", id); }
      return id;
    } catch {
      return (memoryId = memoryId || randomId());
    }
  }
  const clientId = getClientId();

  async function api(path, { method = "GET", body, json, signal } = {}) {
    const headers = { "X-Client-Id": clientId };
    let payload = body;
    if (json !== undefined) {
      headers["Content-Type"] = "application/json";
      payload = JSON.stringify(json);
    }
    let r;
    try {
      r = await fetch(`${API}${path}`, { method, headers, body: payload, signal });
    } catch (err) {
      if (err.name === "AbortError") throw err;
      throw new Error("Could not reach the analysis server. Check the API connection/CORS settings or try again when the server is awake.");
    }
    if (!r.ok) {
      let detail = `Request failed (${r.status})`;
      try {
        const d = await r.json();
        if (typeof d.detail === "string") detail = d.detail;
        else if (Array.isArray(d.detail)) detail = "Please check your input.";
      } catch { /* keep default */ }
      throw new Error(detail);
    }
    return r.status === 204 ? null : r.json();
  }

  function setStatus(text, cls) {
    els.status.textContent = text;
    els.status.className = `pill ${cls}`;
  }

  async function ping(attempt = 0) {
    try {
      const r = await fetch(`${API}/health`, { cache: "no-store" });
      if (!r.ok) throw new Error("bad status");
      setStatus("Server: ready", "pill-ok");
      loadHistory();
    } catch {
      if (attempt >= 30) { setStatus("Server: offline", "pill-bad"); return; }
      setStatus("Server: waking up…", "pill-wait");
      setTimeout(() => ping(attempt + 1), 4000);
    }
  }

  function say(text, isError = false) {
    els.msg.textContent = text;
    els.msg.className = isError ? "msg error" : "msg";
  }

  const esc = (s) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const inline = (s) =>
    esc(s)
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/(^|[\s(])_([^_]+)_(?=$|[\s).,])/g, "$1<em>$2</em>");
  function markdown(text) {
    const out = [];
    let inList = false;
    for (const raw of String(text).split("\n")) {
      const line = raw.trim();
      if (/^[-*•] /.test(line)) {
        if (!inList) { out.push("<ul>"); inList = true; }
        out.push(`<li>${inline(line.slice(2))}</li>`);
        continue;
      }
      if (inList) { out.push("</ul>"); inList = false; }
      if (!line) continue;
      const h = line.match(/^#{1,4}\s+(.*)/);
      out.push(h ? `<h3>${inline(h[1])}</h3>` : `<p>${inline(line)}</p>`);
    }
    if (inList) out.push("</ul>");
    return out.join("");
  }

  els.file.addEventListener("change", () => {
    const f = els.file.files[0];
    chosen = null;
    els.submit.disabled = true;
    els.preview.hidden = true;
    els.dropText.hidden = false;
    say("");
    if (!f) return;
    if (!["image/png", "image/jpeg"].includes(f.type)) { say("Please choose a PNG or JPG image.", true); return; }
    if (f.size > MAX_BYTES) { say("That image is larger than 10 MB.", true); return; }
    chosen = f;
    if (els.preview.dataset.url) URL.revokeObjectURL(els.preview.dataset.url);
    const url = URL.createObjectURL(f);
    els.preview.dataset.url = url;
    els.preview.src = url;
    els.preview.hidden = false;
    els.dropText.hidden = true;
    els.submit.disabled = false;
  });

  function addBubble(role, text) {
    const div = document.createElement("div");
    div.className = `bubble ${role}`;
    if (role === "assistant") div.innerHTML = markdown(text);
    else div.textContent = text;
    els.chatLog.append(div);
    els.chatLog.scrollTop = els.chatLog.scrollHeight;
    return div;
  }

  function setChatBusy(busy) {
    chatBusy = busy;
    els.chatSend.disabled = busy;
    els.chatInput.disabled = busy;
    els.chips.querySelectorAll("button").forEach((b) => (b.disabled = busy));
  }

  async function sendChat(text) {
    text = text.trim();
    if (!currentId || !text || chatBusy) return;
    setChatBusy(true);
    addBubble("user", text);
    const wait = addBubble("assistant", "Thinking…");
    wait.classList.add("pending");
    try {
      const { reply } = await api(`/scans/${currentId}/chat`, { method: "POST", json: { message: text } });
      wait.classList.remove("pending");
      wait.innerHTML = markdown(reply);
      els.chatInput.value = "";
    } catch (err) {
      wait.remove();
      addBubble("error", err.message);
    } finally {
      setChatBusy(false);
      els.chatLog.scrollTop = els.chatLog.scrollHeight;
      els.chatInput.focus();
    }
  }

  els.chatForm.addEventListener("submit", (e) => { e.preventDefault(); sendChat(els.chatInput.value); });
  els.chips.addEventListener("click", (e) => {
    const b = e.target.closest(".chip");
    if (b) sendChat(b.dataset.q);
  });

  function showScan(scan, { scroll = true } = {}) {
    currentId = scan.id;
    els.heatmap.src = scan.heatmap;
    els.camLabel.textContent = `(${scan.heatmap_label})`;

    els.findings.replaceChildren();
    for (const f of scan.findings) {
      const pct = Math.round(Math.min(Math.max(f.probability, 0), 1) * 100);
      const li = document.createElement("li");
      const head = document.createElement("div");
      head.className = "bar-head";
      const name = document.createElement("span");
      name.textContent = f.label;
      const val = document.createElement("span");
      val.textContent = `${pct}%`;
      head.append(name, val);
      const track = document.createElement("div");
      track.className = "bar-track";
      const fill = document.createElement("div");
      fill.className = "bar-fill";
      fill.style.width = `${pct}%`;
      track.append(fill);
      li.append(head, track);
      els.findings.append(li);
    }

    els.report.innerHTML = markdown(scan.report);
    els.chatLog.replaceChildren();
    for (const m of scan.messages) addBubble(m.role, m.content);
    els.results.hidden = false;
    const emptyResults = document.getElementById("results-empty");
    if (emptyResults) emptyResults.hidden = true;
    markActive();
    if (scroll) els.results.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  const fmt = (iso) => new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });

  function markActive() {
    els.history.querySelectorAll(".history-item").forEach((li) =>
      li.classList.toggle("active", Number(li.dataset.id) === currentId));
  }

  function renderHistory(items) {
    els.history.replaceChildren();
    els.historyEmpty.hidden = items.length > 0;
    for (const s of items) {
      const li = document.createElement("li");
      li.className = "history-item";
      li.dataset.id = s.id;

      const open = document.createElement("button");
      open.type = "button";
      open.className = "history-open";
      const title = document.createElement("span");
      title.textContent = s.top_finding
        ? `${s.top_finding.label} ${Math.round(s.top_finding.probability * 100)}%`
        : "Scan";
      const when = document.createElement("span");
      when.className = "h-when";
      when.textContent = fmt(s.created_at);
      open.append(title, when);
      open.addEventListener("click", () => openScan(s.id));

      const del = document.createElement("button");
      del.type = "button";
      del.className = "history-del";
      del.textContent = "Delete";
      del.setAttribute("aria-label", `Delete scan from ${fmt(s.created_at)}`);
      del.addEventListener("click", () => removeScan(s.id));

      li.append(open, del);
      els.history.append(li);
    }
    markActive();
  }

  async function loadHistory() {
    try { renderHistory(await api("/scans")); } catch { /* history is non-critical */ }
  }

  async function openScan(id) {
    try { showScan(await api(`/scans/${id}`)); }
    catch (err) { say(`Error: ${err.message}`, true); }
  }

  async function removeScan(id) {
    if (!confirm("Delete this scan and its chat?")) return;
    try {
      await api(`/scans/${id}`, { method: "DELETE" });
      if (currentId === id) { currentId = null; els.results.hidden = true; const emptyResults = document.getElementById("results-empty"); if (emptyResults) emptyResults.hidden = false; }
      loadHistory();
    } catch (err) { say(`Error: ${err.message}`, true); }
  }

  let scanAnimationTimer = null;
  let scanAnimationStart = 0;
  function showScanning() {
    const overlay = $("scan-overlay");
    if (!overlay) return;
    const image = $("scan-source");
    if (image && els.preview.src) image.src = els.preview.src;
    overlay.hidden = false;
    document.body.classList.add("scan-active");
    scanAnimationStart = Date.now();
    const steps = [...overlay.querySelectorAll(".scan-step")];
    const pct = $("scan-percent");
    const timer = $("scan-timer");
    let lastStep = -1;
    clearInterval(scanAnimationTimer);
    scanAnimationTimer = setInterval(() => {
      const seconds = Math.floor((Date.now() - scanAnimationStart) / 1000);
      if (timer) timer.textContent = String(Math.floor(seconds / 60)).padStart(2,"0") + ":" + String(seconds % 60).padStart(2,"0");
      const progress = Math.min(92, 8 + seconds * 2);
      if (pct) pct.textContent = String(progress).padStart(2,"0") + "%";
      const active = seconds < 3 ? 0 : seconds < 12 ? 1 : 2;
      if (active !== lastStep) {
        steps.forEach((step, i) => { step.classList.toggle("active", i === active); step.classList.toggle("done", i < active); const status = step.querySelector("b"); if (status) status.textContent = i < active ? "Complete" : i === active ? "In progress" : "Waiting"; });
        lastStep = active;
      }
    }, 250);
  }
  function hideScanning() {
    clearInterval(scanAnimationTimer); scanAnimationTimer = null;
    const overlay = $("scan-overlay");
    if (overlay) overlay.hidden = true;
    document.body.classList.remove("scan-active");
  }

  els.form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!chosen) return;
    els.submit.disabled = true;
    say("Analyzing… the first request can take up to a minute while the server wakes up.");
    showScanning();

    const body = new FormData();
    body.append("file", chosen);
    body.append("symptoms", els.symptoms.value.trim());

    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 150000);
    try {
      const scan = await api("/analyze", { method: "POST", body, signal: ctrl.signal });
      setStatus("Server: ready", "pill-ok");
      say("");
      showScan(scan);
      loadHistory();
    } catch (err) {
      say(err.name === "AbortError" ? "Timed out. Please try again." : `Error: ${err.message}`, true);
    } finally {
      clearTimeout(timer);
      hideScanning();
      els.submit.disabled = !chosen;
    }
  });

  document.querySelectorAll("[data-sample]").forEach((button) => {
    button.addEventListener("click", async () => {
      const url = button.dataset.sample;
      const original = button.innerHTML;
      button.disabled = true; button.textContent = "Loading sample…";
      try {
        const response = await fetch(url, { mode: "cors" });
        if (!response.ok) throw new Error("Sample image could not be loaded");
        const blob = await response.blob();
        const file = new File([blob], "nih-chest-xray-sample.png", { type: blob.type || "image/png" });
        const transfer = new DataTransfer(); transfer.items.add(file); els.file.files = transfer.files;
        els.file.dispatchEvent(new Event("change", { bubbles: true }));
        document.getElementById("drop").scrollIntoView({ behavior: "smooth", block: "center" });
        say("Research sample loaded. Add optional context, then select Analyze image.");
      } catch (error) {
        say("The remote sample could not be imported automatically. Open the NIH image in a new tab, save it to your device, then upload it here.", true);
        window.open(url, "_blank", "noopener,noreferrer");
      } finally { button.disabled = false; button.innerHTML = original; }
    });
  });

  ping();
})();
