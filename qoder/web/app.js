/* 格物 Gewu 前端逻辑：全部调用本地后端，无任何外部服务 */
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

async function api(path, options) {
  const response = await fetch(path, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || body.error || response.statusText);
  return body;
}

/* ---------- 顶部健康状态 ---------- */
async function loadHealth() {
  try {
    const h = await api("/api/health");
    const chunks = h.seekdb?.chunks ?? 0;
    const kinds = Object.entries(h.seekdb?.by_kind ?? {}).map(([k, v]) => `${k}:${v}`).join(" ");
    setPill("pill-seekdb", `seekdb ✓ ${chunks} chunks（${kinds}）`, h.seekdb);
    setPill("pill-pc", h.powercontext?.ok ? "PowerContext ✓ ready" : "PowerContext ✗", h.powercontext?.ok);
    setPill("pill-embed", `embedding ✓ ${h.embedding?.model} · ${h.embedding?.dim}d`, true);
  } catch (error) {
    ["pill-seekdb", "pill-pc", "pill-embed"].forEach((id) => setPill(id, "服务未就绪", false, String(error)));
  }
}
function setPill(id, text, ok, detail) {
  const el = $(id);
  el.textContent = text;
  el.className = "pill " + (ok ? "ok" : "bad");
  if (detail) el.title = detail;
}

/* ---------- 页签 ---------- */
document.querySelectorAll(".tab").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b === button));
    document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("active", p.id === `tab-${button.dataset.tab}`));
    if (button.dataset.tab === "corpus") loadDocs();
    if (button.dataset.tab === "memory") loadJournal();
  });
});

/* ---------- 检索 ---------- */
const KIND_LABEL = { paper: "论文", experiment: "实验", meeting: "纪要", note: "笔记", todo: "待办" };

async function doSearch() {
  const query = $("q").value.trim();
  if (!query) return;
  $("search-results").innerHTML = "<div class='meta'>检索中…</div>";
  const payload = {
    query,
    mode: $("mode").value,
    project: $("f-project").value.trim() || null,
    kind: $("f-kind").value || null,
    since: $("f-since").value || null,
    until: $("f-until").value || null,
    size: Number($("f-size").value) || 8,
  };
  try {
    const result = await api("/api/search", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    $("search-meta").innerHTML =
      `模式 <b>${esc(result.mode)}</b> · 命中 <b>${result.hits.length}</b> 条 · ` +
      `seekdb 耗时 <b>${result.elapsed_ms} ms</b>（端到端 ${result.total_ms} ms）`;
    const max = Math.max(...result.hits.map((h) => h._score || 0), 1e-6);
    $("search-results").innerHTML = result.hits.map((hit, i) => `
      <div class="hit">
        <span class="score">#${i + 1} · ${Number(hit._score).toFixed(4)}</span>
        <div class="title">《${esc(hit.title)}》 ${esc(hit.section || "")}</div>
        <div class="src">${KIND_LABEL[hit.kind] || hit.kind} / ${esc(hit.project)} / ${esc(hit.doc_date)}　出处文件分块 ${esc(hit.doc_id)}</div>
        <div class="snippet">${esc((hit.content || "").slice(0, 220))}…</div>
        <div class="bar"><i style="width:${Math.max(3, Math.round(((hit._score || 0) / max) * 100))}%"></i></div>
      </div>`).join("") || "<div class='meta'>没有命中，试试放宽过滤条件。</div>";
    $("sql-box").hidden = false;
    $("sql-content").textContent = `-- 实际下发给 seekdb 的语句\n${result.sql}\n\n-- 对应的混合检索 DSL\n${JSON.stringify(result.dsl, null, 2)}`;
  } catch (error) {
    $("search-results").innerHTML = `<div class="meta">检索失败：${esc(error.message)}</div>`;
  }
}

/* ---------- 记忆 ---------- */
async function remember() {
  const text = $("m-text").value.trim();
  if (!text) return;
  try {
    const result = await api("/api/memory/remember", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind: $("m-kind").value, text }) });
    $("m-text").value = "";
    loadJournal();
    alert(`已写入 PowerContext（${result.endpoint}，${result.elapsed_ms} ms）`);
  } catch (error) { alert("写入失败：" + error.message); }
}

async function recall() {
  const q = $("r-q").value.trim();
  if (!q) return;
  try {
    const result = await api(`/api/memory/recall?q=${encodeURIComponent(q)}&mode=${$("r-mode").value}&limit=6`);
    $("recall-results").innerHTML = result.hits.map((hit) => {
      const m = hit.memory || {};
      return `<div class="memo-hit"><span class="kind">${esc(m.kind || "memory")}</span>${esc(m.text || "")}
        <span class="muted">　score=${Number(hit.score || 0).toFixed(4)} · matched_by=${esc((hit.matched_by || []).join("+"))}</span></div>`;
    }).join("") || "<div class='meta'>没有命中。</div>";
  } catch (error) { $("recall-results").innerHTML = `<div class="meta">召回失败：${esc(error.message)}</div>`; }
}

