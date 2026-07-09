/* Veille IA : SPA vanilla lisant les JSON generes par le pipeline. */

const state = {
  index: null,      // { days: [{date, count, headline}] }
  day: null,        // donnees du jour affiche
  view: "digest",
  filter: "tous",
  cache: new Map(), // date -> day data
};

const $ = (sel, el = document) => el.querySelector(sel);
const app = $("#app");

const TAG_LABELS = {
  optimisation: "Optimisation", llm: "LLM", agents: "Agents", rag: "RAG",
  architecture: "Architecture", interpretabilite: "Interprétabilité",
  vision: "Vision", audio: "Audio", robotique: "Robotique", produit: "Produit",
  regulation: "Régulation", outils: "Outils", benchmark: "Benchmark", autre: "Autre",
};

/* ---------- Theme ---------- */
function initTheme() {
  const saved = localStorage.getItem("theme");
  const dark = saved ? saved === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  $("#theme-toggle").addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    localStorage.setItem("theme", next);
  });
}

/* ---------- Data ---------- */
async function loadIndex() {
  const r = await fetch("data/index.json", { cache: "no-cache" });
  if (!r.ok) throw new Error("index.json introuvable");
  state.index = await r.json();
}

async function loadDay(date) {
  if (state.cache.has(date)) return state.cache.get(date);
  const r = await fetch(`data/days/${date}.json`, { cache: "no-cache" });
  if (!r.ok) throw new Error(`Pas de données pour ${date}`);
  const data = await r.json();
  state.cache.set(date, data);
  return data;
}

/* ---------- Helpers ---------- */
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function fmtDate(iso) {
  return new Date(iso + "T12:00:00").toLocaleDateString("fr-FR", { weekday: "short", day: "numeric", month: "short" });
}

function scoreClass(rel) {
  return rel >= 8 ? "score-high" : rel >= 6 ? "score-mid" : "score-low";
}

function cardHTML(item, { showDeep = true } = {}) {
  const tags = (item.tags || []).map(t => `<span class="badge tag">${esc(TAG_LABELS[t] || t)}</span>`).join("");
  const deep = showDeep && item.deep_analysis
    ? `<button class="deep-btn" data-deep="${esc(item.id)}">Analyse détaillée</button>` : "";
  return `
  <article class="card" data-id="${esc(item.id)}">
    <div class="card-meta">
      <span class="badge source">${esc(item.source_label)}</span>
      ${tags}
      <span class="score-pill ${scoreClass(item.relevance)}" title="Pertinence"><span class="dot"></span>${esc(item.relevance)}/10</span>
    </div>
    <h3 class="card-title"><a href="${esc(item.url)}" target="_blank" rel="noopener">${esc(item.title)}</a></h3>
    <p class="card-tldr">${esc(item.tldr)}</p>
    <div class="card-footer">
      ${deep}
      <span class="reliability">Fiabilité ${esc(item.reliability)}/10</span>
      <a class="card-link" href="${esc(item.url)}" target="_blank" rel="noopener">Source ↗</a>
    </div>
  </article>`;
}

/* ---------- Views ---------- */
function renderDigest() {
  const d = state.day;
  const dg = d.digest || {};
  const tops = d.items.filter(it => it.deep_analysis);
  const highlights = (dg.highlights || []).map(h =>
    `<div class="highlight"><h3>${esc(h.title)}</h3><p>${esc(h.text)}</p></div>`).join("");
  app.innerHTML = `
    <p class="digest-date">${esc(fmtDate(d.date))} · ${d.items.length} items retenus</p>
    <h1 class="digest-headline">${esc(dg.headline || "Pas de digest pour ce jour")}</h1>
    <p class="digest-overview">${esc(dg.overview || "")}</p>
    ${highlights}
    ${dg.trend ? `<div class="trend-box"><strong>Tendance :</strong> ${esc(dg.trend)}</div>` : ""}
    ${tops.length ? `<h2 class="section-title">À la loupe <span class="count">analyses Mistral</span></h2>` : ""}
    ${tops.map(it => cardHTML(it)).join("")}
  `;
}

function renderFlux() {
  const items = state.day.items;
  const tags = ["tous", ...new Set(items.flatMap(it => it.tags || []))];
  const filtered = state.filter === "tous" ? items : items.filter(it => (it.tags || []).includes(state.filter));
  app.innerHTML = `
    <h2 class="section-title">Flux du jour <span class="count">${filtered.length} items</span></h2>
    <div class="filters" role="tablist">
      ${tags.map(t => `<button class="filter-chip ${t === state.filter ? "active" : ""}" data-filter="${esc(t)}">${esc(t === "tous" ? "Tous" : TAG_LABELS[t] || t)}</button>`).join("")}
    </div>
    ${filtered.map(it => cardHTML(it)).join("") || `<div class="state-msg">Aucun item pour ce filtre.</div>`}
  `;
}

function renderThemes() {
  const counts = {};
  for (const it of state.day.items)
    for (const t of it.tags || []) (counts[t] ??= []).push(it);
  const sorted = Object.entries(counts).sort((a, b) => b[1].length - a[1].length);
  const max = sorted.length ? sorted[0][1].length : 1;
  app.innerHTML = `
    <h2 class="section-title">Par thème</h2>
    ${sorted.map(([tag, items]) => `
      <div class="theme-group">
        <div class="theme-bar">
          <h3>${esc(TAG_LABELS[tag] || tag)}</h3>
          <div class="bar"><span style="width:${(items.length / max) * 100}%"></span></div>
          <span class="n">${items.length}</span>
        </div>
        ${items.slice(0, 4).map(it => cardHTML(it, { showDeep: false })).join("")}
      </div>`).join("") || `<div class="state-msg">Rien à afficher.</div>`}
  `;
}

