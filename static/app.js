/* OpportunityHub — vanilla JS SPA. No build step, no framework.
   Served from the same origin as the API, so every call is a relative path. */

const $ = (s) => document.querySelector(s);
const view = $("#view");

const CATS = {
  internship:      { icon: "💼", color: "bg-blue-500/15 text-blue-300 border-blue-500/30" },
  hackathon:       { icon: "🏆", color: "bg-amber-500/15 text-amber-300 border-amber-500/30" },
  scholarship:     { icon: "🎓", color: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30" },
  course:          { icon: "📚", color: "bg-cyan-500/15 text-cyan-300 border-cyan-500/30" },
  certification:   { icon: "📜", color: "bg-violet-500/15 text-violet-300 border-violet-500/30" },
  competition:     { icon: "🥇", color: "bg-orange-500/15 text-orange-300 border-orange-500/30" },
  workshop:        { icon: "🛠️", color: "bg-pink-500/15 text-pink-300 border-pink-500/30" },
};
const MODES = { remote: "🌐 Remote", onsite: "📍 On-site", hybrid: "🔀 Hybrid" };

const state = {
  studentId: localStorage.getItem("oh_student") || null,
  profile: null,
  meta: { categories: Object.keys(CATS), modes: Object.keys(MODES), tags: [] },
  filters: { q: "", category: "", mode: "", skills: "", closing: "", minScore: 0, includeExpired: false },
  results: [],
  detail: null,
  gap: [],
};

/* ------------------------------------------------------------------ api */
async function api(path, opts = {}) {
  const res = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = (await res.json()).detail || msg; } catch (_) {}
    throw new Error(msg);
  }
  return res.status === 204 ? null : res.json();
}

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );

/* ---------------------------------------------------------------- utils */
function deadlineBadge(d) {
  if (d === null || d === undefined) return "";
  if (d < 0) return `<span class="rounded bg-slate-700/60 px-2 py-0.5 text-[11px] text-slate-400">Closed</span>`;
  if (d === 0) return `<span class="rounded bg-rose-500/20 px-2 py-0.5 text-[11px] font-bold text-rose-300">Due today</span>`;
  if (d <= 7)  return `<span class="rounded bg-rose-500/20 px-2 py-0.5 text-[11px] font-bold text-rose-300">${d}d left</span>`;
  if (d <= 30) return `<span class="rounded bg-amber-500/20 px-2 py-0.5 text-[11px] font-semibold text-amber-300">${d}d left</span>`;
  return `<span class="rounded bg-slate-700/60 px-2 py-0.5 text-[11px] text-slate-300">${d}d left</span>`;
}

function scoreRing(score) {
  if (!score) return "";
  const tone = score >= 75 ? "text-emerald-400 border-emerald-500/40 bg-emerald-500/10"
             : score >= 45 ? "text-amber-400 border-amber-500/40 bg-amber-500/10"
             : "text-slate-400 border-slate-600/40 bg-slate-700/20";
  return `<span class="rounded-lg border px-2 py-1 text-[11px] font-bold ${tone}">${score}% match</span>`;
}

