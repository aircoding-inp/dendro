/* The views and the drawer. Each view is one way to read the project as it stood at the end of the chosen day. */
const STATUS = { proposed: "待确认", approved: "已批准", queued: "排队", running: "进行中", done: "已完成", failed: "失败", stopped: "已停止", deferred: "后置", dropped: "放弃" };
const TYPE = { said: "原话", idea: "想法", direction: "指示", correction: "纠正", decision: "决定", design: "设计", survey: "调研", "run.start": "开始", "run.end": "结束", result: "结果", reading: "解读", commit: "提交", change: "改动", digest: "日记", profile: "画像", text: "论文", note: "记要", reply: "回复", problem: "问题", resolved: "了结", release: "发布", reference: "参考", ticket: "工单", check: "检查", output: "产出" };
const KINDS = { claim: "论点", prior: "已有工作", paper: "论文", method: "方法", experiment: "实验", run: "运行", resource: "算力", section: "章节" };
const WORDS = {
  research: { kind: {}, view: {} },
  software: { kind: { claim: "目标", prior: "参考", paper: "参考", method: "方案", experiment: "验证", section: "文档" }, view: { graph: "脉络", runs: "验证", paper: "文档", works: "参考", resources: "环境" } },
  work: { kind: { claim: "目标", prior: "资料", paper: "资料", method: "做法", experiment: "任务", section: "文稿" }, view: { graph: "脉络", runs: "任务", paper: "文稿", works: "资料", resources: "资源" } },
  other: { kind: { claim: "目标", prior: "参考", paper: "参考", method: "方法", experiment: "尝试", section: "文稿" }, view: { graph: "脉络", runs: "尝试", paper: "文稿", works: "参考", resources: "资源" } },
};
const OUTPUT = { report: "报告", slides: "演示", speech: "讲稿", weekly: "周报", thread: "脉络" };
const REFERENCE = { paper: "文献", repository: "仓库", dependency: "依赖" };
const OUTCOMES = { solved: "解决", dropped: "放弃" };
const BASIS = { record: "记录", inferred: "推断", unknown: "未知" };
const TURNS = ["direction", "decision", "correction", "idea", "problem", "resolved", "result", "release"];
const latest = (project, type) => { const rows = project.events.filter(e => e.type === type); return rows[rows.length - 1]; };
const hasNodes = (project, kinds) => project.days.some(d => project.states[d].nodes.some(n => kinds.includes(n.kind)));
const familyOf = project => latest(project, "profile")?.body.data.family || (hasNodes(project, ["claim"]) ? "research" : "other");
let KIND = KINDS;
const RELATION = { gap: ["留下缺口给", "缺口来自"], covers: ["包含", "归类于"], realized_by: ["由它实现", "实现"], tested_by: ["由它取证", "取证"], of: ["属于实验", "运行"], on: ["跑在", "承载"], states: ["陈述", "陈述于"], cites: ["引用", "被引用于"] };
const FIELD = { question: "回答的问题", scale: "规模", until: "何时", authors: "作者", year: "年份", venue: "发表", arxiv: "arXiv", doi: "DOI", url: "链接", task: "任务", program: "程序", program_name: "程序名", instances: "实例数", partition: "实例集", prompt: "提示词", execution: "执行", environment: "环境", checkpoint: "模型权重", executor: "执行器", code: "代码版本", job_dir: "作业目录", log: "日志路径", fidelity: "精度档", generation_seconds: "生成用时（秒）", seconds_per_sample: "每条（秒）", peak_memory_gb: "峰值显存（GB）", qualified: "合格", samples: "样本", metrics: "指标", violations: "违反量", failures: "失败", invalid: "无效", host: "主机", gpu: "GPU", gpu_uuid: "GPU 编号", role: "用途", hardware: "硬件", limit: "限制", file: "文件", words: "词数", todos: "待填", cites: "引用数", backing: "依据", hash: "哈希", author: "作者", files: "文件数", insertions: "新增行", deletions: "删除行", paths: "文件", outcome: "结局", seeds: "种子数", scores: "分数文件", version: "版本", kind: "类别", state: "状态", number: "编号", workflow: "流程", branch: "分支", note: "说明", cut: "省略字数", day: "日期", audience: "读者", bytes: "字节" };
const FILTERS = [["all", "全部", () => true], ["human", "人", e => e.actor && e.actor.kind === "human"], ["agent", "回复", e => e.type === "reply"], ["result", "结果", e => ["result", "reading", "survey"].includes(e.type)], ["problem", "问题", e => e.type === "problem" || e.type === "resolved"], ["run", "运行", e => e.type === "run.start" || e.type === "run.end"], ["code", "代码", e => ["commit", "change", "release", "ticket", "check"].includes(e.type)], ["graph", "图", e => e.group]];
const STRUCTURAL = ["node.put", "node.retire", "edge.put", "edge.drop"], READS = ["idea", "direction", "correction", "decision"];
const HIDDEN = ["sections", "facts", "missing", "family", "pasted", "text", "key", "entry", "order", "parent", "level", "notes", "figures", "figure", "log_file", "reserved"];
const OUTCOME = ["fidelity", "generation_seconds", "seconds_per_sample", "peak_memory_gb", "qualified", "samples", "metrics", "violations", "failures", "invalid", "outcome"];
const BACKING = { L: "文献", M: "实测", H: "假设", C: "共识" };

