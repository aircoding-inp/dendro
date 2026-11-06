/* Dendro's own drawing: a project as a cross-section of a tree, the core that scrubs through its days, and the ring marks that
   stand for status. A ring is a day; its width is how much happened. Shapes come from a seed, so a project always looks the same. */
const SVG = "http://www.w3.org/2000/svg";

function h(tag, props, ...kids) {
  const e = document.createElement(tag);
  dress(e, props);
  for (const kid of kids.flat(4)) if (kid != null && kid !== false) e.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return e;
}
function s(tag, props, ...kids) {
  const e = document.createElementNS(SVG, tag);
  dress(e, props);
  for (const kid of kids.flat(4)) if (kid != null && kid !== false) e.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return e;
}
function dress(e, props) {
  for (const [k, v] of Object.entries(props || {})) {
    if (v == null || v === false) continue;
    if (k === "class") e.setAttribute("class", v);
    else if (k === "text") e.textContent = v;
    else if (k === "dataset") Object.assign(e.dataset, v);
    else if (k === "style" && typeof v === "object") for (const [name, value] of Object.entries(v || {})) { if (name.startsWith("--")) e.style.setProperty(name, value); else e.style[name] = value; }
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v === true ? "" : v);
  }
}
function fill(target, ...kids) {
  target.replaceChildren(...h("div", null, ...kids).childNodes);
}