function oppCard(o) {
  const cat = CATS[o.category] || { icon: "📌", color: "bg-slate-500/15 text-slate-300 border-slate-500/30" };
  const reasons = (o.reasons || []).slice(0, 2);
  return `
  <article class="card rounded-xl border border-slate-800 bg-slate-900/60 p-4 hover:border-violet-500/50">
    <div class="flex items-start justify-between gap-3">
      <div class="min-w-0">
        <div class="flex flex-wrap items-center gap-2">
          <span class="rounded-md border px-2 py-0.5 text-[11px] font-semibold ${cat.color}">${cat.icon} ${esc(o.category)}</span>
          <span class="text-[11px] text-slate-400">${esc(MODES[o.mode] || o.mode)}</span>
        </div>
        <h3 class="mt-2 truncate text-base font-semibold text-slate-100">${esc(o.title)}</h3>
        <p class="text-xs text-slate-400">${esc(o.org)}</p>
      </div>
      <div class="flex shrink-0 flex-col items-end gap-1.5">
        ${scoreRing(o.score)}
        ${deadlineBadge(o.daysLeft)}
      </div>
    </div>

    <p class="mt-2 line-clamp-2 text-sm text-slate-400">${esc(o.description)}</p>

    ${reasons.length ? `<p class="mt-2 text-[11px] text-violet-300">${reasons.map(esc).join(" · ")}</p>` : ""}

    <div class="mt-3 flex flex-wrap gap-1.5">
      ${(o.tags || []).slice(0, 6).map((t) => `<span class="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-400">${esc(t)}</span>`).join("")}
    </div>

    <div class="mt-3 flex items-center gap-2">
      <button data-open="${esc(o.id)}" class="rounded-lg bg-violet-600 px-3 py-1.5 text-xs font-semibold hover:bg-violet-500">Details</button>
      <a href="${esc(o.applyUrl)}" target="_blank" rel="noopener" class="rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-semibold hover:border-violet-500">Apply ↗</a>
      <button data-save="${esc(o.id)}" class="ml-auto rounded-lg border px-3 py-1.5 text-xs font-semibold ${
        o.saved ? "border-amber-500 bg-amber-500/15 text-amber-300" : "border-slate-700 text-slate-300 hover:border-amber-500"
      }">${o.saved ? "★ Saved" : "☆ Save"}</button>
    </div>
  </article>`;
}

const skeletonGrid = () =>
  `<div class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">${
    Array.from({ length: 6 }, () => `<div class="h-52 rounded-xl skeleton"></div>`).join("")
  }</div>`;

function noProfile() {
  return `
  <div class="rounded-xl border border-dashed border-slate-700 bg-slate-900/40 p-10 text-center">
    <div class="text-4xl">👋</div>
    <h2 class="mt-3 text-lg font-semibold">Start with your profile</h2>
    <p class="mx-auto mt-1 max-w-md text-sm text-slate-400">
      Tell us your education, skills and interests and we'll rank every open opportunity for you
      — and show you exactly why each one matched.
    </p>
    <div class="mt-5 flex flex-wrap justify-center gap-2">
      <button id="btn-demo-2" class="rounded-lg bg-violet-600 px-4 py-2 text-sm font-semibold hover:bg-violet-500">Load demo profile</button>
      <a href="#/profile" class="rounded-lg border border-slate-700 px-4 py-2 text-sm font-semibold hover:border-violet-500">Create my profile</a>
    </div>
  </div>`;
}