function renderHistory() {
  const days = state.index.days || [];
  app.innerHTML = `
    <h2 class="section-title">Historique <span class="count">${days.length} jours</span></h2>
    ${days.map(d => `
      <button class="history-item" data-date="${esc(d.date)}">
        <span class="h-date">${esc(fmtDate(d.date))}</span>
        <span class="h-headline">${esc(d.headline || "(pas de digest)")}</span>
        <span class="h-count">${d.count} items</span>
      </button>`).join("") || `<div class="state-msg">Pas encore d'historique.</div>`}
  `;
}

function render() {
  if (!state.day && state.view !== "history") {
    app.innerHTML = `<div class="state-msg">Aucune donnée disponible. Le pipeline n'a pas encore tourné.</div>`;
    return;
  }
  ({ digest: renderDigest, flux: renderFlux, themes: renderThemes, history: renderHistory })[state.view]();
  window.scrollTo({ top: 0 });
}

/* ---------- Modal analyse profonde ---------- */
function openDeep(item) {
  const a = item.deep_analysis;
  const sections = [
    ["Problème", a.probleme], ["Méthode", a.methode],
    ["Résultats", a.resultats], ["Limites", a.limites],
  ];
  $("#modal-content").innerHTML = `
    <div class="card-meta"><span class="badge source">${esc(item.source_label)}</span><span class="badge deep">Analyse Mistral</span></div>
    <h2 id="modal-title">${esc(item.title)}</h2>
    ${sections.map(([t, txt]) => txt ? `<div class="analysis-section"><h4>${t}</h4><p>${esc(txt)}</p></div>` : "").join("")}
    ${a.verdict ? `<div class="verdict">${esc(a.verdict)}</div>` : ""}
    <p style="margin-top:16px"><a href="${esc(item.url)}" target="_blank" rel="noopener">Lire la source ↗</a></p>
  `;
  $("#modal").hidden = false;
  document.body.style.overflow = "hidden";
  $(".modal-close").focus();
}

function closeModal() {
  $("#modal").hidden = true;
  document.body.style.overflow = "";
}

/* ---------- Navigation ---------- */
async function goToDate(date) {
  try {
    state.day = await loadDay(date);
    state.filter = "tous";
    if (state.view === "history") state.view = "digest";
    updateChrome();
    render();
  } catch {
    app.innerHTML = `<div class="state-msg">Pas de données pour ${esc(date)}.</div>`;
  }
}

function updateChrome() {
  $("#current-date").textContent = state.day ? fmtDate(state.day.date) : "—";
  const dates = (state.index.days || []).map(d => d.date);
  const i = state.day ? dates.indexOf(state.day.date) : -1;
  $("#prev-day").disabled = i < 0 || i >= dates.length - 1;
  $("#next-day").disabled = i <= 0;
  document.querySelectorAll(".nav-item").forEach(b =>
    b.classList.toggle("active", b.dataset.view === state.view));
}

function initEvents() {
  document.querySelectorAll(".nav-item").forEach(btn =>
    btn.addEventListener("click", () => { state.view = btn.dataset.view; updateChrome(); render(); }));

  $("#brand").addEventListener("click", e => {
    e.preventDefault();
    const latest = state.index.days?.[0]?.date;
    if (latest) { state.view = "digest"; goToDate(latest); }
  });

  $("#prev-day").addEventListener("click", () => {
    const dates = state.index.days.map(d => d.date);
    const i = dates.indexOf(state.day.date);
    if (i < dates.length - 1) goToDate(dates[i + 1]);
  });
  $("#next-day").addEventListener("click", () => {
    const dates = state.index.days.map(d => d.date);
    const i = dates.indexOf(state.day.date);
    if (i > 0) goToDate(dates[i - 1]);
  });

  app.addEventListener("click", e => {
    const deepBtn = e.target.closest("[data-deep]");
    if (deepBtn) {
      const item = state.day.items.find(it => it.id === deepBtn.dataset.deep);
      if (item) openDeep(item);
      return;
    }
    const chip = e.target.closest("[data-filter]");
    if (chip) { state.filter = chip.dataset.filter; render(); return; }
    const hist = e.target.closest("[data-date]");
    if (hist) goToDate(hist.dataset.date);
  });

  $(".modal-backdrop").addEventListener("click", closeModal);
  $(".modal-close").addEventListener("click", closeModal);
  document.addEventListener("keydown", e => { if (e.key === "Escape") closeModal(); });
}

/* ---------- Init ---------- */
(async function init() {
  initTheme();
  initEvents();
  try {
    await loadIndex();
    const latest = state.index.days?.[0]?.date;
    if (latest) await goToDate(latest);
    else app.innerHTML = `<div class="state-msg">Aucune donnée : le pipeline n'a pas encore tourné.</div>`;
    updateChrome();
  } catch (err) {
    app.innerHTML = `<div class="state-msg">Erreur de chargement : ${esc(err.message)}</div>`;
  }
})();