const fmt = v => typeof v === "number" ? (Number.isInteger(v) ? String(v) : Math.abs(v) < .001 && v !== 0 ? v.toExponential(2) : String(+v.toPrecision(4))) : String(v);
const seconds = t => t == null ? "" : t >= 3600 ? (t / 3600).toFixed(1) + " 时" : t >= 60 ? Math.round(t / 60) + " 分" : Math.round(t) + " 秒";
const clock = t => { const d = new Date(t); return String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0"); };
const stateAt = day => P().states[day] || { nodes: [], edges: [] };
const blobUrl = name => "blob/" + encodeURIComponent(P().project) + "/" + name;
const point = ev => ({ getBoundingClientRect: () => ({ left: ev.clientX, right: ev.clientX, top: ev.clientY, bottom: ev.clientY, width: 0, height: 0 }) });
const status = (st, label = true) => h("span", { class: "st", dataset: { st } }, glyph(st), label && h("span", { text: STATUS[st] || st }));
const chip = type => h("span", { class: "chip", dataset: { type }, text: TYPE[type] || type });

let memo = {};
function ix() {
  const key = S.project + "|" + S.day;
  if (memo.key === key && memo.data === S.data) return memo;
  const st = stateAt(S.day), nodes = Object.fromEntries(st.nodes.map(n => [n.id, n])), events = Object.fromEntries(P().events.map(e => [e.id, e]));
  const reads = {}, numbers = {};
  for (const e of P().events) {
    if (e.day > S.day) continue;
    if (READS.includes(e.type)) for (const r of e.refs || []) if (r.rel === "based_on") (reads[r.to] ||= []).push(e);
    const quote = e.type === "reading" && e.body.data && e.body.data.quote;
    if (quote) for (const id of e.about || []) if (id.startsWith("section:")) (numbers[id] ||= []).push(e);
  }
  memo = { key, data: S.data, st, nodes, events, reads, numbers };
  return memo;
}
const live = kind => ix().st.nodes.filter(n => n.kind === kind && !n.retired);
const linked = (id, rel, end) => ix().st.edges.filter(e => e.rel === rel && e[end] === id).map(e => ix().nodes[end === "src" ? e.dst : e.src]).filter(Boolean);
const dayBefore = () => P().days.filter(d => d < S.day).pop();

/* Year rings: the overview */
function evidenceOf(claim) {
  const out = new Map();
  for (const x of linked(claim.id, "tested_by", "src")) out.set(x.id, x);
  for (const m of linked(claim.id, "realized_by", "src")) for (const x of linked(m.id, "tested_by", "src")) out.set(x.id, x);
  return [...out.values()];
}
function markText(e) {
  if (e.body.text) return e.body.text;
  if (e.type === "node.put") return (ix().nodes[e.body.id] || {}).title || e.body.id;
  return e.body.src ? e.body.src + " → " + e.body.dst : e.type;
}
const digestOf = day => P().events.filter(e => e.type === "digest" && e.body.data.day === day).pop();
function issues(day) {
  const out = {};
  for (const e of P().events) if (e.type === "problem" && e.day <= day) out[e.id] = { event: e, ended: null };
  for (const e of P().events) if (e.type === "resolved" && e.day <= day) for (const r of e.refs || []) if (r.rel === "responds_to" && out[r.to]) out[r.to].ended = e;
  return Object.values(out);
}
function ringsView() {
  const day = P().events.filter(e => e.day === S.day && !UNDATED.includes(e.type)), before = dayBefore(), sections = live("section");
  const words = sections.reduce((n, x) => n + (x.data.words || 0), 0), todos = sections.reduce((n, x) => n + (x.data.todos || 0), 0);
  const was = before ? stateAt(before).nodes.filter(n => n.kind === "section").reduce((n, x) => n + (x.data.words || 0), 0) : 0;
  const runs = live("run"), done = runs.filter(n => n.status === "done").length, spoken = day.filter(e => e.actor.kind === "human" && e.type !== "said").slice(-3).reverse();
  const on = {
    day: setDay, leave: hideTip,
    ringTip: (ev, ring) => tipAt(point(ev), dated(ring.day) + " · " + ring.count + " 条"),
    markTip: (ev, id) => { const e = ix().events[id]; tipAt(ev.target, (TYPE[e.type] ? TYPE[e.type] + " · " : "") + markText(e).slice(0, 72)); },
    event: id => { const e = ix().events[id]; if (!STRUCTURAL.includes(e.type)) return pick(id); if (ix().nodes[e.body.id]) pick(e.body.id); },
  };
  const profile = latest(P(), "profile"), digest = digestOf(S.day), open = issues(S.day).filter(x => !x.ended), output = latest(P(), "output");
  const stat = (n, label, extra) => h("div", { class: "stat" }, h("b", { text: n }), h("span", { text: label }), extra && h("em", { text: extra }));
  return h("div", { class: "overview" },
    h("div", { class: "trunk" }, crossSection(P(), S.day, 820, on)),
    h("div", { class: "ledger" },
      profile && h("button", { type: "button", class: "intro", onclick: () => pick(profile.id) }, profile.body.text),
      h("div", { class: "stats" }, stat(day.filter(e => !STRUCTURAL.includes(e.type)).length, "今日记录"), open.length ? stat(open.length, "未解决") : null, runs.length ? stat(done + "/" + runs.length, "运行") : null, words ? stat(words.toLocaleString(), "词", was && words !== was ? (words > was ? "+" : "") + (words - was) : null) : null, todos ? stat(todos, "待填") : null),
      digest && h("button", { type: "button", class: "digest", onclick: () => pick(digest.id) }, digest.body.text),
      open.length ? h("section", null, h("h2", { text: "未解决" }), open.slice(-3).reverse().map(x => h("button", { type: "button", class: "knot", onclick: () => pick(x.event.id) }, x.event.body.text))) : null,
      live("claim").length ? h("section", null, h("h2", { text: KIND.claim }), h("ul", { class: "claims" }, live("claim").map(c => h("li", null,
        h("button", { type: "button", class: "claim", onclick: () => pick(c.id) }, c.title),
        h("div", { class: "evidence" }, evidenceOf(c).map(x => h("button", { type: "button", "aria-label": x.title, onclick: () => pick(x.id), onmouseenter: ev => tipAt(ev.currentTarget, x.title + " · " + (STATUS[x.status] || "")), onmouseleave: hideTip }, glyph(x.status, 20)))))))) : null,
      spoken.length ? h("section", null, h("h2", { text: "这一天的话" }), spoken.map(e => h("button", { type: "button", class: "spoken", onclick: () => pick(e.id) }, h("q", { text: e.body.text }), chip(e.type)))) : null,
      output && h("button", { type: "button", class: "made", onclick: () => go({ view: "outputs", section: output.id, sel: null }) }, h("span", { text: OUTPUT[output.body.data.kind] }), h("b", { text: output.body.text }))));
}

/* What stands in the way */
function problemsView() {
  const all = issues(S.day), open = all.filter(x => !x.ended).reverse(), ended = all.filter(x => x.ended).reverse();
  if (!all.length) return h("p", { class: "empty", text: "这一天还没有问题" });
  const when = e => e.day.slice(5).replace("-", ".");
  return h("div", { class: "issues" },
    open.length ? h("ul", { class: "open" }, open.map(({ event: e }) => h("li", null, h("button", { type: "button", class: "issue" + (e.id === S.sel ? " picked" : ""), onclick: () => pick(e.id) }, h("p", { text: e.body.text }), h("time", { text: when(e) }))))) : null,
    ended.length ? h("ul", { class: "ended" }, ended.map(({ event: e, ended: r }) => h("li", null, h("button", { type: "button", class: "closed" + (e.id === S.sel ? " picked" : ""), dataset: { outcome: r.body.data.outcome }, onclick: () => pick(e.id) },
      h("span", { class: "was", text: e.body.text }), h("span", { class: "how", text: r.body.text }), h("time", { text: when(r) + " " + OUTCOMES[r.body.data.outcome] }))))) : null);
}

/* The turns of the work, for a project with no argument to draw */
function turnsView() {
  const rows = P().events.filter(e => TURNS.includes(e.type) && e.day <= S.day).reverse();
  if (!rows.length) return h("p", { class: "empty", text: "还没有转折" });
  const days = [...new Set(rows.map(e => e.day))];
  return h("div", { class: "record turns" }, days.map(d => h("section", null, h("h2", { text: dated(d) }), h("ol", { class: "timeline" }, rows.filter(e => e.day === d).map(e =>
    h("li", { class: "ev" + (e.id === S.sel ? " picked" : ""), dataset: { type: e.type, by: e.actor.kind }, tabindex: "0", onclick: () => pick(e.id), onkeydown: ev => { if (ev.key === "Enter") pick(e.id); } },
      h("time", { text: e.time }), h("div", null, h("div", { class: "ev-head" }, chip(e.type), e.actor.kind === "human" && h("span", { class: "who", text: e.actor.name })), h("p", { text: e.body.text }))))))));
}
function argumentView() { return hasNodes(P(), ["claim", "method", "prior", "experiment"]) ? graphView() : turnsView(); }

/* What was written from the trace */
function sources(section, anchor) {
  popAt(anchor, h("div", { class: "sources" }, (section.files || []).map(f => h("a", { class: "kept", href: blobUrl(f.blob), target: "_blank", rel: "noopener", text: f.path })), (section.evidence || []).map(id => ix().events[id]).filter(Boolean).map(brief)), "below");
}
function outputsView() {
  const gone = new Set(P().events.flatMap(e => e.type === "output" ? (e.refs || []).filter(r => r.rel === "supersedes").map(r => r.to) : []));
  const rows = P().events.filter(e => e.type === "output" && !gone.has(e.id)).reverse();
  if (!rows.length) return h("p", { class: "empty", text: "还没有产出" });
  const current = rows.find(e => e.id === S.section) || rows[0], d = current.body.data, kinds = [...new Set(rows.map(e => e.body.data.kind))];
  const newer = P().events.filter(e => !UNDATED.includes(e.type) && !STRUCTURAL.includes(e.type) && e.ts > current.ts).length;
  const part = (x, i) => h("section", { class: d.kind === "slides" ? "slide" : "part" },
    h("h3", { text: x.heading }), h("p", { text: x.text }),
    h("button", { type: "button", class: "backed", "aria-label": "依据", onclick: ev => { ev.stopPropagation(); sources(x, ev.currentTarget); } }, (x.evidence || []).length + (x.files || []).length),
    d.kind === "slides" && h("span", { class: "folio", text: i + 1 }));
  return h("div", { class: "paper made-view" },
    h("nav", { class: "outline", "aria-label": "目录" }, h("ul", null, kinds.flatMap(k => [h("li", { class: "group", text: OUTPUT[k] }), ...rows.filter(e => e.body.data.kind === k).map(e =>
      h("li", null, h("button", { type: "button", "aria-current": e.id === current.id ? "true" : null, onclick: () => { go({ section: e.id, sel: null }); $("content").scrollTop = 0; } }, h("span", { text: e.body.text }))))]))),
    h("article", { class: "page", dataset: { kind: d.kind } }, h("header", null, h("h2", { text: current.body.text }),
      h("div", { class: "page-meta" }, d.audience && h("span", { text: d.audience }), h("span", { text: dated(current.day) }), newer ? h("span", { class: "due", text: "之后 " + newer + " 条新记录" }) : null,
        d.file && h("a", { class: "plain under", href: blobUrl(d.file.blob), download: d.file.name, text: d.file.name }))), d.sections.map(part)));
}

/* What the project builds on */
function referencesBlock(kinds) {
  const q = S.q.trim().toLowerCase(), named = new Map();
  for (const e of P().events) if (e.type === "reference" && kinds.includes(e.body.data.kind) && (!q || e.body.text.toLowerCase().includes(q))) named.set(e.body.data.kind + e.body.text.toLowerCase(), e);
  const rows = [...named.values()];
  return kinds.map(k => { const mine = rows.filter(e => e.body.data.kind === k).sort((a, b) => a.body.text.localeCompare(b.body.text)); return mine.length ? h("section", { class: "year" }, h("h2", null, REFERENCE[k], h("span", { text: mine.length })), h("ul", { class: "named" }, mine.map(e =>
    h("li", null, h("button", { type: "button", class: "work" + (e.id === S.sel ? " picked" : ""), onclick: () => pick(e.id) }, h("span", { class: "work-title", text: e.body.text }), h("span", { class: "work-meta", text: [e.body.data.version, e.body.data.year, e.body.data.venue].filter(Boolean).join(" · ") })))))) : null; });
}

/* Record */
function grouped(events) {
  const out = [], known = new Set(P().events.filter(e => e.day < S.day && e.type === "node.put").map(e => e.body.id)), said = new Set();
  let run = null;
  for (const e of events) {
    if (READS.includes(e.type) && (e.refs || []).some(r => r.rel === "based_on" && ix().events[r.to]?.type === "said" && ix().events[r.to].day === S.day)) continue;
    if (!STRUCTURAL.includes(e.type)) { run = null; out.push(e); continue; }
    if (!run || run.writer !== e.writer) { run = { group: true, time: e.time, writer: e.writer, actor: e.actor, counts: {} }; out.push(run); }
    const kind = (e.body.id || e.body.src || "").split(":")[0], fresh = e.type === "node.put" && !known.has(e.body.id);
    if (e.type === "node.put") known.add(e.body.id);
    const key = fresh ? "new:" + kind : e.type === "node.put" ? "changed:" + kind : e.type;
    run.counts[key] = (run.counts[key] || 0) + 1;
  }
  return out;
}
function summary(counts) {
  return Object.entries(counts).map(([key, n]) => key.startsWith("new:") ? `新增 ${n} 个${KIND[key.slice(4)] || key.slice(4)}` : key.startsWith("changed:") ? `更新 ${n} 次${KIND[key.slice(8)] || "节点"}`
    : { "node.retire": `退役 ${n} 个节点`, "edge.put": `连 ${n} 条边`, "edge.drop": `断 ${n} 条边` }[key]).join("，");
}
function logView() {
  const all = grouped(P().events.filter(e => e.day === S.day && !UNDATED.includes(e.type))), q = S.q.trim().toLowerCase(), pass = FILTERS.find(f => f[0] === S.filter)[2];
  const rows = all.filter(e => pass(e) && (!q || (e.group ? summary(e.counts) : e.body.text + " " + e.actor.name).toLowerCase().includes(q)));
  const chips = h("div", { class: "chips" }, FILTERS.map(([key, label, test]) => { const n = all.filter(test).length; return (key === "all" || n) ? h("button", { type: "button", "aria-pressed": String(S.filter === key), onclick: () => { S.filter = key; renderContent(); } }, label, h("span", { text: n })) : null; }));
  const row = e => {
    if (e.group) return h("li", { class: "ev quiet" }, h("time", { text: e.time }), h("p", { text: summary(e.counts) }));
    const reads = ix().reads[e.id] || [], about = (e.about || []).map(id => ix().nodes[id]).filter(Boolean).filter(n => n.kind !== "run");
    return h("li", { class: "ev" + (e.id === S.sel ? " picked" : ""), dataset: { type: e.type, by: e.actor.kind }, tabindex: "0", onclick: () => pick(e.id), onkeydown: ev => { if (ev.key === "Enter") pick(e.id); } },
      h("time", { text: e.time }),
      h("div", null,
        !["said", "commit"].includes(e.type) && h("div", { class: "ev-head" }, chip(e.type), e.actor.kind === "human" && h("span", { class: "who", text: e.actor.name })),
        e.type === "commit" ? h("p", { class: "commit" }, h("code", { text: (e.source?.id || "").slice(0, 7) }), e.body.text) : h("p", { class: e.type === "said" ? "voice" : null, text: e.body.text }),
        reads.map(r => h("div", { class: "read", onclick: ev => { ev.stopPropagation(); pick(r.id); } }, chip(r.type), h("span", { text: r.body.text }))),
        about.length ? h("div", { class: "about" }, about.map(n => h("span", { text: n.title }))) : null));
  };
  return h("div", { class: "record" }, chips, rows.length ? h("ol", { class: "timeline" }, rows.map(row)) : h("p", { class: "empty", text: "没有符合的记录" }));
}

/* Experiments and runs */
function gauge(a, b, size = 30) {
  const r = 12, c = 2 * Math.PI * r, share = b ? a / b : 0;
  return s("svg", { class: "gauge", viewBox: "0 0 30 30", width: size, height: size, "aria-hidden": "true" }, s("circle", { cx: 15, cy: 15, r, class: "gauge-bg" }),
    s("circle", { cx: 15, cy: 15, r, class: "gauge-on", "stroke-dasharray": `${(share * c).toFixed(1)} ${c.toFixed(1)}`, transform: "rotate(-90 15 15)" }));
}
const RUN_COLUMNS = [
  ["运行", n => n.title, n => n.title], ["实验", n => (linked(n.id, "of", "src")[0] || {}).title || "", n => (linked(n.id, "of", "src")[0] || {}).title || ""],
  ["开始", n => n.since, n => n.since.slice(5, 10).replace("-", ".") + " " + clock(n.since)], ["用时", n => n.data.generation_seconds, n => seconds(n.data.generation_seconds)],
  ["每条", n => n.data.seconds_per_sample, n => n.data.seconds_per_sample != null ? n.data.seconds_per_sample + " 秒" : ""], ["显存", n => n.data.peak_memory_gb, n => n.data.peak_memory_gb != null ? n.data.peak_memory_gb + " GB" : ""],
  ["合格", n => n.data.qualified != null ? n.data.qualified / n.data.samples : null, n => n.data.qualified != null ? h("span", { class: "fit" }, gauge(n.data.qualified, n.data.samples, 22), n.data.qualified + "/" + n.data.samples) : ""],
];
function runsView() {
  const q = S.q.trim().toLowerCase(), match = n => !q || (n.title + " " + (n.summary || "") + " " + (n.data.question || "")).toLowerCase().includes(q);
  const results = {};
  for (const e of P().events) if (e.day <= S.day && e.type === "result") for (const id of e.about || []) results[id] = e;
  const lanes = [["在做", ["running", "queued", "approved"]], ["待定", ["proposed", "deferred"]], ["已结", ["done", "failed", "stopped", "dropped"]]];
  const list = live("experiment").filter(match);
  const card = n => {
    const count = linked(n.id, "of", "dst").length;
    return h("button", { type: "button", class: "lab" + (n.id === S.sel ? " picked" : ""), dataset: { st: n.status }, onclick: () => pick(n.id) },
      h("span", { class: "lab-top" }, glyph(n.status, 18), h("b", { text: n.title })), n.data.question && h("span", { class: "lab-q", text: n.data.question }),
      h("span", { class: "lab-foot" }, n.data.scale && h("span", { text: n.data.scale }), count ? h("span", { text: count + " 次运行" }) : null));
  };
  let runs = live("run").filter(match);
  const sort = S.sort || { at: 2, dir: -1 }, get = RUN_COLUMNS[sort.at][1];
  runs = runs.slice().sort((a, b) => { const x = get(a), y = get(b); if (x == null) return 1; if (y == null) return -1; return (x < y ? -1 : x > y ? 1 : 0) * sort.dir; });
  const toggle = id => { S.picks = S.picks.includes(id) ? S.picks.filter(x => x !== id) : [...S.picks, id].slice(-4); renderContent(); };
  return h("div", { class: "experiments" },
    h("div", { class: "lanes" }, lanes.map(([label, states]) => { const mine = list.filter(n => states.includes(n.status)); return mine.length ? h("section", { class: "lane" }, h("h2", null, label, h("span", { text: mine.length })), mine.map(card)) : null; })),
    runs.length ? h("section", { class: "runs" }, h("div", { class: "runs-head" }, h("h2", { text: "运行" }), S.picks.length > 1 && h("button", { type: "button", class: "action", onclick: () => compare(S.picks) }, "对比 " + S.picks.length + " 次")),
      h("div", { class: "table-wrap" }, h("table", { class: "grid" },
        h("thead", null, h("tr", null, h("th"), RUN_COLUMNS.map(([label], i) => h("th", { class: i > 1 ? "num" : null, "aria-sort": sort.at === i ? (sort.dir > 0 ? "ascending" : "descending") : null, onclick: () => { S.sort = { at: i, dir: sort.at === i ? -sort.dir : -1 }; renderContent(); } }, label)))),
        h("tbody", null, runs.map(n => h("tr", { class: n.id === S.sel ? "picked" : null, onclick: () => pick(n.id) },
          h("td", { class: "tick", onclick: ev => { ev.stopPropagation(); toggle(n.id); } }, h("input", { type: "checkbox", checked: S.picks.includes(n.id), "aria-label": "选中" }), glyph(n.status, 18)),
          RUN_COLUMNS.map(([, , show], i) => h("td", { class: i > 1 ? "num" : i === 0 ? "lead" : "dim" }, show(n))))))))) : null);
}
function flat(data, prefix = "", out = {}) {
  for (const [k, v] of Object.entries(data || {})) {
    if (HIDDEN.includes(k) || ["log", "job_dir", "scores"].includes(k)) continue;
    const label = prefix ? prefix + " · " + k : FIELD[k] || k;
    if (v && typeof v === "object" && !Array.isArray(v)) flat(v, label, out); else out[label] = Array.isArray(v) ? v.join("，") : v;
  }
  return out;
}
function compare(ids) {
  const runs = ids.map(id => ix().nodes[id]).filter(Boolean), cells = runs.map(n => flat(n.data)), keys = [...new Set(cells.flatMap(Object.keys))];
  const differs = k => new Set(cells.map(c => String(c[k]))).size > 1, diff = keys.filter(differs), same = keys.filter(k => !differs(k));
  const line = k => h("tr", null, h("th", { text: k }), cells.map(c => h("td", { text: c[k] == null ? "" : fmt(c[k]) })));
  openModal(h("div", { class: "compare" }, h("header", null, h("h2", { text: "对比" }), h("button", { type: "button", class: "ghost", "aria-label": "关闭", onclick: closeModal }, icon("close"))),
    h("div", { class: "table-wrap" }, h("table", { class: "grid sheet" }, h("thead", null, h("tr", null, h("th"), runs.map(n => h("th", { text: n.title })))), h("tbody", null, diff.map(line)))),
    same.length ? h("details", null, h("summary", { text: "相同 " + same.length + " 项" }), h("table", { class: "grid sheet" }, h("tbody", null, same.map(k => h("tr", null, h("th", { text: k }), h("td", { text: fmt(cells[0][k]) })))))) : null), true);
}

/* Paper */
function balanced(t, at) {
  let depth = 0;
  for (let i = at; i < t.length; i++) { if (t[i] === "{") depth++; else if (t[i] === "}" && --depth === 0) return [t.slice(at + 1, i), i + 1]; }
  return [t.slice(at + 1), t.length];
}
const MATH = { uparrow: "↑", downarrow: "↓", times: "×", Delta: "Δ", geq: "≥", ge: "≥", leq: "≤", le: "≤", approx: "≈", dagger: "†", lambda: "λ", alpha: "α", beta: "β", theta: "θ", sigma: "σ", mu: "μ", pm: "±", in: "∈", sum: "Σ", cdot: "·", to: "→", rightarrow: "→", ldots: "…", dots: "…", infty: "∞", neq: "≠" };
const math = t => t.replace(/\\(?:mathcal|mathbf|mathrm|text|operatorname)\{([^{}]*)\}/g, "$1").replace(/\\([a-zA-Z]+)/g, (m, w) => MATH[w] ?? "").replace(/\\[,;!: ]/g, " ").replace(/[{}]/g, "");
const slug = key => key.toLowerCase().replace(/[^a-z0-9._-]+/g, "-").replace(/^[-.]+|[-.]+$/g, "");
function citeChip(keys) {
  return keys.split(",").map(k => k.trim()).filter(Boolean).map(key => {
    const paper = ix().nodes["paper:" + slug(key)], who = paper && paper.data.authors && paper.data.authors[0] ? paper.data.authors[0].split(/[ ,]/).filter(Boolean).pop() : key;
    return h("button", { type: "button", class: "cite", onclick: () => paper && pick(paper.id), onmouseenter: ev => paper && tipAt(ev.currentTarget, paper.title) , onmouseleave: hideTip }, who + (paper && paper.data.year ? " " + String(paper.data.year).slice(-2) : ""));
  });
}
function runValue(run, field) { return field.split(".").reduce((v, k) => v == null ? v : v[k], run.data); }
const agrees = (v, value) => Math.abs(v - value) <= .5 * 10 ** -(String(value).split(".")[1] || "").length + 1e-12;
function numberChip(link) {
  const e = link.event, d = e.body.data, runs = (e.about || []).map(id => ix().nodes[id]).filter(n => n && n.kind === "run");
  const held = d.field ? runs.map(n => runValue(n, d.field)).filter(v => typeof v === "number") : [], off = d.value != null && held.length > 0 && !held.some(v => agrees(v, d.value));
  const open = ev => { ev.stopPropagation();
    popAt(ev.currentTarget, h("div", { class: "source" }, h("p", { text: e.body.text }), h("ul", null, runs.map(n => { const v = d.field ? runValue(n, d.field) : null;
      return h("li", null, h("button", { type: "button", class: "plain", onclick: () => pick(n.id) }, glyph(n.status, 16), h("span", { text: n.title })), v != null && h("code", { text: fmt(v) })); })),
      off ? h("div", { class: "differs", text: "与记录不一致" }) : null)); };
  return h("button", { type: "button", class: "number" + (off ? " off" : ""), onclick: open }, link.show);
}
function inline(t, links) {
  const out = [];
  let i = 0, buf = "";
  const flush = () => { if (buf) { out.push(buf); buf = ""; } };
  while (i < t.length) {
    const c = t[i];
    if (c === "\u0001") { const j = t.indexOf("\u0002", i); flush(); const link = links[+t.slice(i + 1, j)]; out.push(numberChip({ ...link, show: inline(link.quote, []) })); i = j + 1; continue; }
    if (c === "$") { const j = t.indexOf("$", i + 1); if (j > 0) { flush(); out.push(h("span", { class: "math", text: math(t.slice(i + 1, j)) })); i = j + 1; continue; } }
    if (c === "\\") {
      const m = /^\\([a-zA-Z]+)\*?/.exec(t.slice(i, i + 40));
      if (!m) { const n = t[i + 1]; buf += n === "," || n === ";" || n === " " ? " " : n === "\\" ? " " : n || ""; i += 2; continue; }
      let j = i + m[0].length, name = m[1];
      while (t[j] === "[") j = t.indexOf("]", j) + 1;
      if (t[j] === "{") {
        const [inner, end] = balanced(t, j);
        flush(); i = end;
        if (/^[cC]ite/.test(name)) out.push(citeChip(inner));
        else if (name === "todo") out.push(h("mark", null, inline(inner, links)));
        else if (name === "textbf") out.push(h("b", null, inline(inner, links)));
        else if (name === "emph" || name === "textit") out.push(h("i", null, inline(inner, links)));
        else if (name === "paragraph") out.push(h("b", null, inline(inner, links), " "));
        else if (name === "texttt") out.push(h("code", null, inner));
        else if (/^[cC]?ref$|^autoref$|^eqref$/.test(name)) out.push(h("span", { class: "xref", text: inner.split(":").pop() }));
        else if (name === "label") { /* nothing to show */ } else out.push(inline(inner, links));
        continue;
      }
      i = j; continue;
    }
    if (c === "{" || c === "}") { i++; continue; }
    if (c === "~") { buf += " "; i++; continue; }
    if (c === "`" && t[i + 1] === "`") { buf += "“"; i += 2; continue; }
    if (c === "'" && t[i + 1] === "'") { buf += "”"; i += 2; continue; }
    if (c === "-" && t[i + 1] === "-") { buf += "–"; i += t[i + 2] === "-" ? 3 : 2; continue; }
    buf += c; i++;
  }
  flush();
  return out;
}
function tableBlock(raw, links) {
  const cap = raw.indexOf("\\caption"), caption = cap >= 0 ? balanced(raw, raw.indexOf("{", cap))[0] : null;
  const start = raw.indexOf("\\begin{tabular"), rows = [];
  if (start >= 0) {
    let at = raw.indexOf("}", start) + 1;
    if (raw[at] === "{") at = balanced(raw, at)[1];
    const body = raw.slice(at, raw.indexOf("\\end{tabular"));
    for (let line of body.split(/\\\\(?:\[[^\]]*\])?/)) {
      const rule = /\\midrule/.test(line);
      line = line.replace(/\\(?:toprule|midrule|bottomrule|hline)/g, "").replace(/\\cmidrule(?:\([^)]*\))?\{[^}]*\}/g, "").trim();
      if (!line) continue;
      const cells = line.split(/(?<!\\)&/).map(cell => {
        const m = /^\s*\\multicolumn\{(\d+)\}\{[^]*?\}\{/.exec(cell);
        if (!m) return { span: 1, text: cell.trim() };
        const open = cell.indexOf("{", cell.indexOf("}", cell.indexOf("}") + 1) + 1);
        const head = /^\s*\\multicolumn\{\d+\}/.exec(cell)[0].length, next = balanced(cell, head)[1];
        return { span: +m[1], text: balanced(cell, next)[0].trim(), wide: open };
      });
      rows.push({ rule, cells });
    }
  }
  return h("figure", { class: "tex-table" }, caption && h("figcaption", null, inline(caption, links)),
    h("div", { class: "table-wrap" }, h("table", null, h("tbody", null, rows.map(r => h("tr", { class: r.rule ? "rule" : null }, r.cells.map((c, i) => h(i ? "td" : "th", { colspan: c.span > 1 ? c.span : null }, inline(c.text, links)))))))));
}
function blocks(text) {
  const env = /\\begin\{(table\*?|figure\*?|itemize|enumerate|equation\*?|align\*?)\}([^]*?)\\end\{\1\}/g, out = [];
  const prose = (t, at) => { const part = /\n\s*\n/g; let last = 0, m; const push = (from, to) => { const raw = t.slice(from, to); if (raw.trim()) out.push({ kind: "p", raw, at: at + from }); }; while ((m = part.exec(t))) { push(last, m.index); last = m.index + m[0].length; } push(last, t.length); };
  let last = 0, m;
  while ((m = env.exec(text))) { prose(text.slice(last, m.index), last); out.push({ kind: m[1].replace("*", ""), raw: m[2], at: m.index }); last = m.index + m[0].length; }
  prose(text.slice(last), last);
  return out;
}
function noteTabs(notes) {
  const tabs = notes.flatMap(n => n.tags);
  return tabs.length ? h("div", { class: "gutter" }, tabs.map(tag => h("button", { type: "button", class: "note", dataset: { k: tag.k }, onclick: ev => { ev.stopPropagation(); popAt(ev.currentTarget, h("div", { class: "note-body" }, h("b", { text: BACKING[tag.k] || tag.k }), h("p", { text: tag.t })), "below"); } }, BACKING[tag.k] || tag.k))) : null;
}
function sectionBody(current, before) {
  const d = current.data, text = d.text || "", parts = blocks(text), links = (ix().numbers[current.id] || []).map(event => ({ event, quote: event.body.data.quote }));
  let figure = 0;
  const notesFor = i => (d.notes || []).filter(n => n.at > parts[i].at && (!parts[i + 1] || n.at <= parts[i + 1].at));
  return parts.map((block, i) => {
    let raw = block.raw;
    links.forEach((link, k) => { if (raw.includes(link.quote)) raw = raw.replace(link.quote, "\u0001" + k + "\u0002"); });
    const fresh = before && !before.includes(block.raw.trim());
    let body;
    if (block.kind === "table") body = tableBlock(raw, links);
    else if (block.kind === "figure") {
      const fig = (d.figures || [])[figure++], url = fig && blobUrl(fig.blob), cap = raw.indexOf("\\caption");
      body = h("figure", { class: "tex-figure" }, fig && /\.(svg|png|jpe?g)$/.test(fig.blob) ? h("button", { type: "button", class: "plate", onclick: () => lightbox(url, fig.name) }, h("img", { src: url, alt: fig.name })) : null, cap >= 0 && h("figcaption", null, inline(balanced(raw, raw.indexOf("{", cap))[0], links)));
    } else if (block.kind === "itemize" || block.kind === "enumerate") body = h(block.kind === "itemize" ? "ul" : "ol", null, raw.split("\\item").slice(1).map(x => h("li", null, inline(x.trim(), links))));
    else if (block.kind === "equation" || block.kind === "align") body = h("p", { class: "equation", text: math(raw.replace(/\\label\{[^}]*\}/, "").replace(/&|\\\\/g, " ").trim()) });
    else body = h("p", null, inline(raw.trim(), links));
    return h("div", { class: "para" + (fresh ? " fresh" : "") }, body, noteTabs(notesFor(i)));
  });
}
function lightbox(url, name) {
  openModal(h("div", { class: "lightbox" }, h("button", { type: "button", class: "ghost", "aria-label": "关闭", onclick: closeModal }, icon("close")), h("img", { src: url, alt: name })), true);
}
function paperView() {
  const supp = n => n.id.startsWith("section:supp-"), sections = live("section").filter(n => n.data.words || n.data.level === 1).sort((a, b) => supp(a) - supp(b) || a.data.order - b.data.order);
  if (!sections.length) return h("p", { class: "empty", text: "这一天还没有论文" });
  const current = sections.find(n => n.id === S.section) || sections[0], items = [];
  sections.forEach((n, i) => {
    if (supp(n) && !(i && supp(sections[i - 1]))) items.push(h("li", { class: "group", text: "补充材料" }));
    items.push(h("li", null, h("button", { type: "button", class: "lv" + n.data.level, "aria-current": n.id === current.id ? "true" : null, onclick: () => { go({ section: n.id, sel: null }); $("content").scrollTop = 0; } },
      h("span", { text: n.title }), n.data.todos ? h("i", { text: n.data.todos }) : null)));
  });
  requestAnimationFrame(() => document.querySelector(".outline [aria-current]")?.scrollIntoView({ block: "nearest" }));
  const d = current.data, cited = linked(current.id, "cites", "src"), past = dayBefore() ? stateAt(dayBefore()).nodes.find(n => n.id === current.id) : null;
  const backing = Object.entries(d.backing || {}).map(([k, n]) => h("span", { class: "note still", dataset: { k } }, (BACKING[k] || k) + " " + n));
  return h("div", { class: "paper" }, h("nav", { class: "outline", "aria-label": "目录" }, h("ul", null, items)),
    h("article", { class: "page" }, h("header", null, h("h2", { text: current.title }), h("div", { class: "page-meta" }, h("span", { text: d.words + " 词" }), d.todos ? h("span", { class: "due", text: d.todos + " 待填" }) : null, past && past.data.words !== d.words ? h("span", { class: "grew", text: (d.words > past.data.words ? "+" : "") + (d.words - past.data.words) }) : null, backing,
      cited.length ? h("button", { type: "button", class: "plain under", onclick: ev => { ev.stopPropagation(); popAt(ev.currentTarget, h("ul", { class: "cited" }, cited.sort((a, b) => a.title.localeCompare(b.title)).map(p => h("li", null, h("button", { type: "button", class: "plain", onclick: () => pick(p.id) }, p.title)))), "below"); } }, cited.length + " 篇引用") : null)),
      sectionBody(current, past ? past.data.text : null)));
}