/* -------------------------------------------------------------- discover */
async function renderDiscover() {
  const f = state.filters;
  const chip = (active) => active
    ? "bg-violet-600 text-white border-violet-500"
    : "bg-slate-800 text-slate-300 border-slate-700 hover:border-slate-500";

  view.innerHTML = `
  <div class="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
    <div class="flex flex-wrap gap-2">
      <input id="q" value="${esc(f.q)}" placeholder="Search title, org or description…"
        class="min-w-[220px] flex-1 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-violet-500" />
      <select id="f-mode" class="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm">
        <option value="">Any mode</option>
        ${state.meta.modes.map((m) => `<option value="${m}" ${f.mode === m ? "selected" : ""}>${MODES[m]}</option>`).join("")}
      </select>
      <select id="f-closing" class="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm">
        <option value="">Any deadline</option>
        <option value="7"  ${f.closing === "7"  ? "selected" : ""}>Closing in 7 days</option>
        <option value="30" ${f.closing === "30" ? "selected" : ""}>Closing in 30 days</option>
      </select>
      <label class="flex items-center gap-1.5 rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-300">
        <input id="f-expired" type="checkbox" ${f.includeExpired ? "checked" : ""} class="accent-violet-500" /> Show closed
      </label>
    </div>

    <div class="mt-3 flex flex-wrap gap-1.5">
      <button data-cat="" class="chip border px-2.5 py-1 rounded-full text-xs ${chip(!f.category)}">All</button>
      ${state.meta.categories.map((c) => `
        <button data-cat="${c}" class="chip border px-2.5 py-1 rounded-full text-xs ${chip(f.category === c)}">
          ${(CATS[c] || {}).icon || ""} ${c}
        </button>`).join("")}
    </div>

    ${state.profile ? `
    <div class="mt-3 flex flex-wrap items-center gap-2 border-t border-slate-800 pt-3">
      <span class="text-xs text-slate-400">Min match:</span>
      ${[0, 40, 60, 80].map((v) => `
        <button data-score="${v}" class="border rounded-full px-2.5 py-1 text-xs ${chip(f.minScore === v)}">${v === 0 ? "Any" : v + "%+"}</button>`).join("")}
      <span class="ml-auto text-xs text-slate-500">${state.results.length} result(s)</span>
    </div>` : `<p class="mt-3 border-t border-slate-800 pt-3 text-xs text-slate-500">Load a profile to see match scores and personalised ranking.</p>`}
  </div>

  <div id="gap" class="mt-4"></div>
  <div id="results" class="mt-4">${skeletonGrid()}</div>`;

  const qs = new URLSearchParams();
  if (f.q) qs.set("q", f.q);
  if (f.category) qs.set("category", f.category);
  if (f.mode) qs.set("mode", f.mode);
  if (f.closing) qs.set("closing", f.closing);
  if (f.minScore) qs.set("minScore", f.minScore);
  if (f.includeExpired) qs.set("includeExpired", "true");
  if (state.studentId) qs.set("studentId", state.studentId);

  try {
    const data = await api(`/opportunities?${qs}`);
    state.results = data.items;
    $("#results").innerHTML = data.items.length
      ? `<div class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">${data.items.map(oppCard).join("")}</div>`
      : `<div class="rounded-xl border border-dashed border-slate-700 p-10 text-center text-sm text-slate-400">No opportunities match these filters.</div>`;
  } catch (e) {
    $("#results").innerHTML = `<div class="rounded-xl border border-rose-500/40 p-6 text-sm text-rose-300">${esc(e.message)}</div>`;
  }

  if (state.studentId) await renderGap();
}

async function renderGap() {
  const el = $("#gap");
  if (!el) return;
  try {
    const { items } = await api(`/skill-gap/${state.studentId}`);
    state.gap = items;
    if (!items.length) { el.innerHTML = ""; return; }
    el.innerHTML = `
    <div class="rounded-xl border border-cyan-500/30 bg-cyan-500/5 p-4">
      <div class="flex items-center gap-2">
        <span class="text-lg">📊</span>
        <h3 class="font-semibold text-cyan-200">Skill-gap analysis</h3>
        <span class="text-xs text-slate-400">— skills that unlock the most open opportunities for you</span>
      </div>
      <div class="mt-3 flex flex-wrap gap-2">
        ${items.map((g) => `
          <span class="rounded-lg border border-cyan-500/30 bg-slate-950/50 px-2.5 py-1.5 text-xs">
            <span class="font-semibold text-cyan-200">${esc(g.skill)}</span>
            <span class="ml-1 text-slate-400">${g.count} open</span>
          </span>`).join("")}
      </div>
    </div>`;
  } catch (_) { /* non-critical */ }
}