function seeded(text) {
  let a = 2166136261;
  for (const c of text) a = Math.imul(a ^ c.charCodeAt(0), 16777619);
  return () => {
    a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/* One outline for the whole tree: every ring follows it, more and more as it grows, the way wood does. */
function outline(seed) {
  const r = seeded(seed), waves = [2, 3, 4, 5, 7, 11].map((k, i) => ({ k, a: .05 / (1 + i * .75) * (.6 + r() * .8), p: r() * 6.283 }));
  return (theta, grown) => 1 + grown * waves.reduce((sum, w) => sum + w.a * Math.sin(w.k * theta + w.p), 0);
}
function ringPath(cx, cy, radius, shape, grown) {
  let d = "";
  for (let i = 0; i < 144; i++) {
    const t = i / 144 * 6.28319, r = radius * shape(t, grown);
    d += (i ? "L" : "M") + (cx + r * Math.cos(t)).toFixed(1) + " " + (cy + r * Math.sin(t)).toFixed(1);
  }
  return d + "Z";
}

const TRACKS = [["human", "人", 0], ["read", "解读", 1], ["argument", "论证", 2], ["run", "运行", 3], ["code", "代码", 4], ["paper", "论文", 5], ["works", "文献", 6]];
function track(e) {
  if (["said", "idea", "direction", "correction", "decision"].includes(e.type)) return "human";
  if (["reading", "survey", "design", "note", "reply", "problem", "resolved"].includes(e.type)) return "read";
  if (["commit", "change", "release", "ticket", "check"].includes(e.type)) return "code";
  if (e.type === "run.start" || e.type === "run.end" || e.type === "result") return "run";
  if (e.type === "text") return "paper";
  const id = e.body.id || e.body.src || "", kind = id.split(":")[0];
  return kind === "run" || kind === "resource" ? "run" : kind === "section" ? "paper" : kind === "paper" ? "works" : "argument";
}
const UNDATED = ["reference", "digest", "profile", "output"];
const moment = e => { const [a, b] = e.time.split(":").map(Number); return (a * 60 + b) / 1440; };

/* Ring widths: how much happened, kept readable when one day dwarfs the rest. */
function growth(project) {
  const counts = project.days.map(d => project.events.filter(e => e.day === d && !UNDATED.includes(e.type)).length);
  const weights = counts.map(n => 1 + Math.sqrt(n) * .55), total = weights.reduce((a, b) => a + b, 0);
  let at = .12;
  return project.days.map((day, i) => { const inner = at; at += weights[i] / total * .88; return { day, inner, outer: at, count: counts[i] }; });
}

function crossSection(project, day, size, on) {
  const c = size / 2, R = size / 2 - 44, shape = outline(project.project), rings = growth(project), reached = project.days.indexOf(day);
  const svg = s("svg", { class: "section", viewBox: `0 0 ${size} ${size}`, role: "img", "aria-label": project.project + " 年轮" });
  const r = seeded(project.project + "rays"), rays = s("g", { class: "rays" });
  const bark = rings[Math.max(reached, 0)].outer * R;
  svg.append(s("path", { class: "ghost-bark", d: ringPath(c, c, R + 7, shape, 1) }));
  rings.slice().reverse().forEach((ring, back) => {
    const i = rings.length - 1 - back, alive = i <= reached;
    const band = s("path", { class: "ring" + (alive ? "" : " future") + (i === reached ? " now" : ""), d: ringPath(c, c, ring.outer * R, shape, ring.outer), dataset: { day: ring.day, tone: i % 2 }, tabindex: alive ? "0" : null });
    band.addEventListener("click", ev => { ev.stopPropagation(); on.day(ring.day); });
    band.addEventListener("mouseenter", ev => on.ringTip(ev, ring));
    band.addEventListener("mouseleave", on.leave);
    svg.append(band);
    if (alive) {
      const hours = [...new Set(project.events.filter(e => e.day === ring.day).map(e => Math.floor(moment(e) * 12)))];
      for (const hour of hours) {
        const at = ring.inner + (ring.outer - ring.inner) * (hour + 1) / 12;
        svg.append(s("path", { class: "grain", d: ringPath(c, c, at * R, shape, at) }));
      }
    }
  });
  svg.append(s("circle", { class: "pith", cx: c, cy: c, r: rings[0].inner * R * .6 }));
  for (let i = 0; i < 90; i++) {
    const t = r() * 6.283, from = (.1 + r() * .45) * bark, to = from + (.08 + r() * .3) * bark;
    rays.append(s("line", { x1: (c + from * Math.cos(t)).toFixed(1), y1: (c + from * Math.sin(t)).toFixed(1), x2: (c + Math.min(to, bark * .96) * Math.cos(t)).toFixed(1), y2: (c + Math.min(to, bark * .96) * Math.sin(t)).toFixed(1) }));
  }
  svg.append(rays);
  const step = 6.28319 / TRACKS.length, start = -1.5708 - step / 2, marks = s("g", { class: "marks" }), jitter = seeded(project.project + "marks");
  TRACKS.forEach(([key, label], i) => {
    const t = start + step * (i + .5), x = c + (R + 26) * Math.cos(t), y = c + (R + 26) * Math.sin(t);
    svg.append(s("text", { class: "track", x: x.toFixed(1), y: y.toFixed(1), "text-anchor": "middle", "dominant-baseline": "middle", text: label }));
    const t0 = start + step * i;
    svg.append(s("line", { class: "split", x1: c + bark * .1 * Math.cos(t0), y1: c + bark * .1 * Math.sin(t0), x2: c + (R + 5) * Math.cos(t0), y2: c + (R + 5) * Math.sin(t0) }));
  });
  const place = {};
  rings.forEach((ring, i) => { place[ring.day] = { ...ring, i }; });
  for (const e of project.events) {
    if (UNDATED.includes(e.type)) continue;
    const ring = place[e.day], here = TRACKS.find(t => t[0] === track(e)), a = jitter(), b = jitter();
    if (ring.i > reached) continue;
    const at = ring.inner + (ring.outer - ring.inner) * Math.min(.96, Math.max(.06, moment(e))), t = start + step * (here[2] + .08 + a * .84), rr = at * R * shape(t, at);
    const quiet = ["node.put", "edge.put", "commit"].includes(e.type);
    const dot = s("circle", { class: "mark", cx: (c + rr * Math.cos(t)).toFixed(1), cy: (c + rr * Math.sin(t)).toFixed(1), r: quiet ? 1.5 : 2.5 + b, dataset: { track: here[0], type: e.type, id: e.id } });
    marks.append(dot);
  }
  marks.addEventListener("mouseover", ev => { if (ev.target.dataset.id) on.markTip(ev, ev.target.dataset.id); });
  marks.addEventListener("mouseout", on.leave);
  marks.addEventListener("click", ev => { if (ev.target.dataset.id) { ev.stopPropagation(); on.event(ev.target.dataset.id); } });
  svg.append(marks);
  return svg;
}

/* A project's face: its own rings, small. */
function avatar(project, size = 34) {
  const c = size / 2, shape = outline(project.project), rings = growth(project), R = size / 2 - 1;
  return s("svg", { class: "avatar", viewBox: `0 0 ${size} ${size}`, width: size, height: size, "aria-hidden": "true" },
    rings.length ? rings.slice().reverse().map((ring, i) => s("path", { class: "a-ring", dataset: { tone: i % 2 }, d: ringPath(c, c, ring.outer * R, shape, ring.outer) })) : s("circle", { class: "a-ring", cx: c, cy: c, r: R }),
    s("circle", { class: "a-pith", cx: c, cy: c, r: size * .05 }));
}

/* The mark for a status: a ring that fills as a thing is settled and takes a scar when it fails. */
function glyph(status, size = 16) {
  const g = s("svg", { class: "glyph", viewBox: "0 0 16 16", width: size, height: size, dataset: { st: status || "" }, "aria-hidden": "true" });
  const circle = (r, cls) => s("circle", { cx: 8, cy: 8, r, class: cls });
  const parts = {
    proposed: [circle(6.2, "g-dash")],
    approved: [circle(6.2, "g-line"), circle(2, "g-dot")],
    queued: [circle(6.2, "g-line"), circle(3.4, "g-dash")],
    running: [circle(6.2, "g-faint"), s("path", { class: "g-arc", d: "M8 1.8A6.2 6.2 0 0 1 14.2 8" }), circle(2.4, "g-dot")],
    done: [circle(7, "g-disc"), circle(4.4, "g-cut"), circle(1.9, "g-cut")],
    failed: [circle(7, "g-disc"), s("path", { class: "g-scar", d: "M8 8L15.5 3.8V12.2Z" })],
    stopped: [circle(6.2, "g-line"), s("path", { class: "g-bar", d: "M5 8H11" })],
    deferred: [circle(6.2, "g-faint"), circle(2, "g-faintdot")],
    dropped: [circle(6.2, "g-faint"), s("path", { class: "g-bar", d: "M4 12L12 4" })],
  };
  g.append(...(parts[status] || [circle(2.5, "g-faintdot")]));
  return g;
}

const ICONS = {
  problems: ["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z", "M12 7.5v5.5", "M12 16.2v.3"],
  outputs: ["M5 8.5 12 5l7 3.5-7 3.5z", "M5 12.5l7 3.5 7-3.5", "M5 16.5l7 3.5 7-3.5"],
  rings: ["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z", "M12 16.5a4.5 4.5 0 1 0 0-9 4.5 4.5 0 0 0 0 9Z", "M12 12.8a.8.8 0 1 0 0-1.6.8.8 0 0 0 0 1.6Z"],
  graph: ["M4 12h3.5c3 0 3-6.5 6-6.5H20", "M7.5 12c3 0 3 6.5 6 6.5H20", "M7.5 12H20"],
  log: ["M7 4v16", "M11 6h9", "M11 12h9", "M11 18h6", "M5.6 6h2.8", "M5.6 12h2.8", "M5.6 18h2.8"],
  runs: ["M3 9.5h18v5H3z", "M7 9.5v5", "M10 9.5v5", "M12 9.5v5", "M16 9.5v5", "M19 9.5v5"],
  paper: ["M6 3h9l4 4v14H6z", "M15 3v4h4", "M9 12h7", "M9 16h7"],
  works: ["M5 4v16", "M9.5 4v16", "M14 4.6l4.6 15.2", "M3.5 20h17"],
  resources: ["M6 6h12v12H6z", "M9.5 9.5h5v5h-5z", "M9 3v3", "M15 3v3", "M9 18v3", "M15 18v3", "M3 9h3", "M3 15h3", "M18 9h3", "M18 15h3"],
  search: ["M10.5 18a7.5 7.5 0 1 0 0-15 7.5 7.5 0 0 0 0 15Z", "M16 16l5 5"],
  sun: ["M12 16.5a4.5 4.5 0 1 0 0-9 4.5 4.5 0 0 0 0 9Z", "M12 2.5v2", "M12 19.5v2", "M2.5 12h2", "M19.5 12h2", "M5.3 5.3l1.4 1.4", "M17.3 17.3l1.4 1.4", "M5.3 18.7l1.4-1.4", "M17.3 6.7l1.4-1.4"],
  moon: ["M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5Z"],
  play: ["M8 5.5v13l10.5-6.5z"], pause: ["M8.5 5.5v13", "M15.5 5.5v13"],
  back: ["M14.5 5.5L8 12l6.5 6.5"], next: ["M9.5 5.5L16 12l-6.5 6.5"], close: ["M6 6l12 12", "M18 6L6 18"],
  expand: ["M14 4h6v6", "M10 20H4v-6", "M20 4l-7 7", "M4 20l7-7"], link: ["M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1", "M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"],
};
function icon(name, size = 22) {
  return s("svg", { class: "icon", viewBox: "0 0 24 24", width: size, height: size, "aria-hidden": "true" }, ICONS[name].map(d => s("path", { d })));
}