/* Literature */
function worksView() {
  const q = S.q.trim().toLowerCase(), cited = {}, family = {};
  for (const e of ix().st.edges) { if (e.rel === "cites") cited[e.dst] = (cited[e.dst] || 0) + 1; if (e.rel === "covers") (family[e.dst] ||= []).push(ix().nodes[e.src]); }
  const lines = live("prior").filter(p => linked(p.id, "covers", "src").length);
  let works = live("paper").filter(n => !q || (n.title + " " + (n.data.authors || []).join(" ") + " " + (n.data.venue || "")).toLowerCase().includes(q));
  if (S.family) works = works.filter(n => (family[n.id] || []).some(f => f && f.id === S.family));
  if (!live("paper").length) { const refs = referencesBlock(Object.keys(REFERENCE)); return refs.some(Boolean) ? h("div", { class: "works" }, refs) : h("p", { class: "empty", text: "这一天还没有" + KIND.paper }); }
  const years = {}, peak = () => Math.max(...Object.values(years), 1);
  for (const n of works) years[n.data.year || "?"] = (years[n.data.year || "?"] || 0) + 1;
  const who = a => !a || !a.length ? "" : a.length > 2 ? a[0] + " 等" : a.join("、");
  const byYear = Object.keys(years).sort().reverse();
  return h("div", { class: "works" },
    lines.length ? h("div", { class: "chips" }, h("button", { type: "button", "aria-pressed": String(!S.family), onclick: () => { S.family = null; renderContent(); } }, "全部"), lines.map(p => h("button", { type: "button", "aria-pressed": String(S.family === p.id), onclick: () => { S.family = p.id; renderContent(); } }, p.title))) : null,
    byYear.length ? byYear.map(y => h("section", { class: "year" }, h("h2", null, y, h("span", { text: years[y] })), h("ul", null, works.filter(n => (n.data.year || "?") === y).sort((a, b) => (cited[b.id] || 0) - (cited[a.id] || 0)).map(n =>
      h("li", null, h("button", { type: "button", class: "work" + (n.id === S.sel ? " picked" : ""), onclick: () => pick(n.id) }, h("span", { class: "work-title", text: n.title }), h("span", { class: "work-meta", text: [who(n.data.authors), (n.data.venue || "").replace(/^Proceedings of (the )?/, "")].filter(Boolean).join(" · ") }), cited[n.id] ? h("span", { class: "work-cited", text: cited[n.id] }) : null)))))) : h("p", { class: "empty", text: "没有符合的" + KIND.paper }), referencesBlock(["repository", "dependency"]));
}