/* ------------------------------------------------------------- dashboard */
async function renderDashboard() {
  if (!state.studentId) { view.innerHTML = noProfile(); return; }
  view.innerHTML = `<div class="grid gap-4 md:grid-cols-4">${Array.from({ length: 4 }, () => `<div class="h-24 rounded-xl skeleton"></div>`).join("")}</div>`;

  let d;
  try { d = await api(`/dashboard/${state.studentId}`); }
  catch (e) { view.innerHTML = `<div class="rounded-xl border border-rose-500/40 p-6 text-sm text-rose-300">${esc(e.message)}</div>`; return; }

  const s = d.stats;
  const stat = (label, value, tone) => `
    <div class="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
      <p class="text-2xl font-bold ${tone}">${value}</p>
      <p class="text-xs text-slate-400">${label}</p>
    </div>`;

  view.innerHTML = `
  <div class="mb-4">
    <h1 class="text-2xl font-bold">Welcome back, ${esc(d.profile.name.split(" ")[0])} 👋</h1>
    <p class="text-sm text-slate-400">${esc(d.profile.degree || "")} ${d.profile.year ? "· " + esc(d.profile.year) : ""} ${d.profile.university ? "· " + esc(d.profile.university) : ""}</p>
  </div>

  <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
    ${stat("Open opportunities", s.openNow, "text-cyan-300")}
    ${stat("Strong matches (60%+)", s.strongMatches, "text-emerald-300")}
    ${stat("Closing this week", s.closingThisWeek, "text-rose-300")}
    ${stat("Saved by you", s.saved, "text-amber-300")}
  </div>

  <div class="mt-4 grid gap-4 lg:grid-cols-3">
    <div class="rounded-xl border border-slate-800 bg-slate-900/60 p-4 lg:col-span-2">
      <h2 class="mb-3 font-semibold">🎯 Recommended for you</h2>
      <div class="grid gap-3 sm:grid-cols-2">
        ${d.recommended.length ? d.recommended.map(oppCard).join("") : `<p class="text-sm text-slate-400">No matches yet — add more skills to your profile.</p>`}
      </div>
    </div>

    <div class="space-y-4">
      <div class="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
        <h2 class="mb-3 font-semibold">⏰ Closing soon</h2>
        ${d.closingSoon.length ? d.closingSoon.map((o) => `
          <button data-open="${esc(o.id)}" class="mb-2 block w-full rounded-lg border border-slate-800 p-2 text-left hover:border-violet-500">
            <p class="truncate text-sm">${esc(o.title)}</p>
            <p class="text-[11px] text-slate-400">${esc(o.org)} · ${deadlineBadge(o.daysLeft) || "no deadline"}</p>
          </button>`).join("") : `<p class="text-sm text-slate-400">Nothing closing this week.</p>`}
      </div>

      <div class="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
        <h2 class="mb-3 font-semibold">📈 Open by category</h2>
        ${Object.entries(d.byCategory).sort((a, b) => b[1] - a[1]).map(([k, v]) => `
          <div class="mb-2">
            <div class="flex justify-between text-xs"><span class="capitalize text-slate-300">${esc(k)}</span><span class="text-slate-400">${v}</span></div>
            <div class="mt-1 h-1.5 rounded bg-slate-800"><div class="h-1.5 rounded bg-violet-500" style="width:${Math.round((v / s.openNow) * 100)}%"></div></div>
          </div>`).join("")}
      </div>
    </div>
  </div>

  ${d.skillGap.length ? `
  <div class="mt-4 rounded-xl border border-cyan-500/30 bg-cyan-500/5 p-4">
    <h2 class="font-semibold text-cyan-200">📊 Learn next</h2>
    <p class="mt-1 text-xs text-slate-400">Skills you're missing that appear across the most open listings.</p>
    <div class="mt-3 flex flex-wrap gap-2">
      ${d.skillGap.map((g) => `<span class="rounded-lg border border-cyan-500/30 bg-slate-950/50 px-2.5 py-1.5 text-xs"><b class="text-cyan-200">${esc(g.skill)}</b> <span class="text-slate-400">${g.count} open</span></span>`).join("")}
    </div>
  </div>` : ""}`;
}