async function loadJournal() {
  try {
    const result = await api("/api/memory/journal?limit=20");
    $("journal").innerHTML = result.records.slice().reverse().map((r) =>
      `<div class="jr"><span class="t">${esc(r.ts)}</span><b>${esc(r.endpoint)}</b> · ${esc(r.status)} · ${esc(r.elapsed_ms)} ms</div>`
    ).join("") || "<div class='meta'>暂无记录。</div>";
  } catch (error) { $("journal").innerHTML = `<div class="meta">${esc(error.message)}</div>`; }
}

/* ---------- 草稿 ---------- */
async function makeDraft() {
  $("draft-md").hidden = false;
  $("draft-md").textContent = "生成中…";
  $("draft-prefs").innerHTML = "";
  const payload = {
    since: $("d-since").value, until: $("d-until").value,
    project: $("d-project").value.trim() || null, size: 12,
  };
  try {
    const result = await api("/api/draft", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    $("draft-md").textContent = result.markdown;
    const applied = result.preferences_applied || [];
    $("draft-prefs").innerHTML = applied.length
      ? `<div class="card"><h3>本次因记忆改变的输出</h3>` +
        applied.map((p) => `<span class="pref"><b>${esc(p.rule)}</b> ${esc(p.note)}</span>`).join("") +
        `<p class="hint">记忆来源：${esc((result.memory_used || []).map((m) => `${m.query}(${m.hits.length}条)`).join("；"))}</p></div>`
      : `<div class="card"><h3>没有命中任何记忆偏好</h3><p class="hint">到「记忆」页写入「组会材料要结论先行」等偏好，再重新生成即可看到版式变化。</p></div>`;
  } catch (error) {
    $("draft-md").textContent = "生成失败：" + error.message;
  }
}

/* ---------- 语料 ---------- */
async function ingestSample() {
  try {
    const result = await api("/api/ingest/sample", { method: "POST" });
    alert(`已导入 ${result.ingested.length} 篇、${result.ingested.reduce((s, r) => s + r.chunks, 0)} 个分块`);
    loadDocs();
  } catch (error) { alert("导入失败：" + error.message); }
}

async function pasteIngest() {
  const content = $("paste-md").value.trim();
  if (!content) return;
  try {
    const result = await api("/api/ingest", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filename: $("paste-name").value.trim() || "粘贴笔记.md", content }) });
    $("paste-md").value = "";
    alert(`已导入 ${result.chunks} 个分块`);
    loadDocs();
  } catch (error) { alert("导入失败：" + error.message); }
}

async function loadDocs() {
  try {
    const result = await api("/api/documents");
    $("doc-list").innerHTML = `<div class="card"><h3>已入库 ${result.stats.chunks} 个分块</h3>` +
      result.documents.map((d) =>
        `<div class="doc"><span class="tag">${KIND_LABEL[d.kind] || d.kind}/${esc(d.project)}</span>
         <span>《${esc(d.title)}》</span><span class="muted">${esc(d.doc_date)} · ${d.chunks} chunks</span></div>`
      ).join("") + "</div>";
  } catch (error) { $("doc-list").innerHTML = `<div class="meta">${esc(error.message)}</div>`; }
}

/* ---------- URL 参数自动执行（支持分享链接与无头演示） ---------- */
function activateTab(name) {
  const button = document.querySelector(`.tab[data-tab="${name}"]`);
  if (button) button.click();
}

function runFromUrlParams() {
  const params = new URLSearchParams(location.search);
  const tab = params.get("tab");
  if (tab) activateTab(tab);
  const query = params.get("q");
  if (query) {
    $("q").value = query;
    if (params.get("mode")) $("mode").value = params.get("mode");
    if (params.get("project")) $("f-project").value = params.get("project");
    if (params.get("since")) $("f-since").value = params.get("since");
    if (params.get("until")) $("f-until").value = params.get("until");
    doSearch().then(() => {
      if (params.get("sql")) {
        const box = $("sql-box");
        if (box) box.open = true;
      }
    });
  }
  const recallQuery = params.get("rq");
  if (recallQuery) {
    activateTab("memory");
    $("r-q").value = recallQuery;
    if (params.get("rmode")) $("r-mode").value = params.get("rmode");
    recall();
  }
  if (params.get("autodraft")) {
    activateTab("draft");
    if (params.get("since")) $("d-since").value = params.get("since");
    if (params.get("until")) $("d-until").value = params.get("until");
    if (params.get("dproject")) $("d-project").value = params.get("dproject");
    makeDraft();
  }
  if (params.get("docs")) {
    activateTab("corpus");
    loadDocs();
  }
}

loadHealth();
setInterval(loadHealth, 15000);
runFromUrlParams();
