/* The shell: where you are, how you move, and the layers that open over a view. The page shows data.json and can change nothing. */
const VIEWS = [["rings", "年轮", "rings"], ["graph", "论证", "graph"], ["log", "记录", "log"], ["problems", "问题", "problems"], ["outputs", "成果", "outputs"], ["runs", "实验", "runs"], ["paper", "论文", "paper"], ["works", "文献", "works"], ["resources", "算力", "resources"]];
const WANTS = { problems: p => p.events.some(e => e.type === "problem"), outputs: p => p.events.some(e => e.type === "output"), runs: p => hasNodes(p, ["experiment", "run"]), paper: p => hasNodes(p, ["section"]),
  works: p => hasNodes(p, ["paper"]) || p.events.some(e => e.type === "reference"), resources: p => hasNodes(p, ["resource"]), graph: p => hasNodes(p, ["claim", "method", "prior", "experiment"]) || p.events.some(e => TURNS.includes(e.type)) };
const shown = p => VIEWS.filter(([v]) => !WANTS[v] || WANTS[v](p));
const named = (view, p) => WORDS[familyOf(p)].view[view] || (view === "graph" && !hasNodes(p, ["claim", "method", "prior", "experiment"]) ? "脉络" : VIEWS.find(v => v[0] === view)[1]);
const WEEK = "日一二三四五六";
const $ = id => document.getElementById(id);
const iso = d => d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
const parse = t => { const [y, m, d] = t.split("-").map(Number); return new Date(y, m - 1, d); };
const dated = t => { const d = parse(t); return (d.getMonth() + 1) + " 月 " + d.getDate() + " 日"; };
const today = iso(new Date());
const remembered = key => { try { return localStorage.getItem(key); } catch (e) { return null; } };
const remember = (key, value) => { try { localStorage.setItem(key, value); } catch (e) { /* the page works without it */ } };

const S = { data: null, project: null, view: "rings", day: null, sel: null, section: null, filter: "all", q: "", follow: true, trail: [], picks: [], sort: null, family: null, tab: null };
let playing = null;

const P = () => S.data.projects.find(p => p.project === S.project) || S.data.projects[0];