/* ----------------------------------------------------------------- saved */
async function renderSaved() {
  if (!state.studentId) { view.innerHTML = noProfile(); return; }
  view.innerHTML = `<div class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">${skeletonGrid().match(/<div class="h-52 rounded-xl skeleton"><\/div>/g)?.slice(0, 3).join("") || ""}</div>`;
  try {
    const { items } = await api(`/bookmarks/${state.studentId}`);
    view.innerHTML = `
    <h1 class="mb-4 text-2xl font-bold">🔖 Saved opportunities <span class="text-base font-normal text-slate-400">(${items.length})</span></h1>
    ${items.length
      ? `<div class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">${items.map(oppCard).join("")}</div>`
      : `<div class="rounded-xl border border-dashed border-slate-700 p-10 text-center">
           <div class="text-4xl">☆</div>
           <p class="mt-3 text-sm text-slate-400">Nothing saved yet. Hit <b>Save</b> on any opportunity to track its deadline here.</p>
           <a href="#/discover" class="mt-4 inline-block rounded-lg bg-violet-600 px-4 py-2 text-sm font-semibold hover:bg-violet-500">Browse opportunities</a>
         </div>`}`;
  } catch (e) {
    view.innerHTML = `<div class="rounded-xl border border-rose-500/40 p-6 text-sm text-rose-300">${esc(e.message)}</div>`;
  }
}

/* --------------------------------------------------------------- profile */
function renderProfile() {
  const p = state.profile || { name: "", email: "", university: "", year: "", degree: "", skills: [], interests: [], categories: [] };
  const tag = (arr, key) => (p[key] || []).map((t) => `
    <span class="rounded-full border border-violet-500/40 bg-violet-500/10 px-2.5 py-1 text-xs">
      ${esc(t)}<button data-rm="${key}" data-v="${esc(t)}" class="ml-1.5 text-violet-300 hover:text-rose-300">×</button>
    </span>`).join("");

  view.innerHTML = `
  <h1 class="mb-1 text-2xl font-bold">🎓 Student profile</h1>
  <p class="mb-5 text-sm text-slate-400">This drives your match scores and recommendations.</p>

  <form id="pform" class="grid gap-6 lg:grid-cols-3">
    <div class="rounded-xl border border-slate-800 bg-slate-900/60 p-5 lg:col-span-2">
      <div class="grid gap-4 sm:grid-cols-2">
        <label class="block text-sm">Full name *
          <input name="name" required value="${esc(p.name)}" class="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 outline-none focus:border-violet-500" />
        </label>
        <label class="block text-sm">Email * <span class="text-[11px] text-slate-500">(used as your login key)</span>
          <input name="email" required type="email" value="${esc(p.email)}" class="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 outline-none focus:border-violet-500" />
        </label>
        <label class="block text-sm">University
          <input name="university" value="${esc(p.university)}" placeholder="Flora Institute of Technology, Pune" class="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 outline-none focus:border-violet-500" />
        </label>
        <label class="block text-sm">Degree
          <input name="degree" value="${esc(p.degree)}" placeholder="B.Tech Computer Engineering" class="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 outline-none focus:border-violet-500" />
        </label>
        <label class="block text-sm sm:col-span-2">Year of study
          <input name="year" value="${esc(p.year)}" placeholder="3rd Year" class="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 outline-none focus:border-violet-500" />
        </label>
      </div>

      <div class="mt-5 grid gap-5 sm:grid-cols-2">
        ${["skills", "interests"].map((k) => `
        <div>
          <label class="text-sm">${k === "skills" ? "Skills" : "Interests"}</label>
          <div class="mt-1 flex gap-2">
            <input id="in-${k}" placeholder="Type and press Enter" class="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-violet-500" />
            <button type="button" data-add="${k}" class="rounded-lg border border-slate-700 px-3 text-sm font-semibold hover:border-violet-500">Add</button>
          </div>
          <div class="mt-2 flex flex-wrap gap-1.5" id="tag-${k}">${tag(p, k) || `<span class="text-xs text-slate-500">none yet</span>`}</div>
        </div>`).join("")}
      </div>

      <button class="mt-6 rounded-lg bg-violet-600 px-5 py-2.5 font-semibold hover:bg-violet-500">Save profile</button>
    </div>

    <div class="rounded-xl border border-slate-800 bg-slate-900/60 p-5">
      <h2 class="font-semibold">Preferred categories</h2>
      <p class="mt-1 text-xs text-slate-400">Selections here add a relevance bonus.</p>
      <div class="mt-3 flex flex-wrap gap-1.5">
        ${state.meta.categories.map((c) => {
          const on = (p.categories || []).includes(c);
          return `<button type="button" data-togcat="${c}" class="rounded-full border px-2.5 py-1 text-xs ${
            on ? "border-violet-500 bg-violet-600 text-white" : "border-slate-700 text-slate-300 hover:border-slate-500"
          }">${(CATS[c] || {}).icon || ""} ${c}</button>`;
        }).join("")}
      </div>
      <div class="mt-6 rounded-lg border border-slate-800 bg-slate-950/50 p-3 text-xs text-slate-400">
        <b class="text-slate-300">How matching works</b><br />
        Skill match ×3, interest match ×2, interest in description ×1, followed category ×2 — normalised to 100%.
        Every score shows the terms that produced it.
      </div>
    </div>
  </form>`;

  $("#pform").addEventListener("submit", saveProfile);
}

/* Draft tag editing -- kept in a scratch object so Save is the only commit. */
let draft = { skills: [], interests: [], categories: [] };
function seedDraft() {
  const p = state.profile || {};
  draft = {
    skills: [...(p.skills || [])],
    interests: [...(p.interests || [])],
    categories: [...(p.categories || [])],
  };
}

function repaintTags() {
  for (const k of ["skills", "interests"]) {
    $("#tag-" + k).innerHTML = draft[k].map((t) => `
      <span class="rounded-full border border-violet-500/40 bg-violet-500/10 px-2.5 py-1 text-xs">
        ${esc(t)}<button type="button" data-rm="${k}" data-v="${esc(t)}" class="ml-1.5 text-violet-300 hover:text-rose-300">×</button>
      </span>`).join("") || `<span class="text-xs text-slate-500">none yet</span>`;
  }
  document.querySelectorAll("[data-togcat]").forEach((b) => {
    const on = draft.categories.includes(b.dataset.togcat);
    b.className = `rounded-full border px-2.5 py-1 text-xs ${
      on ? "border-violet-500 bg-violet-600 text-white" : "border-slate-700 text-slate-300 hover:border-slate-500"}`;
  });
}

async function saveProfile(e) {
  e.preventDefault();
  const fd = new FormData(e.target);
  const body = Object.fromEntries(fd.entries());
  body.skills = draft.skills;
  body.interests = draft.interests;
  body.categories = draft.categories;
  const btn = e.target.querySelector("button[type=submit], button:not([type])");
  if (btn) { btn.disabled = true; btn.textContent = "Saving…"; }
  try {
    const s = await api("/students", { method: "POST", body: JSON.stringify(body) });
    setStudent(s.id, s);
    alert("Profile saved — your recommendations are updated.");
    location.hash = "#/dashboard";
  } catch (err) {
    alert("Could not save: " + err.message);
    if (btn) { btn.disabled = false; btn.textContent = "Save profile"; }
  }
}

function setStudent(id, profile) {
  state.studentId = id;
  state.profile = profile;
  localStorage.setItem("oh_student", id);
  const el = $("#whoami");
  el.classList.remove("hidden");
  el.textContent = `👤 ${profile.name}`;
  seedDraft();
}

/* ----------------------------------------------------------------- modal */
function openDetail(id) {
  const o = state.results.find((r) => r.id === id) || state.detail?.id === id ? null : null;
  const cached = [...state.results];
  const found = cached.find((r) => r.id === id);
  if (!found) return;
  const cat = CATS[found.category] || { icon: "📌", color: "bg-slate-500/15 text-slate-300 border-slate-500/30" };

  const d = document.createElement("div");
  d.id = "modal";
  d.className = "fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/70 p-4 sm:p-8";
  d.innerHTML = `
  <div class="w-full max-w-2xl rounded-2xl border border-slate-700 bg-slate-900 p-6">
    <div class="flex items-start justify-between gap-3">
      <div>
        <span class="rounded-md border px-2 py-0.5 text-[11px] font-semibold ${cat.color}">${cat.icon} ${esc(found.category)}</span>
        <h2 class="mt-2 text-xl font-bold">${esc(found.title)}</h2>
        <p class="text-sm text-slate-400">${esc(found.org)} · ${esc(MODES[found.mode] || found.mode)}</p>
      </div>
      <button id="mclose" class="rounded-lg border border-slate-700 px-2.5 py-1 text-sm hover:border-slate-500">✕</button>
    </div>

    <div class="mt-3 flex flex-wrap items-center gap-2">
      ${scoreRing(found.score)} ${deadlineBadge(found.daysLeft)}
      ${found.eligibility ? `<span class="text-[11px] text-slate-400">Eligibility: ${esc(found.eligibility)}</span>` : ""}
    </div>

    <p class="mt-4 text-sm leading-relaxed text-slate-300">${esc(found.description)}</p>

    ${(found.reasons || []).length ? `
    <div class="mt-4 rounded-lg border border-violet-500/30 bg-violet-500/5 p-3">
      <p class="text-xs font-semibold text-violet-200">✨ Why this matched you</p>
      <ul class="mt-1 list-inside list-disc text-xs text-slate-300">
        ${found.reasons.map((r) => `<li>${esc(r)}</li>`).join("")}
      </ul>
    </div>` : ""}

    <div class="mt-4">
      <p class="text-xs text-slate-400">Skills & tags</p>
      <div class="mt-1.5 flex flex-wrap gap-1.5">
        ${(found.tags || []).map((t) => `<span class="rounded bg-slate-800 px-2 py-0.5 text-[11px] text-slate-300">${esc(t)}</span>`).join("")}
      </div>
    </div>

    ${found.deadline ? `<p class="mt-4 text-xs text-slate-400">Deadline: <b class="text-slate-200">${esc(found.deadline)}</b></p>` : ""}

    <div class="mt-5 flex flex-wrap gap-2">
      <a href="${esc(found.applyUrl)}" target="_blank" rel="noopener" class="rounded-lg bg-violet-600 px-4 py-2 text-sm font-semibold hover:bg-violet-500">Apply on official site ↗</a>
      <button data-save="${esc(found.id)}" class="rounded-lg border px-4 py-2 text-sm font-semibold ${
        found.saved ? "border-amber-500 bg-amber-500/15 text-amber-300" : "border-slate-700 hover:border-amber-500"
      }">${found.saved ? "★ Saved" : "☆ Save"}</button>
    </div>
  </div>`;
  document.body.appendChild(d);
  d.addEventListener("click", (ev) => { if (ev.target === d) d.remove(); });
  d.querySelector("#mclose").addEventListener("click", () => d.remove());
}

async function toggleSave(id) {
  if (!state.studentId) {
    alert("Load or create a profile first so we know whose bookmarks these are.");
    return;
  }
  try {
    const r = await api("/bookmarks", {
      method: "POST",
      body: JSON.stringify({ studentId: state.studentId, opportunityId: id }),
    });
    state.results = state.results.map((o) => (o.id === id ? { ...o, saved: r.saved } : o));
    const m = document.getElementById("modal");
    if (m) m.remove();
    route();
  } catch (e) { alert("Could not save: " + e.message); }
}

/* ---------------------------------------------------------------- router */
const ROUTES = { discover: renderDiscover, dashboard: renderDashboard, saved: renderSaved, profile: renderProfile };

async function route() {
  const name = (location.hash.replace(/^#\/?/, "") || "discover").split("?")[0];
  const fn = ROUTES[name] || renderDiscover;
  document.querySelectorAll(".navlink").forEach((a) => a.classList.toggle("active", a.dataset.nav === name));
  window.scrollTo(0, 0);
  await fn();
}

/* --------------------------------------------------------- global events */
document.addEventListener("click", async (e) => {
  const t = e.target;

  const open = t.closest("[data-open]");
  if (open) { openDetail(open.dataset.open); return; }

  const save = t.closest("[data-save]");
  if (save) { toggleSave(save.dataset.save); return; }

  if (t.closest("#btn-demo") || t.closest("#btn-demo-2")) {
    const b = t.closest("button");
    if (b) { b.disabled = true; b.textContent = "Loading…"; }
    try {
      const s = await api("/demo-profile", { method: "POST" });
      setStudent(s.id, s);
      if (!location.hash) location.hash = "#/dashboard";
      await route();
    } catch (err) { alert("Demo failed: " + err.message); }
    return;
  }

  const cat = t.closest("[data-cat]");
  if (cat) { state.filters.category = cat.dataset.cat; renderDiscover(); return; }

  const sc = t.closest("[data-score]");
  if (sc) { state.filters.minScore = Number(sc.dataset.score); renderDiscover(); return; }

  const add = t.closest("[data-add]");
  if (add) {
    const k = add.dataset.add;
    const inp = $("#in-" + k);
    const v = inp.value.trim();
    if (v && !draft[k].some((x) => x.toLowerCase() === v.toLowerCase())) { draft[k].push(v); repaintTags(); }
    inp.value = "";
    return;
  }

  const rm = t.closest("[data-rm]");
  if (rm) {
    const k = rm.dataset.rm;
    draft[k] = draft[k].filter((x) => x !== rm.dataset.v);
    repaintTags();
    return;
  }

  const tog = t.closest("[data-togcat]");
  if (tog) {
    const c = tog.dataset.togcat;
    draft.categories = draft.categories.includes(c)
      ? draft.categories.filter((x) => x !== c)
      : [...draft.categories, c];
    repaintTags();
  }
});

let debounce;
document.addEventListener("input", (e) => {
  if (e.target.id === "q") {
    clearTimeout(debounce);
    debounce = setTimeout(() => { state.filters.q = e.target.value; renderDiscover(); }, 280);
  }
});
document.addEventListener("change", (e) => {
  if (e.target.id === "f-mode")     { state.filters.mode = e.target.value; renderDiscover(); }
  if (e.target.id === "f-closing")  { state.filters.closing = e.target.value; renderDiscover(); }
  if (e.target.id === "f-expired")  { state.filters.includeExpired = e.target.checked; renderDiscover(); }
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && e.target.id?.startsWith("in-")) {
    e.preventDefault();
    document.querySelector(`[data-add="${e.target.id.slice(3)}"]`)?.click();
  }
  if (e.key === "Escape") document.getElementById("modal")?.remove();
});
window.addEventListener("hashchange", route);

/* ------------------------------------------------------------------ boot */
(async function boot() {
  try {
    state.meta = await api("/meta");
    if (state.studentId) {
      try { state.profile = await api(`/students/${state.studentId}`); setStudent(state.studentId, state.profile); }
      catch (_) { state.studentId = null; localStorage.removeItem("oh_student"); }
    } else {
      seedDraft();
    }
    await route();
  } catch (e) {
    view.innerHTML = `<div class="rounded-xl border border-rose-500/40 p-6 text-sm text-rose-300">
      Could not reach the API: ${esc(e.message)}</div>`;
  } finally {
    $("#splash").remove();
  }
})();
