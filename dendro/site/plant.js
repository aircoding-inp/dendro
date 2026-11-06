/* Argument: the project as a plant. Existing work is the soil, gaps are roots, claims are boughs, methods are branches, experiments
   are leaves, and each finished run is a leaf on the ground. Its shape comes from everything the project ever held, so a node keeps
   its place on every day and a day only decides how much of the plant has grown. The page re-renders often, so the plant is built
   once and kept, and everything that moves is computed from the clock. */
const graphView = (() => {
  const SHOWN = ["prior", "claim", "method", "experiment", "paper", "run"], TIES = ["gap", "realized_by", "tested_by", "covers", "of"];
  const FALLEN = ["failed", "stopped", "dropped"], ENDED = ["done", ...FALLEN];
  const LEAF = { running: [1.12, 1], done: [1, 1], approved: [.78, .9], queued: [.78, .9], proposed: [.5, .62], deferred: [.5, .62], failed: [1, .85], stopped: [.95, .85], dropped: [.72, .7] };
  const TIER = { root: .3, trunk: .75, claim: 1.15, method: 1.55, twig: 1.95, leaf: 2.15, litter: 2.7 };
  const still = matchMedia("(prefers-reduced-motion: reduce)");
  const lerp = (a, b, t) => a + (b - a) * t, type = id => id.split(":")[0], f1 = v => v.toFixed(1);
  const out = t => 1 - (1 - t) ** 3, back = t => 1 + 2.6 * (t - 1) ** 3 + 1.6 * (t - 1) ** 2, even = t => t * t * (3 - 2 * t), flat = t => t;
  const grown = new WeakSet();
  let plant = null, locked = null, hovering = null, shownSel = null, ticking = false, last = 0, watching = false, wait = 0;

  /* Shape */
  function history(p) {
    const nodes = new Map(), above = {}, home = {}, gaps = {};
    for (const day of p.days) {
      const st = p.states[day];
      for (const n of st.nodes) if (SHOWN.includes(n.kind)) nodes.set(n.id, n);
      for (const e of st.edges) {
        if (e.rel === "realized_by") above[e.dst] ||= e.src;
        else if (e.rel === "tested_by" && (!above[e.dst] || (type(above[e.dst]) === "claim" && type(e.src) === "method"))) above[e.dst] = e.src;
        else if (e.rel === "of") above[e.src] ||= e.dst;
        else if (e.rel === "covers") home[e.dst] ||= e.src;
        else if (e.rel === "gap") (gaps[e.src] ||= new Set()).add(e.dst);
      }
    }
    return { nodes, above, home, gaps };
  }
  function curve(a, b, dir, n = 16) {
    const dx = b[0] - a[0], dy = Math.abs(b[1] - a[1]), c1 = [a[0] + dx * .08, a[1] + dir * dy * .62], c2 = [b[0] - dx * .42, b[1] - dir * dy * .12], pts = [];
    for (let i = 0; i <= n; i++) {
      const t = i / n, m = 1 - t;
      pts.push([0, 1].map(k => m * m * m * a[k] + 3 * m * m * t * c1[k] + 3 * m * t * t * c2[k] + t * t * t * b[k]));
    }
    return pts;
  }
  const along = (pts, u) => { const at = u * (pts.length - 1), i = Math.min(Math.floor(at), pts.length - 2), t = at - i; return [lerp(pts[i][0], pts[i + 1][0], t), lerp(pts[i][1], pts[i + 1][1], t)]; };
  function pebble(x, y, w, ht, rand) {
    const pts = Array.from({ length: 12 }, (_, i) => { const a = i / 12 * Math.PI * 2, k = .9 + rand() * .2; return [x + Math.cos(a) * w / 2 * k, y + Math.sin(a) * ht / 2 * k]; });
    const mid = i => { const a = pts[i % 12], b = pts[(i + 1) % 12]; return [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]; };
    return `M${mid(0).map(f1)} ` + pts.map((_, i) => `Q${pts[(i + 1) % 12].map(f1)} ${mid(i + 1).map(f1)}`).join(" ") + "Z";
  }
  const blade = (x, l, wide) => `M0,0 C${f1(l * .22)},${f1(-l * wide)} ${f1(l * .72)},${f1(-l * wide * .8)} ${f1(l)},0 C${f1(l * .72)},${f1(l * wide * .8)} ${f1(l * .22)},${f1(l * wide)} 0,0Z`;

  function build(p, frame) {
    const { nodes, above, home, gaps } = history(p), all = [...nodes.values()].sort((a, b) => (a.since < b.since ? -1 : a.since > b.since ? 1 : 0) || (a.id < b.id ? -1 : 1));
    const of = kind => all.filter(n => n.kind === kind), children = id => all.filter(n => above[n.id] === id);
    const priors = of("prior"), methods = of("method");
    const W = Math.max(frame.w, 880, methods.length * 178, priors.length * 192), small = frame.w < 720, k = frame.w / W, H = small ? Math.min(Math.max(frame.h / k, 660), 980) : Math.max(frame.h, 660), G = Math.round(H * .64), cx = W / 2, rand = seeded(p.project);
    const a1 = rand() * 6, a2 = rand() * 6, ground = x => G + Math.sin(x * .012 + a1) * 3.2 + Math.sin(x * .031 + a2) * 1.6;
    const L = { soil: s("g"), grains: s("g", { class: "grains" }), roots: s("g"), rocks: s("g"), grass: s("g"), rings: s("g"), wood: s("g"), sap: s("g"), graft: s("g"), seed: s("g", { class: "seed" }), leaves: s("g"), litter: s("g"), air: s("g") };
    const limbs = [], limbOf = {}, leaves = [], litter = [], rocks = {}, labels = {}, grains = [], parts = {};
    const part = (id, el) => { (parts[id] ||= []).push(el); el.dataset.id = id; return el; };

    const limb = (id, tier, pts, parent, at, bend) => {
      const wood = s("path", { class: "limb", dataset: { tier } }), sap = s("path", { class: "sap" });
      (tier === "root" || tier === "rootlet" ? L.roots : L.wood).append(wood); L.sap.append(sap);
      const n = pts.length - 1, nx = pts.map((q, i) => { const a = pts[Math.max(i - 1, 0)], b = pts[Math.min(i + 1, n)], dx = b[0] - a[0], dy = b[1] - a[1], d = Math.hypot(dx, dy) || 1; return [-dy / d, dx / d]; });
      const l = { id, tier, pts, nx, parent, at, bend, wood, sap, g: 0, w0: 1, w1: .5, want: false, load: 0, bx: 0, by: 0, sway: 0 };
      limbs.push(l);
      if (id) { limbOf[id] = l; part(id, wood); }
      return l;
    };

    /* Above ground */
    const base = [cx, ground(cx) + 3], fork = [cx + (rand() - .5) * 14, G - H * .13];
    const trunk = limb(null, "trunk", curve(base, fork, -1), null, 0, 1.2);
    const claims = of("claim").sort((a, b) => children(b.id).length - children(a.id).length).reduce((row, c, i) => { i % 2 ? row.unshift(c) : row.push(c); return row; }, []);
    const gap = Math.min(W * .8 / Math.max(claims.length - 1, 1), 340), reach = (claims.length - 1) / 2 || 1;
    const spot = {};
    claims.forEach((c, i) => {
      const off = (i - (claims.length - 1) / 2) / reach, end = [cx + off * reach * gap, G - H * (.2 + .06 * (1 - Math.abs(off)))], at = 1 - .3 * Math.abs(off);
      limb(c.id, "claim", curve(along(trunk.pts, at), end, -1), trunk, at, 3);
      spot[c.id] = end;
    });
    const rank = id => { const i = claims.findIndex(c => c.id === above[id]); return i < 0 ? claims.length / 2 : i; };
    methods.sort((a, b) => rank(a.id) - rank(b.id));
    methods.forEach((m, j) => {
      const x = W * .08 + (j + .5) / methods.length * W * .84, end = [x, 132 + ((x - cx) / (W / 2)) ** 2 * H * .1 + (j % 2) * H * .05], from = limbOf[above[m.id]] || trunk;
      limb(m.id, "method", curve(from.pts[from.pts.length - 1], end, -1), from, 1, 3.4);
      spot[m.id] = end;
    });
    const fan = new Map();
    for (const x of of("experiment")) { const at = limbOf[above[x.id]] ? above[x.id] : ""; fan.set(at, [...(fan.get(at) || []), x]); }
    for (const [at, group] of fan) {
      const from = limbOf[at] || trunk, end = from.pts[from.pts.length - 1], lean = (end[0] - cx) / W * .9, spread = Math.min(1.9, (group.length - 1) * .66);
      group.forEach((x, i) => {
        const a = lean + (group.length > 1 ? (i / (group.length - 1) - .5) * spread : 0), length = 66 + (i % 2) * 18, tip = [end[0] + Math.sin(a) * length, end[1] - Math.cos(a) * length];
        const twig = limb(x.id, "twig", curve(end, tip, -1, 8), from, 1, 2.2);
        const el = part(x.id, s("g", { class: "leaf", transform: "scale(0)", tabindex: 0, role: "button", "aria-label": x.title }, s("circle", { class: "hit", r: 21, cx: 18 }), s("path", { class: "blade", d: blade(0, 38, .4) }), s("path", { class: "rib", d: "M2,0 L32,0" })));
        L.leaves.append(el); hook(el, x);
        const land = Math.min(W - 16, Math.max(16, tip[0] + (rand() - .5) * 120));
        leaves.push({ id: x.id, el, twig, angle: a * 57.3 - 90, s: 0, sy: 1, fall: 0, pulse: 0, phase: rand() * 6.28, land: [land, ground(land) - 2], spin: 340 + rand() * 300, n: x });
      });
    }
    const leafOf = Object.fromEntries(leaves.map(l => [l.id, l]));
    for (const r of of("run")) {
      const from = leafOf[above[r.id]];
      if (!from) continue;
      const x = Math.min(W - 12, Math.max(12, from.twig.pts[8][0] + (rand() + rand() - 1) * 110));
      const el = part(r.id, s("g", { class: "leaf litter", transform: "scale(0)", tabindex: 0, role: "button", "aria-label": r.title }, s("circle", { class: "hit", r: 12, cx: 8 }), s("path", { class: "blade", d: blade(0, 17, .36) })));
      L.litter.append(el); hook(el, r);
      litter.push({ id: r.id, el, from, f: 0, phase: rand() * 6.28, land: [x, ground(x) - 1 + rand() * 5], turn: (rand() - .5) * 44, spin: 260 + rand() * 280 });
    }
    for (const n of [...claims, ...methods]) {
      const el = part(n.id, h("button", { type: "button", class: "sprig", dataset: { kind: n.kind }, style: { left: spot[n.id][0] + "px", top: spot[n.id][1] + "px" }, text: n.title }));
      hook(el, n); labels[n.id] = el;
    }

    /* Below ground */
    const bottom = H, depth = i => G + (H - G) * [.0, .32, .66][i], wave = (y, k, amp) => { let d = ""; for (let x = -12; x <= W + 12; x += 16) d += (d ? "L" : "M") + f1(x) + "," + f1(y(x) + Math.sin(x * .017 + k) * amp + Math.sin(x * .043 + k * 2) * amp * .4); return d; };
    [0, 1, 2].forEach(i => L.soil.append(s("path", { class: "soil", dataset: { layer: i }, d: wave(x => i ? depth(i) : ground(x), i * 2.1, i ? 7 : 0) + `L${W + 12},${bottom} L-12,${bottom}Z` })));
    const humus = s("path", { class: "humus" }); L.soil.append(humus);
    [1, 2].forEach(i => L.soil.append(s("path", { class: "seamline", d: wave(() => depth(i), i * 2.1, 7) })));
    const claimX = id => (spot[id] || [cx])[0], mean = n => { const to = [...(gaps[n.id] || [])]; return to.length ? to.reduce((a, id) => a + claimX(id), 0) / to.length : cx; };
    const stacked = Math.ceil(priors.length * 192 / (W * .94)), rockW = Math.min(W * .92 / Math.ceil(priors.length / stacked) - 22, 236), rockH = 62;
    [...priors].sort((a, b) => mean(a) - mean(b)).forEach((n, i) => {
      const y = G + (H - G) * (stacked > 1 ? (i % 2 ? .76 : .42) : .56), x = W * .04 + (i + .5) / priors.length * W * .92, count = all.filter(q => home[q.id] === n.id).length;
      const rock = part(n.id, s("path", { class: "rock", d: pebble(x, y, rockW, rockH, rand) }));
      const label = part(n.id, h("button", { type: "button", class: "stone", style: { left: x + "px", top: y + "px", width: rockW - 24 + "px" } }, h("span", { text: n.title }), count ? h("small", { text: count }) : null));
      L.rocks.append(rock); hook(label, n); labels[n.id] = label;
      rocks[n.id] = { x, y, w: rockW, h: rockH, el: rock };
      const root = limb(n.id, "root", curve(base, [x, y - rockH / 2 + 8], 1), null, 0, 0);
      for (let k = 0; k < 3; k++) {
        const at = .34 + k * .2 + rand() * .08, from = along(root.pts, at), side = rand() < .5 ? -1 : 1, length = 34 + rand() * 46;
        limb(null, "rootlet", curve(from, [from[0] + side * length, from[1] + 12 + rand() * 30], 1, 7), root, at, 0).of = root;
      }
    });
    const clear = (x, y) => Object.values(rocks).every(r => Math.abs(x - r.x) > r.w / 2 + 4 || Math.abs(y - r.y) > r.h / 2 + 4);
    for (const n of of("paper")) {
      const r = rocks[home[n.id]];
      let x, y, tries = 0;
      do {
        x = r ? r.x + (rand() - .5) * (r.w + 46) : 8 + rand() * (W - 16);
        y = r ? r.y + (rand() < .5 ? -1 : 1) * (r.h / 2 + 5 + rand() * 24) : G + 30 + rand() * (H - G - 42);
      } while (!clear(x, y) && ++tries < 12);
      const el = part(n.id, s("circle", { class: "grain" + (r ? " held" : ""), cx: f1(x), cy: f1(y), r: r ? 3.4 : 1.6 + rand() * 1.2 }));
      L.grains.append(el); grains.push({ id: n.id, el, n });
    }
    L.grains.addEventListener("pointerover", ev => { const g = grains.find(q => q.el === ev.target); if (g) { hovering = g.id; tipAt(ev.target, g.n.title); light(g.id); } });
    L.grains.addEventListener("pointerout", ev => { if (ev.target.dataset.id) { hovering = null; hideTip(); rest(); } });
    L.grains.addEventListener("click", ev => { const id = ev.target.dataset.id; if (id) { ev.stopPropagation(); pick(id); } });

    /* The living ground */
    const grass = [];
    for (let x = 10; x < W; x += 15 + rand() * 24) {
      if (Math.abs(x - cx) < 46) continue;
      const tall = 7 + rand() * 13, lean = (rand() - .5) * 9, el = s("path", { class: "grass", d: `M-1.4,0 Q${f1(lean * .3)},${f1(-tall * .6)} ${f1(lean)},${f1(-tall)} Q${f1(lean * .3 + 1.6)},${f1(-tall * .5)} 1.4,0Z` });
      L.grass.append(el); grass.push({ el, x, y: ground(x) + 1, tilt: lean });
    }
    L.seed.append(s("ellipse", { rx: 13, ry: 8.5 }), s("path", { class: "crack", d: "M-9,-1 Q0,-5 9,-1" }));
    const air = Array.from({ length: 16 }, () => { const el = s("circle", { class: "fleck", r: 1 + rand() * 1.5 }); L.air.append(el); return { el, x: rand() * W, y: 40 + rand() * (G - 70), v: 8 + rand() * 12, phase: rand() * 6.28 }; });

    const svg = s("svg", { class: "plantfield", width: W, height: H, viewBox: `0 0 ${W} ${H}`, "aria-hidden": "false" }, Object.values(L));
    const plot = h("div", { class: "plot", style: { width: W + "px", height: H + "px" } }, svg, Object.values(labels));
    const sizer = h("div", { class: "sizer" }, plot), root = h("div", { class: "scroll field", style: { height: frame.h + "px" } }, sizer);
    return { p, frame, small, k, far: false, top: frame.h - H * k, sizer, W, H, G, cx, ground, base, trunk, limbs, limbOf, leaves, leafOf, litter, rocks, labels, grains, grass, air, parts, L, plot, root, humus, hum: 0, grafts: [], seed: { s: 0, y: ground(cx) }, tweens: [], flying: [], motes: [], gust: { at: -99, power: 0, dir: 1 }, nextGust: 3, nextMote: 3.4, day: null, wind: 0 };
  }
  function hook(el, n) {
    const words = () => { const stat = ix().nodes[n.id]?.status; return n.title + (stat ? " · " + (STATUS[stat] || stat) : ""); };
    const tipped = el.tagName !== "BUTTON";
    el.addEventListener("pointerenter", () => { hovering = n.id; light(n.id); if (tipped) tipAt(el, words()); });
    el.addEventListener("pointerleave", () => { hovering = null; hideTip(); rest(); });
    el.addEventListener("focus", () => light(n.id));
    el.addEventListener("blur", rest);
    const act = ev => { ev.stopPropagation(); locked = S.sel === n.id ? null : n.id; pick(n.id); };
    el.addEventListener("click", act);
    if (tipped) el.addEventListener("keydown", ev => { if (ev.key === "Enter") act(ev); });
  }

  /* Time */
  function to(obj, key, value, ms = 0, delay = 0, ease = out) {
    const list = plant.tweens, at = list.findIndex(t => t.obj === obj && t.key === key);
    if (at >= 0) list.splice(at, 1);
    if (!ms || still.matches) { obj[key] = value; return; }
    list.push({ obj, key, from: obj[key], value, begin: performance.now() + delay, ms, ease });
  }
  function show(pace) {
    const st = stateAt(S.day), here = new Map(st.nodes.filter(n => !n.retired).map(n => [n.id, n])), { limbs, limbOf, leaves, litter, labels, rocks, grains, parts } = plant;
    const beat = (tier, i = 0) => (TIER[tier] * 1000 + i * 55) * pace, span = ms => ms * Math.max(pace, .42) * (pace ? 1 : 0);
    for (const l of limbs) { l.next = false; l.load = 0; }
    const feed = l => { for (; l; l = l.parent) { l.next = true; l.load += 1; } };
    const rooted = new Set(st.edges.filter(e => e.rel === "gap" && here.has(e.src)).map(e => e.src));
    for (const n of here.values()) if (["claim", "method", "experiment"].includes(n.kind) && limbOf[n.id]) feed(limbOf[n.id]);
    for (const id of rooted) if (limbOf[id]) { limbOf[id].next = true; limbOf[id].load += 2; }
    limbs.forEach((l, i) => {
      if (l.tier === "rootlet") { l.next = l.of.next; l.load = 1; }
      const thick = Math.sqrt(l.load), heir = Math.sqrt(Math.max(1, ...limbs.filter(c => c.parent === l).map(c => c.load))), wide = l.tier === "trunk" ? [7 + 2.3 * thick, 2.6 + 1.5 * heir] : l.tier === "root" ? [3 + 1.5 * thick, 1] : l.tier === "rootlet" ? [1.3, .3] : l.tier === "twig" ? [1.9, .8] : [2.6 + 1.5 * thick, 1.3 + .7 * thick];
      to(l, "w0", wide[0], span(800)); to(l, "w1", wide[1], span(800));
      if (l.next && !l.want) to(l, "g", 1, span(l.tier === "rootlet" ? 1100 : 1000), beat(l.tier === "rootlet" ? "trunk" : l.tier, i % 7), l.tier === "trunk" ? even : out);
      else if (!l.next && l.want) to(l, "g", 0, span(380), 0, even);
      l.want = l.next;
    });
    leaves.forEach((f, i) => {
      const n = here.get(f.id), stat = n && (n.status || "proposed"), size = n ? LEAF[stat] || [.8, .9] : [0, 1], changed = f.stat !== stat, down = FALLEN.includes(stat);
      if (!changed) return;
      const fresh = !f.stat;
      to(f, "s", size[0], span(fresh ? 950 : 600), fresh ? beat("leaf", i) : 0, back); to(f, "sy", size[1], span(700), fresh ? beat("leaf", i) : 0, out);
      to(f, "fall", down ? 1 : 0, down ? span(3400) : span(350), down ? beat("litter") : 0, flat);
      if (f.stat && !down && n) { f.pulse = 1; to(f, "pulse", 0, span(900), 0, out); }
      f.stat = stat; f.el.dataset.st = stat || "";
      f.el.classList.toggle("shown", !!n);
    });
    let finished = 0;
    litter.forEach((r, i) => {
      const n = here.get(r.id), ended = n && ENDED.includes(n.status);
      if (ended) finished += 1;
      if (ended && !r.ended) { r.el.classList.add("shown"); to(r, "f", 1, span(2600 + (i % 4) * 500), beat("litter", i * 2.2), flat); }
      else if (!ended && r.ended) { to(r, "f", 0, 0); r.el.classList.remove("shown"); }
      r.ended = ended; if (n) r.el.dataset.st = n.status || "";
    });
    to(plant, "hum", finished ? 7 + Math.sqrt(finished) * 5.5 : 0, span(1500), beat("litter"));
    /* A class set on an element that has not been drawn yet would skip its transition, so it waits for its moment in the sequence. */
    const up = (el, on, ms) => {
      clearTimeout(el.due);
      if (el.classList.contains("up") === on) return;
      if (on && pace) el.due = setTimeout(() => el.classList.add("up"), ms); else el.classList.toggle("up", on);
    };
    Object.entries(labels).forEach(([id, el], i) => up(el, here.has(id), beat(type(id) === "prior" ? "root" : type(id), i % 6) + 420 * pace));
    Object.values(rocks).forEach((r, i) => up(r.el, here.has(Object.keys(rocks)[i]), 60 + beat("root", i) * .4));
    grains.forEach((g, i) => up(g.el, here.has(g.id), 60 + (i * 37 % 900) * pace));
    to(plant.seed, "s", 1, span(800), 0, back);
    for (const [id, els] of Object.entries(parts)) for (const el of els) el.classList.toggle("picked", id === S.sel);
  }

  /* Wind: slow swells everywhere, and now and then a gust that crosses the whole field. */
  function breeze(t, x) {
    const g = plant.gust, front = g.dir > 0 ? (t - g.at) * 520 - 200 : plant.W + 200 - (t - g.at) * 520, near = (x - front) / 260;
    return .5 * Math.sin(t * .7 + x * .004) + .28 * Math.sin(t * 1.63 + x * .011 + 1.3) + g.dir * g.power * Math.exp(-near * near);
  }
  function outlineOf(l) {
    const n = l.pts.length - 1, end = l.g * n, full = Math.ceil(end), left = [], right = [], line = [], grow = .45 + .55 * l.g;
    const lift = l.parent ? [l.parent.bx + l.parent.sway * l.at * l.at, l.parent.by] : [0, 0];
    l.bx = lift[0]; l.by = lift[1];
    for (let i = 0; i <= full; i++) {
      const at = Math.min(i, end), k = Math.floor(at), t = at - k, a = l.pts[k], b = l.pts[Math.min(k + 1, n)], u = at / n, push = l.sway * u * u;
      const x = lerp(a[0], b[0], t) + l.bx + push, y = lerp(a[1], b[1], t) + l.by + Math.abs(push) * .12, w = lerp(l.w0, l.w1, u) * grow * (l.g < 1 ? 1 - (at / (end || 1)) ** 3 * .8 : 1) / 2, [nx, ny] = l.nx[k];
      left.push(f1(x + nx * w) + "," + f1(y + ny * w)); right.unshift(f1(x - nx * w) + "," + f1(y - ny * w)); line.push(f1(x) + "," + f1(y));
    }
    l.wood.setAttribute("d", "M" + left.join("L") + "L" + right.join("L") + "Z");
    if (l.sap.classList.contains("on")) l.sap.setAttribute("d", "M" + (l.tier === "root" ? [...line].reverse() : line).join("L"));
  }
  const fallAt = (x0, y0, x1, y1, f, phase, amp) => [lerp(x0, x1, f) + Math.sin(f * 8.5 + phase) * amp * (1 - f), lerp(y0, y1, f ** 1.35)];
  function placeLeaf(f, t) {
    const l = f.twig, n = l.pts.length - 1, end = l.pts[n], g = l.g, wind = breeze(t, end[0]), push = l.sway;
    const tip = along(l.pts, Math.min(g, 1)), x = tip[0] + l.bx + push * g * g, y = tip[1] + l.by, flutter = Math.sin(t * 2.3 + f.phase) * (4 + Math.abs(wind) * 5) + wind * 11;
    const breath = f.stat === "running" ? 1 + Math.sin(t * 2.4) * .06 : 1, size = Math.max(f.s, 0) * (1 + f.pulse * .3) * breath;
    f.tip = [x, y];
    if (f.fall > 0) {
      const [px, py] = fallAt(x, y, f.land[0], f.land[1], f.fall, f.phase, 44);
      f.el.setAttribute("transform", `translate(${f1(px)},${f1(py)}) rotate(${f1(f.angle + flutter * (1 - f.fall) + f.spin * f.fall + Math.sin(f.fall * 8.5 + f.phase) * 40 * (1 - f.fall))}) scale(${size.toFixed(3)},${(size * f.sy * lerp(1, .55, f.fall)).toFixed(3)})`);
    } else f.el.setAttribute("transform", `translate(${f1(x)},${f1(y)}) rotate(${f1(f.angle + flutter)}) scale(${size.toFixed(3)},${(size * f.sy).toFixed(3)})`);
  }
  function placeLitter(r) {
    if (!r.f) return;
    const from = r.from.tip || r.land, [x, y] = fallAt(from[0], from[1], r.land[0], r.land[1], r.f, r.phase, 34), done = r.f >= 1;
    r.el.setAttribute("transform", `translate(${f1(x)},${f1(y)}) rotate(${f1(done ? r.turn : r.turn + r.spin * (1 - r.f) + Math.sin(r.f * 8.5 + r.phase) * 46)}) scale(1,${lerp(1, .62, r.f).toFixed(2)})`);
  }
  function shed(t) {
    const ripe = plant.leaves.filter(f => f.stat === "done" && f.tip && f.s > .5 && f.fall === 0);
    if (!ripe.length || plant.flying.length > 3) return;
    const f = ripe[Math.floor(Math.random() * ripe.length)], x = f.tip[0] + (Math.random() - .5) * 160, el = s("path", { class: "shed", d: blade(0, 15, .36) });
    plant.L.air.append(el);
    plant.flying.push({ el, from: f.tip, land: [x, plant.ground(x) - 1], f: 0, phase: Math.random() * 6.28, spin: 300 + Math.random() * 360, life: 4.6 + Math.random() * 2 });
  }
  function rise(t) {
    const going = plant.leaves.filter(f => ["running", "queued"].includes(f.stat) && f.s > .3);
    if (!going.length) return;
    const leaf = going[Math.floor(Math.random() * going.length)], roots = plant.limbs.filter(l => l.tier === "root" && l.g > .9);
    const trail = [], chain = [];
    for (let l = leaf.twig; l; l = l.parent) chain.unshift(l);
    if (roots.length) trail.push(...[...roots[Math.floor(Math.random() * roots.length)].pts].reverse());
    chain.forEach((l, i) => { const stop = chain[i + 1] ? chain[i + 1].at : 1; trail.push(...l.pts.slice(0, Math.max(2, Math.round(stop * (l.pts.length - 1)) + 1))); });
    const lengths = [0];
    for (let i = 1; i < trail.length; i++) lengths.push(lengths[i - 1] + Math.hypot(trail[i][0] - trail[i - 1][0], trail[i][1] - trail[i - 1][1]));
    const halo = s("circle", { class: "mote halo", r: 7 }), core = s("circle", { class: "mote", r: 2.6 });
    plant.L.graft.append(halo, core);
    plant.motes.push({ halo, core, trail, lengths, at: 0, leaf });
  }
  function moveMote(m, dt) {
    m.at += dt * 300;
    const total = m.lengths[m.lengths.length - 1];
    if (m.at >= total) { m.halo.remove(); m.core.remove(); m.leaf.pulse = 1; to(m.leaf, "pulse", 0, 900); return false; }
    let i = m.lengths.findIndex(v => v > m.at); i = Math.max(i, 1);
    const t = (m.at - m.lengths[i - 1]) / ((m.lengths[i] - m.lengths[i - 1]) || 1), x = lerp(m.trail[i - 1][0], m.trail[i][0], t), y = lerp(m.trail[i - 1][1], m.trail[i][1], t);
    for (const c of [m.halo, m.core]) { c.setAttribute("cx", f1(x)); c.setAttribute("cy", f1(y)); }
    return true;
  }
  function paint(t, dt) {
    const pl = plant, calm = still.matches;
    if (!calm && t > pl.nextGust) { pl.gust = { at: t, power: .9 + Math.random() * 1.3, dir: Math.random() < .75 ? 1 : -1 }; pl.nextGust = t + 7 + Math.random() * 10; setTimeout(() => plant === pl && shed(t), 500 + Math.random() * 900); }
    if (!calm && t > pl.nextMote) { rise(t); pl.nextMote = t + 2.6 + Math.random() * 3.4; }
    for (const l of pl.limbs) {
      if (l.g <= .002) { if (l.drawn) { l.wood.removeAttribute("d"); l.drawn = false; } continue; }
      l.sway = l.bend ? breeze(t, l.pts[l.pts.length - 1][0]) * l.bend : 0;
      outlineOf(l); l.drawn = true;
    }
    for (const f of pl.leaves) if (f.s > .01 || f.fall > 0) placeLeaf(f, t);
    for (const r of pl.litter) placeLitter(r);
    if (pl.hum !== pl.humusAt) { pl.humus.setAttribute("d", humusOf()); pl.humusAt = pl.hum; }
    pl.L.seed.classList.toggle("sprouting", pl.trunk.g > 0 && pl.trunk.g < 1);
    drawGrafts();
    pl.L.seed.setAttribute("transform", `translate(${f1(pl.cx)},${f1(pl.seed.y)}) scale(${pl.seed.s.toFixed(3)})`);
    for (const b of pl.grass) b.el.setAttribute("transform", `translate(${f1(b.x)},${f1(b.y)}) rotate(${f1(breeze(t, b.x) * 13 + Math.sin(t * 1.9 + b.x) * 2)})`);
    for (const a of pl.air) {
      a.x += (a.v + breeze(t, a.x) * 46) * dt; a.y += Math.sin(t * .8 + a.phase) * 6 * dt;
      if (a.x > pl.W + 6) a.x = -6; else if (a.x < -6) a.x = pl.W + 6;
      a.el.setAttribute("cx", f1(a.x)); a.el.setAttribute("cy", f1(a.y));
    }
    pl.flying = pl.flying.filter(q => {
      q.f += dt / q.life;
      const [x, y] = fallAt(q.from[0], q.from[1], q.land[0], q.land[1], Math.min(q.f, 1), q.phase, 42);
      q.el.setAttribute("transform", `translate(${f1(x)},${f1(y)}) rotate(${f1(q.spin * q.f + Math.sin(q.f * 8.5 + q.phase) * 44)})`);
      q.el.style.opacity = q.f > 1 ? Math.max(0, 1 - (q.f - 1) * 7) : 1;
      if (q.f > 1.15) { q.el.remove(); return false; }
      return true;
    });
    pl.motes = pl.motes.filter(m => moveMote(m, dt));
  }
  const tipOf = l => { const q = l.pts[l.pts.length - 1]; return [q[0] + l.bx + l.sway, q[1] + l.by + Math.abs(l.sway) * .12]; };
  function drawGrafts() {
    for (const g of plant.grafts) {
      const a = tipOf(g.from), b = g.leaf?.tip || tipOf(g.to), mid = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2 - Math.min(34, Math.hypot(b[0] - a[0], b[1] - a[1]) * .16)];
      g.el.setAttribute("d", `M${a.map(f1)} Q${mid.map(f1)} ${b.map(f1)}`);
    }
  }
  function humusOf() {
    const { W, ground, hum } = plant;
    if (hum < .4) return "";
    let top = "", under = "";
    for (let x = -12; x <= W + 12; x += 16) { top += (top ? "L" : "M") + x + "," + f1(ground(x)); under = `L${x},${f1(ground(x) + hum + Math.sin(x * .023) * hum * .22)}` + under; }
    return top + under + "Z";
  }
  function tick(now) {
    if (!plant?.root.isConnected || still.matches) { ticking = false; return; }
    requestAnimationFrame(tick);
    if (now - last < 30) return;
    const dt = Math.min((now - last) / 1000, .06);
    last = now;
    plant.tweens = plant.tweens.filter(w => {
      if (now < w.begin) return true;
      const k = Math.min((now - w.begin) / w.ms, 1);
      w.obj[w.key] = lerp(w.from, w.value, w.ease(k));
      return k < 1;
    });
    paint(now / 1000, dt);
  }
  function wake() {
    if (still.matches) {
      if (plant) { for (const w of plant.tweens) w.obj[w.key] = w.value; plant.tweens = []; paint(1, 0); }
      return;
    }
    if (!ticking) { ticking = true; last = performance.now(); requestAnimationFrame(tick); }
  }

  /* Reading it: touching any part lights everything it stands on and everything that stands on it. */
  function reach(ties, id, from, end) {
    const found = new Set([id]), todo = [id];
    while (todo.length) { const x = todo.pop(); for (const e of ties) if (e[from] === x && !found.has(e[end])) { found.add(e[end]); todo.push(e[end]); } }
    return found;
  }
  function light(id) {
    if (!plant) return;
    const ties = ix().st.edges.filter(e => TIES.includes(e.rel)), up = reach(ties, id, "dst", "src"), down = reach(ties, id, "src", "dst"), lit = new Set([...up, ...down]);
    plant.plot.classList.add("focus");
    for (const [key, els] of Object.entries(plant.parts)) for (const el of els) el.classList.toggle("on", lit.has(key));
    for (const l of plant.limbs) {
      let on = l.id ? lit.has(l.id) : l.tier === "trunk" ? [...lit].some(k => ["claim", "prior", "method"].includes(type(k))) : l.of ? lit.has(l.of.id) : false;
      if (on && l.g < .5) on = false;
      l.wood.classList.toggle("on", on); l.sap.classList.toggle("on", on);
    }
    clearGrafts();
    for (const e of ties) {
      if (!["realized_by", "tested_by"].includes(e.rel) || !(up.has(e.dst) && up.has(e.src) || down.has(e.dst) && down.has(e.src))) continue;
      const from = plant.limbOf[e.src], end = plant.limbOf[e.dst];
      if (!from || !end || end.parent === from || from.g < .9 || end.g < .9) continue;
      const el = s("path", { class: "graft" });
      plant.L.graft.append(el); plant.grafts.push({ el, from, to: end, leaf: plant.leafOf[e.dst] });
    }
    drawGrafts();
  }
  function clearGrafts() { for (const g of plant.grafts) g.el.remove(); plant.grafts = []; }
  function rest() {
    if (!plant) return;
    const keep = hovering || (locked && S.sel === locked ? locked : null);
    if (keep) return light(keep);
    plant.plot.classList.remove("focus");
    for (const el of plant.plot.querySelectorAll(".on")) el.classList.remove("on");
    clearGrafts();
  }

  /* The drawer narrows the page but never reshapes the plant: the view pans to what was picked, the way a map does. */
  function pan() {
    const pl = plant, el = pl.parts[S.sel]?.[0];
    if (!el || pl.far || !pl.root.isConnected) return;
    const box = pl.root.getBoundingClientRect(), edge = document.querySelector(".drawer")?.getBoundingClientRect().left ?? box.right, right = Math.min(box.right, edge), r = el.getBoundingClientRect(), x = r.left + r.width / 2;
    if (x > box.left + 90 && x < right - 90) return;
    pl.sizer.style.paddingRight = box.right - right + "px";
    to(pl.root, "scrollLeft", pl.root.scrollLeft + x - (box.left + right) / 2, 620, 0, even);
  }
  /* On a phone the whole plant fits the screen; a tap goes in to where it landed and a tap on open ground comes back. */
  const distant = pl => `translate(${pl.root.scrollLeft}px,${pl.root.scrollTop + pl.top}px) scale(${pl.k})`;
  function settle(pl, far) {
    pl.far = far;
    pl.plot.classList.toggle("far", far);
    pl.sizer.style.width = (far ? pl.frame.w : pl.W) + "px"; pl.sizer.style.height = (far ? pl.frame.h : pl.H) + "px";
    pl.plot.style.transform = far ? `translate(0px,${pl.top}px) scale(${pl.k})` : "none";
    if (far) pl.root.scrollTo(0, 0);
  }
  function zoom(pl, x, y) {
    const duration = still.matches ? 0 : 460, easing = "cubic-bezier(.2, .8, .2, 1)";
    if (x == null) return pl.plot.animate([{ transform: "none" }, { transform: distant(pl) }], { duration, easing }).finished.then(() => settle(pl, true));
    settle(pl, false);
    pl.root.scrollLeft = x - pl.root.clientWidth / 2; pl.root.scrollTop = y - pl.root.clientHeight / 2;
    pl.plot.animate([{ transform: distant(pl) }, { transform: "none" }], { duration, easing });
  }
  function fit(pl) {
    settle(pl, true);
    pl.root.addEventListener("click", ev => {
      if (pl.far) { const r = pl.plot.getBoundingClientRect(); ev.stopPropagation(); zoom(pl, (ev.clientX - r.left) / pl.k, (ev.clientY - r.top) / pl.k); }
      else if (!ev.target.closest("button, .leaf, .grain")) zoom(pl);
    }, true);
  }

  function watch() {
    if (watching) return;
    watching = true;
    still.addEventListener("change", wake);
    new ResizeObserver(() => { clearTimeout(wait); wait = setTimeout(() => { if (S.view === "graph" && S.day) renderContent(); }, 200); }).observe($("content"));
  }
  return function () {
    watch();
    const p = P(), box = $("content"), frame = { w: Math.round(innerWidth - box.getBoundingClientRect().left), h: box.clientHeight };
    if (!p.days.some(d => p.states[d].nodes.some(n => SHOWN.includes(n.kind)))) return h("p", { class: "empty", text: "这一天还没有论证" });
    const same = plant && plant.p === p && plant.frame.w === frame.w && plant.frame.h === frame.h;
    if (!same) {
      plant = build(p, frame);
      const fresh = plant;
      if (fresh.small) fit(fresh);
      else { settle(fresh, false); requestAnimationFrame(() => { fresh.root.scrollLeft = (fresh.W - frame.w) / 2; fresh.root.scrollTop = fresh.H; }); }
    }
    const first = !grown.has(p), moved = plant.day && plant.day !== S.day;
    grown.add(p);
    show(first ? 1 : moved ? .34 : 0);
    plant.day = S.day;
    wake();
    requestAnimationFrame(rest);
    if (S.sel && S.sel !== shownSel) setTimeout(pan, 360);
    shownSel = S.sel;
    if (!S.sel) plant.sizer.style.paddingRight = "";
    return plant.root;
  };
})();