/* Compute */
function resourcesView() {
  const machines = live("resource");
  if (!machines.length) return h("p", { class: "empty", text: "这一天还没有算力记录" });
  const runsOn = r => linked(r.id, "on", "dst").filter(n => n.kind === "run");
  const planned = r => linked(r.id, "on", "dst").filter(n => n.kind === "experiment" && ["approved", "queued", "running", "proposed"].includes(n.status));
  const all = machines.flatMap(runsOn), start = all.length ? Math.min(...all.map(n => +new Date(n.since))) : 0;
  const end = all.length ? Math.max(...all.map(n => n.status === "running" ? Date.now() : +new Date(n.changed))) : 1, width = Math.max(end - start, 1);
  const hours = [], first = new Date(start); first.setMinutes(0, 0, 0);
  for (let t = +first + 3600e3, step = width > 864e5 * 2 ? 6 * 3600e3 : width > 864e5 ? 3 * 3600e3 : 3600e3; t < end; t += step) hours.push(t);
  const cards = machines.map(r => { const busy = runsOn(r).filter(n => n.status === "running"), next = planned(r);
    return h("button", { type: "button", class: "machine" + (r.id === S.sel ? " picked" : "") + (r.data.reserved ? " reserved" : "") + (busy.length ? " busy" : ""), onclick: () => pick(r.id) },
      h("span", { class: "m-top" }, h("b", { text: r.title }), h("i", { class: "pulse" })), r.data.hardware && h("span", { class: "m-hw", text: r.data.hardware }), r.data.role && h("span", { class: "m-role", text: r.data.role }),
      next.length ? h("span", { class: "m-next" }, next.map(x => h("span", null, glyph(x.status, 16), x.title))) : null); });
  const lanes = machines.filter(r => runsOn(r).length).map(r => h("div", { class: "lane-row" }, h("span", { class: "lane-name", text: r.title }), h("div", { class: "lane-track" }, runsOn(r).map(n => {
    const from = +new Date(n.since), to = n.status === "running" ? Date.now() : +new Date(n.changed);
    return h("button", { type: "button", class: "bar", dataset: { st: n.status }, style: { left: ((from - start) / width * 100).toFixed(2) + "%", width: Math.max((to - from) / width * 100, .6).toFixed(2) + "%" }, onclick: () => pick(n.id), onmouseenter: ev => tipAt(ev.currentTarget, n.title + " · " + seconds((to - from) / 1000)), onmouseleave: hideTip }, h("span", { text: n.data.task || "" }));
  }))));
  return h("div", { class: "compute" }, h("div", { class: "machines" }, cards),
    all.length ? h("section", { class: "gantt" }, h("div", { class: "axis" }, hours.map(t => h("span", { style: { left: ((t - start) / width * 100).toFixed(2) + "%" }, text: clock(t) }))), lanes) : null);
}