function go(patch, animate) {
  const moved = patch.view && patch.view !== S.view;
  Object.assign(S, patch);
  const parts = [S.project, S.view, S.day || "", S.sel || "", S.section || ""];
  while (parts.length > 2 && !parts[parts.length - 1]) parts.pop();
  const hash = "#/" + parts.map(encodeURIComponent).join("/");
  if (location.hash !== hash) history.replaceState(null, "", hash);
  hidePop(); hideTip();
  if ((moved || animate) && document.startViewTransition && !matchMedia("(prefers-reduced-motion: reduce)").matches) { const shift = document.startViewTransition(render); for (const step of [shift.ready, shift.finished]) step.catch(() => {}); }
  else render();
}
function pick(id) {
  if (S.sel === id) return go({ sel: null, trail: [] });
  go({ sel: id, trail: S.sel ? [...S.trail, S.sel] : [], tab: null });
}
function readHash() {
  const [project, view, day, sel, section] = location.hash.replace(/^#\/?/, "").split("/").map(decodeURIComponent);
  if (project) S.project = project;
  if (VIEWS.some(v => v[0] === view)) S.view = view;
  if (day) { S.day = day; S.follow = false; }
  S.sel = sel || null; S.section = section || null;
}
function setDay(day) {
  const days = P().days;
  go({ day, follow: day === days[days.length - 1] });
}

/* Rail */
function renderRail() {
  const p = P();
  fill($("rail"),
    h("button", { type: "button", class: "project", "aria-label": "项目", onclick: ev => { ev.stopPropagation(); projectMenu(ev.currentTarget); } }, avatar(p, 40)),
    h("ul", null, shown(p).map(([v, , name]) => h("li", null,
      h("button", { type: "button", "aria-current": v === S.view ? "page" : null, onclick: () => go({ view: v, q: "", filter: "all" }) }, icon(name), h("span", { text: named(v, p) }))))),
    h("div", { class: "rail-foot" },
      h("button", { type: "button", "aria-label": "搜索", onclick: palette, onmouseenter: ev => tipAt(ev.currentTarget, "搜索 · Ctrl K"), onmouseleave: hideTip }, icon("search")),
      h("button", { type: "button", "aria-label": "明暗", onclick: flipTheme }, icon(theme() === "dark" ? "sun" : "moon"))));
}
function projectMenu(anchor) {
  popAt(anchor, h("div", { class: "menu" }, S.data.projects.map(p => h("button", { type: "button", "aria-current": p.project === S.project ? "true" : null,
    onclick: () => go({ project: p.project, day: null, sel: null, section: null, follow: true, trail: [] }, true) }, avatar(p, 30),
    h("span", null, h("b", { text: p.project }), h("small", { text: p.days.length + " 天 · " + p.events.length + " 条" }))))), "right");
}
const theme = () => document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
function flipTheme() {
  const next = theme() === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  remember("dendro-theme", next);
  renderRail();
}

/* Top */
function renderTop() {
  const title = named(S.view, P());
  fill($("top"),
    h("h1", null, h("span", { class: "where", text: title })),
    h("span", { class: "grow" }),
    ["log", "works", "runs"].includes(S.view) && h("input", { class: "filter", id: "filter", type: "search", placeholder: "筛选", value: S.q, "aria-label": "筛选", oninput: ev => { S.q = ev.target.value; renderContent(); } }),
    S.day && h("button", { type: "button", class: "date", "aria-haspopup": "dialog", onclick: ev => { ev.stopPropagation(); popAt(ev.currentTarget, calendar(), "below"); } },
      h("b", { text: dated(S.day) }), h("span", { text: "周" + WEEK[parse(S.day).getDay()] })));
}
function calendar(month) {
  const days = P().days, shown = month || S.day.slice(0, 7), [y, m] = shown.split("-").map(Number), by = {};
  for (const e of P().events) by[e.day] = (by[e.day] || 0) + 1;
  const peak = Math.max(...Object.values(by), 1), first = new Date(y, m - 1, 1), count = new Date(y, m, 0).getDate(), months = [...new Set(days.map(d => d.slice(0, 7)))];
  const turn = d => h("button", { type: "button", "aria-label": d < 0 ? "上个月" : "下个月", disabled: !months[months.indexOf(shown) + d], onclick: ev => { ev.stopPropagation(); fill($("pop"), calendar(months[months.indexOf(shown) + d])); } }, icon(d < 0 ? "back" : "next", 18));
  const cells = [...WEEK].map(w => h("span", { class: "wd", text: w }));
  for (let i = 0; i < first.getDay(); i++) cells.push(h("span"));
  for (let d = 1; d <= count; d++) {
    const date = shown + "-" + String(d).padStart(2, "0"), n = by[date];
    cells.push(h("button", { type: "button", class: "cell" + (date === today ? " today" : "") + (date === S.day ? " sel" : ""), disabled: !n, style: n ? { "--grown": (.25 + .75 * Math.sqrt(n / peak)).toFixed(2) } : null, onclick: () => setDay(date) }, h("span", { text: d })));
  }
  return h("div", { class: "calendar" }, h("header", null, turn(-1), h("b", { text: y + " 年 " + m + " 月" }), turn(1)), h("div", { class: "cal-grid" }, cells));
}

/* The core: the project's life as a strip of wood. Each band is a day and its width is how much happened. */
function renderCore() {
  const p = P(), core = $("core");
  if (!p.days.length) return fill(core);
  const rings = growth(p), reached = p.days.indexOf(S.day), span = rings.map(r => r.outer - r.inner);
  const band = (ring, i) => {
    const events = p.events.filter(e => e.day === ring.day), grain = s("svg", { class: "grain-strip", viewBox: "0 0 100 10", preserveAspectRatio: "none", "aria-hidden": "true" });
    const r = seeded(ring.day);
    for (const e of events) { const x = moment(e) * 100; grain.append(s("line", { x1: x.toFixed(2), x2: (x + r() * 1.2 - .6).toFixed(2), y1: 0, y2: 10, class: "fibre", dataset: { track: track(e) } })); }
    const scars = events.filter(e => e.type === "correction" || (e.type === "node.put" && e.body.status === "failed"));
    return h("button", { type: "button", class: "band" + (i === reached ? " now" : "") + (i > reached ? " later" : ""), style: { flexGrow: Math.max(span[i], .08) }, dataset: { day: ring.day, tone: i % 2 },
      "aria-label": dated(ring.day), "aria-current": i === reached ? "date" : null,
      onmouseenter: ev => tipAt(ev.currentTarget, dated(ring.day) + " · " + ring.count + " 条"), onmouseleave: hideTip },
      grain, scars.map(e => h("i", { class: "scar", style: { left: (moment(e) * 100).toFixed(1) + "%" } })), h("span", { class: "band-label", text: ring.day.slice(5).replace("-", ".") }));
  };
  fill(core, h("button", { type: "button", class: "play", "aria-label": playing ? "暂停" : "回放", onclick: togglePlay }, icon(playing ? "pause" : "play", 20)),
    h("div", { class: "strip", id: "strip", onpointerdown: scrub }, rings.map(band), h("span", { class: "bark" })));
}
function scrub(ev) {
  const at = e => { const hit = document.elementFromPoint(e.clientX, e.clientY)?.closest?.(".band"); if (hit && hit.dataset.day !== S.day) setDay(hit.dataset.day); };
  at(ev);
  const move = e => at(e), up = () => { removeEventListener("pointermove", move); removeEventListener("pointerup", up); };
  addEventListener("pointermove", move); addEventListener("pointerup", up);
}
function togglePlay() {
  if (playing) { clearInterval(playing); playing = null; return renderCore(); }
  const days = P().days;
  let at = S.day === days[days.length - 1] ? 0 : days.indexOf(S.day);
  setDay(days[at]);
  playing = setInterval(() => {
    at += 1;
    if (at >= days.length) { clearInterval(playing); playing = null; return renderCore(); }
    setDay(days[at]);
  }, 1100);
  renderCore();
}

/* Tip and pop: the two small layers. A tip follows the pointer's target; a pop stays until you leave it. */
function place(el, anchor, side) {
  el.hidden = false;
  const a = anchor.getBoundingClientRect(), w = el.offsetWidth, ht = el.offsetHeight, gap = 8;
  let x = a.left + a.width / 2 - w / 2, y = a.top - ht - gap;
  if (side === "below") { x = a.right - w; y = a.bottom + gap; }
  if (side === "right") { x = a.right + gap; y = a.top; }
  if (y < 8) y = a.bottom + gap;
  el.style.left = Math.max(8, Math.min(x, innerWidth - w - 8)) + "px";
  el.style.top = Math.max(8, Math.min(y, innerHeight - ht - 8)) + "px";
}
function tipAt(anchor, text) { const t = $("tip"); t.textContent = text; place(t, anchor); t.classList.add("in"); }
function hideTip() { const t = $("tip"); t.hidden = true; t.classList.remove("in"); }
function popAt(anchor, content, side) {
  const p = $("pop");
  if (!p.hidden && p.anchor === anchor) return hidePop();
  fill(p, content); p.anchor = anchor; place(p, anchor, side);
  requestAnimationFrame(() => p.classList.add("in"));
}
function hidePop() { const p = $("pop"); p.hidden = true; p.anchor = null; p.classList.remove("in"); }
function openModal(content, wide) {
  const m = $("modal");
  m.className = "modal" + (wide ? " wide" : "");
  fill(m, content);
  if (!m.open) m.showModal();
}
function closeModal() { const m = $("modal"); if (m.open) m.close(); }

/* Search everything */
function palette() {
  hidePop();
  const p = P(), box = h("input", { class: "pal-input", type: "search", placeholder: "节点、论文、记录", "aria-label": "搜索" }), list = h("ul", { class: "pal-list" });
  const items = [
    ...shown(p).map(([v, , name]) => ({ kind: "视图", title: named(v, p), run: () => go({ view: v }), icon: name })),
    ...stateAt(S.day).nodes.filter(n => !n.retired).map(n => ({ kind: KIND[n.kind] || n.kind, title: n.title || n.id, sub: n.summary, run: () => n.kind === "section" ? go({ view: "paper", section: n.id, sel: null }) : pick(n.id) })),
    ...p.events.filter(e => !STRUCTURAL.includes(e.type) && e.day <= S.day).map(e => ({ kind: TYPE[e.type] || e.type, title: e.body.text, sub: e.day.slice(5) + " " + e.time, run: () => go({ view: "log", day: e.day, follow: false, sel: e.id }) })),
  ];
  let at = 0, found = [];
  const show = () => {
    const q = box.value.trim().toLowerCase();
    found = (q ? items.filter(i => (i.title + " " + (i.sub || "")).toLowerCase().includes(q)) : items.slice(0, shown(p).length)).slice(0, 40);
    at = Math.min(at, Math.max(found.length - 1, 0));
    fill(list, found.length ? found.map((item, i) => h("li", { class: i === at ? "on" : null, onclick: () => { closeModal(); item.run(); }, onmouseenter: () => { at = i; for (const [j, li] of [...list.children].entries()) li.classList.toggle("on", j === at); } },
      h("span", { class: "pal-kind", text: item.kind }), h("span", { class: "pal-title", text: item.title }), item.sub && h("span", { class: "pal-sub", text: item.sub }))) : h("li", { class: "pal-none", text: "没有结果" }));
    list.children[at]?.scrollIntoView({ block: "nearest" });
  };
  box.addEventListener("input", () => { at = 0; show(); });
  box.addEventListener("keydown", ev => {
    if (ev.key === "ArrowDown") { ev.preventDefault(); at = Math.min(at + 1, found.length - 1); show(); }
    else if (ev.key === "ArrowUp") { ev.preventDefault(); at = Math.max(at - 1, 0); show(); }
    else if (ev.key === "Enter" && found[at]) { closeModal(); found[at].run(); }
  });
  openModal(h("div", { class: "palette" }, h("div", { class: "pal-head" }, icon("search", 20), box), list));
  show(); box.focus();
}

let arrived = null;
function renderContent() {
  const views = { rings: ringsView, graph: argumentView, log: logView, problems: problemsView, outputs: outputsView, runs: runsView, paper: paperView, works: worksView, resources: resourcesView };
  const place = S.project + S.view, kept = [".outline", ".scroll"].map(q => [q, document.querySelector(q)?.scrollTop, document.querySelector(q)?.scrollLeft]);
  const active = document.activeElement;
  fill($("content"), S.day ? h("div", { class: "view" + (place === arrived ? "" : " enter"), dataset: { view: S.view } }, views[S.view]()) : h("p", { class: "empty", text: "还没有记录" }));
  if (place === arrived) for (const [q, top, left] of kept) { const el = document.querySelector(q); if (el && top != null) { el.scrollTop = top; el.scrollLeft = left; } }
  if (active?.isConnected && active !== document.body && active !== document.activeElement) active.focus({ preventScroll: true });
  arrived = place;
}
function render() {
  if (!S.data) return;
  if (!S.data.projects.some(p => p.project === S.project)) S.project = S.data.projects[0].project;
  const days = P().days;
  KIND = { ...KINDS, ...WORDS[familyOf(P())].kind };
  if (!shown(P()).some(v => v[0] === S.view)) S.view = "rings";
  if (!days.includes(S.day) || S.follow) S.day = days.filter(d => d <= today).pop() || days[days.length - 1] || null;
  document.title = [named(S.view, P()), P().project, "Dendro"].filter(Boolean).join(" · ");
  renderRail(); renderTop(); renderCore(); renderContent(); renderDrawer();
}

document.addEventListener("click", ev => { if (!$("pop").hidden && !ev.target.closest("#pop")) hidePop(); });
document.addEventListener("keydown", ev => {
  const typing = ["INPUT", "TEXTAREA"].includes(document.activeElement.tagName), days = S.data ? P().days : [], at = days.indexOf(S.day);
  if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "k") { ev.preventDefault(); return $("modal").open ? closeModal() : palette(); }
  if ($("modal").open) return;
  if (ev.key === "Escape") { if (!$("pop").hidden) hidePop(); else if (S.sel) go({ sel: null, trail: [] }); else if (typing) document.activeElement.blur(); return; }
  if (typing || ev.ctrlKey || ev.metaKey || ev.altKey) return;
  if (ev.key === "/") { ev.preventDefault(); ($("filter") || { focus: palette }).focus(); }
  else if (ev.key === "ArrowLeft" && days[at - 1]) setDay(days[at - 1]);
  else if (ev.key === "ArrowRight" && days[at + 1]) setDay(days[at + 1]);
  else if (/^[1-9]$/.test(ev.key) && S.data && shown(P())[+ev.key - 1]) go({ view: shown(P())[+ev.key - 1][0], q: "", filter: "all" });
});
window.addEventListener("hashchange", () => { readHash(); render(); });

(async () => {
  const saved = remembered("dendro-theme");
  if (saved) document.documentElement.dataset.theme = saved;
  try {
    const answer = await fetch("data.json", { cache: "no-store" });
    if (!answer.ok) throw new Error(answer.status);
    S.data = await answer.json();
    for (const p of S.data.projects) for (const e of p.events) if (e.type === "said") e.body.text = e.body.text.replace(/<\/?pasted_content[^>]*>/g, "").trim();
  } catch (e) { fill($("content"), h("p", { class: "empty", text: "读不到记录" })); return; }
  if (!S.data.projects.length) { fill($("content"), h("p", { class: "empty", text: "还没有记录" })); return; }
  readHash();
  render();
})();