/* Drawer */
function kv(data) {
  const rows = [];
  const put = (label, value) => {
    if (value == null || value === "") return;
    if (Array.isArray(value)) value = value.map(fmt).join("，");
    const mono = typeof value === "number" || /^[0-9a-f]{8,}$|[\\/]/.test(String(value));
    const web = label === "arXiv" ? "https://arxiv.org/abs/" + value : /^https:\/\//.test(value) ? value : null;
    rows.push(h("dt", { text: label }), web ? h("dd", null, h("a", { href: web, target: "_blank", rel: "noopener", text: value })) : h("dd", { class: mono ? "mono" : null, text: fmt(value) }));
  };
  for (const [key, value] of Object.entries(data || {})) {
    if (HIDDEN.includes(key)) continue;
    if (value && typeof value === "object" && !Array.isArray(value)) for (const [k, v] of Object.entries(value)) put((FIELD[key] || key) + " · " + k, v);
    else put(FIELD[key] || key, value);
  }
  return rows.length ? h("dl", { class: "kv" }, rows) : null;
}
const only = (data, keep) => Object.fromEntries(Object.entries(data || {}).filter(([k]) => keep(k)));
function brief(e) {
  return h("button", { type: "button", class: "brief", onclick: () => pick(e.id) }, h("span", { class: "brief-head" }, chip(e.type), h("time", { text: e.day.slice(5).replace("-", ".") + " " + e.time })), h("span", { class: "brief-text", text: e.body.text }));
}
function links(label, nodes) {
  return nodes.length ? [h("h3", null, label, h("span", { text: nodes.length })), h("ul", { class: "links" }, nodes.slice(0, 60).map(o => h("li", null, h("button", { type: "button", class: "plain", onclick: () => pick(o.id) }, o.status && glyph(o.status, 16), h("span", { text: o.title })))))] : null;
}
function logTab(node) {
  const box = h("pre", { class: "log", text: "读取中" }), file = node.data.log_file;
  fetch(blobUrl(file.blob)).then(r => r.text()).then(text => { const lines = text.split("\n"); box.textContent = lines.slice(-400).join("\n"); box.scrollTop = box.scrollHeight; }).catch(() => { box.textContent = "读不到日志"; });
  return [h("div", { class: "log-head" }, h("span", { text: (file.bytes / 1024).toFixed(0) + " KB" }), h("a", { href: blobUrl(file.blob), target: "_blank", rel: "noopener" }, icon("expand", 16))), box];
}
function runDetail(node, records) {
  const d = node.data, tabs = [["result", "结果"], ["settings", "设置"], d.log_file && ["log", "日志"], records.length && ["record", "记录"]].filter(Boolean), tab = tabs.some(t => t[0] === S.tab) ? S.tab : tabs[0][0];
  const metrics = Object.entries(d.metrics || {});
  return [h("div", { class: "tabs", role: "tablist" }, tabs.map(([k, label]) => h("button", { type: "button", role: "tab", "aria-selected": String(k === tab), onclick: () => { S.tab = k; renderDrawer(); } }, label))),
    tab === "result" && [d.qualified != null && h("div", { class: "qualified" }, gauge(d.qualified, d.samples, 64), h("div", null, h("b", { text: d.qualified + " / " + d.samples }), h("span", { text: "合格" }))),
      metrics.length ? h("div", { class: "metrics" }, metrics.map(([k, v]) => h("div", null, h("span", { text: k }), h("b", { text: fmt(v) })))) : null,
      kv(only(d, k => OUTCOME.includes(k) && !["metrics", "qualified", "samples"].includes(k)))],
    tab === "settings" && kv(only(d, k => !OUTCOME.includes(k))),
    tab === "log" && logTab(node),
    tab === "record" && records.slice(0, 40).map(brief)];
}
function renderDrawer() {
  const box = $("drawer"), { nodes, events, st } = ix(), node = S.sel && nodes[S.sel], event = S.sel && events[S.sel];
  const open = !!(node || event);
  $("app").classList.toggle("open", open);
  if (!open) { box.hidden = true; return; }
  box.hidden = false;
  const bar = label => h("div", { class: "drawer-bar" }, S.trail.length ? h("button", { type: "button", class: "ghost", "aria-label": "返回", onclick: () => { const trail = S.trail.slice(0, -1); go({ sel: S.trail[S.trail.length - 1], trail, tab: null }); } }, icon("back")) : null, label, h("span", { class: "grow" }),
    h("button", { type: "button", class: "ghost", "aria-label": "关闭", onclick: () => { locked = null; go({ sel: null, trail: [] }); } }, icon("close")));
  if (node) {
    const groups = {}, mine = P().events.filter(e => e.day <= S.day);
    for (const e of st.edges) { const side = e.src === node.id ? 0 : e.dst === node.id ? 1 : -1; const other = side < 0 ? null : nodes[side ? e.src : e.dst]; if (other) (groups[(RELATION[e.rel] || [e.rel, e.rel])[side]] ||= []).push(other); }
    const records = mine.filter(e => !STRUCTURAL.includes(e.type) && (e.about || []).includes(node.id)).reverse(), fig = node.data.figure;
    fill(box, bar(h("span", { class: "kind", text: KIND[node.kind] || node.kind })),
      h("div", { class: "drawer-body" }, h("h2", { text: node.title }), node.status && status(node.status), node.summary && h("p", { class: "lead", text: node.summary }),
        fig && h("button", { type: "button", class: "plate", onclick: () => lightbox(blobUrl(fig.blob), fig.name) }, h("img", { src: blobUrl(fig.blob), alt: fig.name })),
        node.kind === "run" ? runDetail(node, records) : [kv(node.data), node.kind === "section" && h("button", { type: "button", class: "action", onclick: () => go({ view: "paper", section: node.id, sel: null, trail: [] }) }, "读全文")],
        Object.entries(groups).map(([label, others]) => links(label, others.sort((a, b) => String(b.data.year || b.since).localeCompare(String(a.data.year || a.since))))),
        node.kind !== "run" && records.length ? [h("h3", null, "记录", h("span", { text: records.length })), records.slice(0, 30).map(brief)] : null));
    return;
  }
  const later = P().events.filter(e => (e.refs || []).some(r => r.to === event.id)), src = event.source || {};
  const facts = event.type === "profile" && event.body.data, made = event.type === "output";
  fill(box, bar(chip(event.type)),
    h("div", { class: "drawer-body" }, h("p", { class: event.actor.kind === "human" ? "full voice" : "full", text: event.body.text }),
      facts && h("dl", { class: "facts" }, facts.facts.map(f => [h("dt", { text: f.field }), h("dd", { dataset: { basis: f.basis } }, f.value || BASIS.unknown, f.basis === "inferred" ? h("span", { class: "inferred", text: BASIS.inferred }) : null)])),
      facts && facts.missing && [h("h3", { text: "缺" }), h("ul", { class: "wanting" }, facts.missing.map(m => h("li", { text: m })))],
      made && h("button", { type: "button", class: "action", onclick: () => go({ view: "outputs", section: event.id, sel: null, trail: [] }) }, "读全文"),
      h("div", { class: "byline" }, h("b", { text: event.actor.name }), h("span", { text: event.day.slice(5).replace("-", ".") + " " + event.time }), event.writer !== event.actor.name && h("span", { text: "由 " + event.writer + " 记录" })),
      kv(event.body.data),
      links("关于", (event.about || []).map(id => nodes[id]).filter(Boolean)),
      (event.refs || []).length ? [h("h3", null, "依据", h("span", { text: event.refs.length })), event.refs.slice(0, 30).map(r => events[r.to]).filter(Boolean).map(brief)] : null,
      later.length ? [h("h3", null, "后续", h("span", { text: later.length })), later.map(brief)] : null,
      src.kind ? h("details", { class: "origin" }, h("summary", { text: "出处" }), kv(Object.fromEntries(Object.entries(src).map(([k, v]) => [{ kind: "来源", id: "记录", session: "会话", repo: "仓库", file: "文件", host: "主机" }[k] || k, v])))) : null));
}
