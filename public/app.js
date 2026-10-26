"use strict";
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const STORE_KEY = "carebridge.reviews.v1";
const LEVEL_ORDER = { "긴급": 0, "주의": 1, "관찰": 2, "일반": 3 };
// 내부 단계 → 화면 표시 (진단·위험 판정이 아니라 보고 우선순위로 보여 준다)
const LV_LABEL = { "긴급": "즉시 보고", "주의": "오늘 확인", "관찰": "관찰", "일반": "일반 기록" };
const lvl = (k) => LV_LABEL[k] || k;

let current = null; // 마지막 분석 결과
let currentInput = null;

/* ---------- 저장소 (브라우저 전용) ---------- */
function loadReviews() {
  try { return JSON.parse(localStorage.getItem(STORE_KEY) || "[]"); } catch { return []; }
}
function saveReviews(list) {
  try { localStorage.setItem(STORE_KEY, JSON.stringify(list)); } catch { /* 사생활 보호 모드 등 */ }
  memoryReviews = list;
}
let memoryReviews = loadReviews();

function toast(msg) {
  const t = document.createElement("div");
  t.className = "toast"; t.textContent = msg; t.setAttribute("role", "status");
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 2200);
}
async function copy(text) {
  try { await navigator.clipboard.writeText(text); toast("복사했습니다"); }
  catch { toast("복사하지 못했습니다. 직접 선택해 복사해 주세요."); }
}

/* ---------- 탭 ---------- */
const TABS = ["analyze", "review", "about"];
function showTab(name) {
  TABS.forEach((t) => {
    $(`#tab-${t}`).setAttribute("aria-selected", String(t === name));
    $(`#view-${t}`).hidden = t !== name;
  });
  if (name === "review") renderReviews();
  window.scrollTo({ top: 0 });
}
TABS.forEach((t) => { $(`#tab-${t}`).onclick = () => showTab(t); });
$$("[data-goto]").forEach((b) => { b.onclick = () => showTab(b.dataset.goto); });

/* ---------- 진행 단계 (1 입력 → 2 분석 → 3 검토) ---------- */
function setStep(n, allDone = false) {
  $$("#stepper li").forEach((li) => {
    const k = Number(li.dataset.step);
    li.className = allDone || k < n ? "done" : k === n ? "on" : "";
  });
}

/* ---------- 첫 방문 안내 ---------- */
const INTRO_KEY = "carebridge.intro.hidden";
try { if (localStorage.getItem(INTRO_KEY)) $("#intro").hidden = true; } catch { /* 저장소 없음 */ }
$("#btn-intro-close").onclick = () => {
  $("#intro").hidden = true;
  try { localStorage.setItem(INTRO_KEY, "1"); } catch { /* 저장소 없음 */ }
};
$("#btn-how").onclick = () => showTab("about");

let SAMPLES = [];
function loadSample(s) {
  $("#memo").value = s.memo; $("#shift").value = s.shift || ""; $("#rcode").value = s.recipient_code || "";
  $$("#samples button").forEach((b) => b.classList.toggle("sel", b.dataset.id === s.id));
  updateChars();
}
async function tryDemo() {
  showTab("analyze");
  if (!$("#source-view").hidden) $("#btn-edit").click();
  const s = SAMPLES.find((x) => x.id === "vi_02") || SAMPLES[0];
  if (!s) return;
  loadSample(s);
  $(".split").scrollIntoView({ behavior: "smooth", block: "start" });
  analyze();
}
$("#btn-try").onclick = tryDemo;
$$("[data-try]").forEach((b) => { b.onclick = tryDemo; });

/* ---------- 초기화 ---------- */
async function init() {
  updateCount();
  try {
    const h = await (await fetch("/api/health")).json();
    const st = $("#ai-status");
    if (h.mode === "ai") { $("span", st).textContent = `AI 연결됨 · ${h.model}`; st.className = "status ai"; }
    else { $("span", st).textContent = "데모 모드 · AI 미연결"; st.className = "status demo"; st.title = "AI 키가 없어 규칙 기반으로만 동작합니다"; }
  } catch { $("#ai-status span").textContent = "서버 연결 안 됨"; }
  try {
    SAMPLES = await (await fetch("/samples.json")).json();
    const box = $("#samples");
    SAMPLES.forEach((s) => {
      const b = document.createElement("button");
      b.type = "button";
      b.dataset.id = s.id;
      b.innerHTML = `<b>${esc(s.lang_name)}</b>${esc(s.title)}`;
      b.onclick = () => { loadSample(s); $("#memo").focus(); };
      box.appendChild(b);
    });
  } catch { /* 샘플 없어도 동작 */ }
}
function updateChars() { $("#charcount").textContent = `${$("#memo").value.length} / 3000`; }
$("#memo").addEventListener("input", updateChars);

/* ---------- 분석 ---------- */
$("#btn-analyze").onclick = analyze;
$("#memo").addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) analyze(); });

async function analyze() {
  const memo = $("#memo").value.trim();
  const err = $("#error");
  err.hidden = true;
  if (!memo) { err.textContent = "메모 내용을 입력해 주세요."; err.hidden = false; return; }
  const names = $("#names").value.split(",").map((s) => s.trim()).filter(Boolean);
  currentInput = { memo, context: { shift: $("#shift").value, recipient_code: $("#rcode").value.trim() } };
  const btn = $("#btn-analyze");
  btn.disabled = true; btn.textContent = "정리하는 중…";
  $("#empty").hidden = true; $("#out").hidden = true; $("#loading").hidden = false;
  setStep(2);
  $("#intro").hidden = true; // 작업을 시작하면 안내를 접어 결과가 위로 오게
  const steps = $$("#loading .steps p");
  steps.forEach((p) => p.className = "");
  let i = 0; steps[0].className = "on";
  const timer = setInterval(() => {
    if (i < steps.length - 1) { steps[i].className = "done"; i++; steps[i].className = "on"; }
  }, 1400);
  try {
    const res = await fetch("/api/analyze", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...currentInput, registered_names: names }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "분석에 실패했습니다.");
    current = data;
    render(data);
  } catch (e) {
    $("#loading").hidden = true; $("#empty").hidden = false;
    setStep(1);
    err.textContent = e.message || "분석에 실패했습니다. 잠시 뒤 다시 시도해 주세요."; err.hidden = false;
  } finally {
    clearInterval(timer);
    btn.disabled = false; btn.textContent = "AI로 정리하기";
  }
}

$("#btn-edit").onclick = () => {
  $("#input-area").hidden = false; $("#source-view").hidden = true; $("#btn-edit").hidden = true;
  $("#out").hidden = true; $("#empty").hidden = false; setStep(1);
  $("#memo").focus();
};

/* ---------- 원문 하이라이트 ---------- */
function renderSource(data) {
  const text = data.masked_memo;
  const marks = []; // {start,end,cls,id}
  data.pii.entities.forEach((e) => marks.push({ start: e.start, end: e.end, cls: "pii" }));
  data.checks.rule_hits.forEach((h) => marks.push({ start: h.start, end: h.end, cls: "rule" }));
  const r = data.result;
  r.risk_flags.forEach((f, i) => { const c = f.evidence_check; if (c.start != null) marks.push({ start: c.start, end: c.end, cls: "ev", id: `r${i}` }); });
  r.observations.forEach((o, i) => { const c = o.evidence_check; if (c.start != null) marks.push({ start: c.start, end: c.end, cls: "ev", id: `o${i}` }); });
  data.checks.cross_check_alerts.forEach((a, i) => marks.push({ start: a.start, end: a.end, cls: "ev", id: `a${i}` }));
  const pts = new Set([0, text.length]);
  marks.forEach((m) => { pts.add(m.start); pts.add(m.end); });
  const sorted = [...pts].sort((a, b) => a - b);
  let html = "";
  for (let k = 0; k < sorted.length - 1; k++) {
    const a = sorted[k], b = sorted[k + 1];
    const seg = text.slice(a, b);
    const on = marks.filter((m) => m.start <= a && m.end >= b);
    if (!on.length) { html += esc(seg); continue; }
    const cls = [...new Set(on.map((m) => m.cls))].join(" ");
    const ids = on.filter((m) => m.id).map((m) => m.id).join(" ");
    html += `<span class="${cls}"${ids ? ` data-ids="${ids}"` : ""}>${esc(seg)}</span>`;
  }
  const box = $("#source-text");
  box.innerHTML = html;
  box.lang = data.result.detected_language || "";
  const c = data.pii.counts;
  const piiTxt = Object.keys(c).length ? Object.entries(c).map(([k, v]) => `${k} ${v}`).join(", ") : "찾은 항목 없음";
  const ev = data.checks.evidence;
  $("#source-facts").innerHTML = `
    <dt>언어</dt><dd>${esc(data.meta.language_name)}${data.checks.language_agrees ? "" : ` <span class="muted">(규칙 추정: ${esc(data.checks.language_rule_guess)})</span>`}</dd>
    <dt>가린 정보</dt><dd>${esc(piiTxt)}</dd>
    <dt>근거 대조</dt><dd>${ev.total ? `${ev.exact + ev.partial} / ${ev.total}건 원문에서 확인${ev.missing ? ` · <b style="color:var(--urgent)">${ev.missing}건 확인 불가</b>` : ""}` : "-"}</dd>
    <dt>처리</dt><dd>${data.meta.mode === "ai" ? `${esc(data.meta.model)} · ${(data.meta.latency_ms / 1000).toFixed(1)}초` : "데모 모드(규칙 기반)"}</dd>`;
  $("#input-area").hidden = true; $("#source-view").hidden = false; $("#btn-edit").hidden = false;
}

function light(id, on) {
  $$("#source-text [data-ids]").forEach((s) => {
    if (s.dataset.ids.split(" ").includes(id)) s.classList.toggle("lit", on);
  });
  const first = on && $$("#source-text [data-ids]").find((s) => s.dataset.ids.split(" ").includes(id));
  if (first) {
    const box = $("#source-text");
    const top = first.offsetTop - box.offsetTop;
    if (top < box.scrollTop || top > box.scrollTop + box.clientHeight - 30) box.scrollTo({ top: top - 40, behavior: "smooth" });
  }
}
function bindEvidence(el, id) {
  el.dataset.ev = id; el.tabIndex = 0;
  el.addEventListener("mouseenter", () => light(id, true));
  el.addEventListener("mouseleave", () => { if (!el.classList.contains("lit")) light(id, false); });
  el.addEventListener("focus", () => light(id, true));
  el.addEventListener("blur", () => { if (!el.classList.contains("lit")) light(id, false); });
  el.addEventListener("click", () => {
    const was = el.classList.contains("lit");
    $$(".item.lit, .alert.lit").forEach((x) => { x.classList.remove("lit"); light(x.dataset.ev, false); });
    if (!was) { el.classList.add("lit"); light(id, true); }
  });
}

const CHK = { exact: "원문 확인", partial: "원문과 대부분 일치", missing: "원문에서 못 찾음" };
function evLine(item) {
  const c = item.evidence_check || {};
  if (!item.evidence_original) return "";
  return `<span class="evq"><q>${esc(item.evidence_original)}</q><span class="chk ${c.status}">${CHK[c.status] || ""}</span></span>`;
}

/* ---------- 결과 렌더 ---------- */
function render(data) {
  renderSource(data);
  const r = data.result, ck = data.checks;
  const out = $("#out");
  out.innerHTML = "";
  out.appendChild($("#tpl-result").content.cloneNode(true));

  const lv = ck.final_urgency;
  const vl = $(".v-level", out);
  vl.classList.add(`lv-${lv}`);
  $(".v-word", out).textContent = lvl(lv);
  $(".v-summary", out).textContent = r.summary_ko || "요약 없음";
  const code = currentInput.context.recipient_code;
  $(".v-meta", out).textContent = [code && `어르신 ${code}`, currentInput.context.shift && `${currentInput.context.shift} 근무`, `${data.meta.language_name} 메모`,
    ck.urgency_raised_by_rule && `AI는 '${lvl(ck.ai_urgency)}'로 정리 → 규칙 교차검증으로 올림`].filter(Boolean).join(" / ");
  if (data.meta.mode === "demo") {
    const n = document.createElement("p");
    n.className = "demo-note";
    n.textContent = "데모 모드입니다. AI 키가 연결되지 않아 규칙 사전으로 주의 표현만 찾았습니다. 번역·요약·되묻기는 AI 연결 후 동작합니다.";
    $(".verdict", out).after(n);
  }

  const ev = ck.evidence;
  const glance = [
    ["risks", "보고 필요 변화", r.risk_flags.length, r.risk_flags.length ? "hot" : "ok"],
    ["obs", "관찰 내용", r.observations.length, ""],
    ["acts", "권장 조치", r.recommended_actions.length, ""],
    ["obs", "근거 원문 확인", ev.total ? `${ev.exact + ev.partial}/${ev.total}` : "-", ev.missing ? "hot" : "ok"],
  ];
  $(".glance", out).innerHTML = glance.map(([k, label, v, cls]) =>
    `<a href="#" data-jump="${k}" class="${cls}"><b>${esc(v)}</b>${esc(label)}</a>`).join("");
  $$(".glance a", out).forEach((a) => { a.onclick = (e) => { e.preventDefault(); $(`[data-k="${a.dataset.jump}"]`, out).scrollIntoView({ behavior: "smooth", block: "start" }); }; });
  if (r.risk_flags.length) $(".n-risks", out).textContent = r.risk_flags.length;
  if (r.observations.length) $(".n-obs", out).textContent = r.observations.length;
  if (r.recommended_actions.length) $(".n-acts", out).textContent = r.recommended_actions.length;

  const alerts = $(".alerts", out);
  ck.cross_check_alerts.forEach((a, i) => {
    const d = document.createElement("div");
    d.className = "alert";
    d.innerHTML = `<b>교차검증 경고 · ${esc(a.type)}</b><br>${esc(a.message)}`;
    bindEvidence(d, `a${i}`);
    alerts.appendChild(d);
  });

  const risks = $(".risks", out);
  const rs = r.risk_flags.map((f, i) => ({ f, i })).sort((a, b) => LEVEL_ORDER[a.f.level] - LEVEL_ORDER[b.f.level]);
  if (!rs.length) risks.innerHTML = `<li class="none">보고가 필요한 변화를 찾지 못했습니다.</li>`;
  rs.forEach(({ f, i }) => {
    const li = document.createElement("li");
    li.className = "item";
    li.innerHTML = `<div class="row1"><span class="pill lv-${esc(f.level)}">${esc(lvl(f.level))}</span><b>${esc(f.type)}</b></div>
      <div class="txt">${esc(f.reason_ko)}</div>${evLine(f)}`;
    bindEvidence(li, `r${i}`);
    risks.appendChild(li);
  });

  const obs = $(".obs", out);
  if (!r.observations.length) obs.innerHTML = `<li class="none">정리된 관찰 내용이 없습니다.</li>`;
  r.observations.forEach((o, i) => {
    const li = document.createElement("li");
    li.className = "item";
    li.innerHTML = `<div class="row1"><span class="cat">${esc(o.category)}</span><span class="txt">${esc(o.content_ko)}</span>${o.certainty === "추정" ? `<span class="cert">(추정)</span>` : ""}</div>${evLine(o)}`;
    bindEvidence(li, `o${i}`);
    obs.appendChild(li);
  });

  const acts = $(".acts", out);
  if (!r.recommended_actions.length) acts.innerHTML = `<li class="none">권장 조치가 없습니다.</li>`;
  r.recommended_actions.forEach((a, i) => {
    const li = document.createElement("li");
    li.innerHTML = `<input type="checkbox" id="act${i}"><label for="act${i}"><span class="txt">${esc(a.action_ko)}</span><br><span class="who">${esc(a.owner)} · ${esc(a.due)}</span></label>`;
    $("input", li).onchange = (e) => li.classList.toggle("done", e.target.checked);
    acts.appendChild(li);
  });

  $(".draft", out).value = r.record_draft_ko;

  const asks = $(".asks", out);
  if (!r.followup_questions.length) asks.innerHTML = `<li class="none">AI가 제안한 질문이 없습니다.</li>`;
  r.followup_questions.forEach((q) => {
    const li = document.createElement("li");
    li.innerHTML = `<span>${esc(q.question_ko)}</span><span class="native"><span>${esc(q.question_native)}</span><button type="button">복사</button></span>`;
    $("button", li).onclick = () => copy(q.question_native);
    asks.appendChild(li);
  });
  $(".btn-reply", out).onclick = () => replyTranslate(r.detected_language);
  $("#reply-ko").addEventListener("keydown", (e) => { if (e.key === "Enter") replyTranslate(r.detected_language); });

  const miss = $(".missing", out);
  if (!r.missing_info.length) $('[data-k="missing"]', out).remove();
  r.missing_info.forEach((m) => { const li = document.createElement("li"); li.textContent = m; miss.appendChild(li); });

  const terms = $(".terms", out);
  if (!r.terms.length) $('[data-k="terms"]', out).remove();
  r.terms.forEach((t) => { const li = document.createElement("li"); li.innerHTML = `<span class="o">${esc(t.original)}</span> → <b>${esc(t.standard_ko)}</b>`; terms.appendChild(li); });

  $(".tr", out).textContent = r.translation_ko;

  $(".btn-save", out).onclick = () => saveRecord("승인");
  $(".btn-hold", out).onclick = () => saveRecord("보류");
  $(".btn-copy", out).onclick = () => copy($(".draft", out).value);

  $("#loading").hidden = true; out.hidden = false;
  setStep(3);
  out.scrollIntoView({ block: "nearest" });
}

async function replyTranslate(lang) {
  const msg = $("#reply-ko").value.trim();
  const box = $(".reply-out");
  if (!msg) { $("#reply-ko").focus(); return; }
  box.hidden = false; box.textContent = "번역하는 중…";
  try {
    const res = await fetch("/api/reply", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message: msg, target_lang: lang }) });
    const d = await res.json();
    if (!res.ok) throw new Error(d.error);
    box.innerHTML = `<div class="tl">${esc(d.translation)}</div><div class="muted small">다시 한국어로: ${esc(d.back_translation_ko)}</div><button class="copy-mini" type="button">번역문 복사</button>`;
    $("button", box).onclick = () => copy(d.translation);
  } catch (e) { box.textContent = e.message || "번역하지 못했습니다."; }
}

/* ---------- 검토함 ---------- */
function saveRecord(status) {
  if (!current) return;
  const list = memoryReviews.slice();
  list.unshift({
    id: Date.now(), at: new Date().toISOString(), status,
    code: currentInput.context.recipient_code || "", shift: currentInput.context.shift || "",
    lang: current.meta.language_name, urgency: current.checks.final_urgency,
    summary: current.result.summary_ko, draft: $(".draft").value,
    risks: current.result.risk_flags.map((f) => `${f.type}(${lvl(f.level)})`),
    actions_done: $$(".acts input").filter((x) => x.checked).length, actions_total: $$(".acts input").length,
    ai: current.meta.mode === "ai" ? current.meta.model : "demo",
  });
  saveReviews(list);
  updateCount();
  setStep(3, true);
  toast(status === "승인" ? "검토 완료로 저장했습니다" : "보류로 저장했습니다");
}
function updateCount() { $("#review-count").textContent = memoryReviews.length; }

function renderReviews() {
  const list = memoryReviews;
  const ol = $("#review-list");
  ol.innerHTML = "";
  $("#review-empty").hidden = list.length > 0;
  const cnt = (k) => list.filter((x) => x.urgency === k).length;
  $("#review-stats").innerHTML = list.length ? `
    <div class="stat"><b style="color:var(--urgent)">${cnt("긴급")}</b>즉시 보고</div>
    <div class="stat"><b style="color:var(--caution)">${cnt("주의")}</b>오늘 확인</div>
    <div class="stat"><b style="color:var(--calm)">${cnt("일반")}</b>일반 기록</div>
    <div class="stat"><b>${list.filter((x) => x.status === "보류").length}</b>보류</div>` : "";
  list.forEach((x) => {
    const li = document.createElement("li");
    const d = new Date(x.at);
    li.innerHTML = `<details class="rec"><summary>
        <span class="lv lv-${esc(x.urgency)}">${esc(lvl(x.urgency))}</span>
        <span><b>${esc(x.code || "코드 없음")}</b> <span class="muted small">${esc(x.lang)}${x.shift ? " · " + esc(x.shift) : ""}</span><span class="st ${x.status === "보류" ? "hold" : ""}">${esc(x.status)}</span><br>${esc(x.summary)}</span>
        <span class="when">${d.toLocaleDateString("ko-KR")} ${d.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" })}</span>
      </summary><div class="body">
        <pre>${esc(x.draft)}</pre>
        <p class="muted small">보고 필요 변화: ${esc(x.risks.join(", ") || "없음")} · 조치 ${x.actions_done}/${x.actions_total} 완료 · AI: ${esc(x.ai)}</p>
        <button class="ghost btn-del" type="button">이 기록 지우기</button>
      </div></details>`;
    $(".btn-del", li).onclick = () => { saveReviews(memoryReviews.filter((y) => y.id !== x.id)); updateCount(); renderReviews(); };
    ol.appendChild(li);
  });
}
$("#btn-clear").onclick = () => {
  if (!memoryReviews.length) return;
  const b = $("#btn-clear");
  if (b.dataset.confirm) { saveReviews([]); updateCount(); renderReviews(); b.textContent = "모두 지우기"; delete b.dataset.confirm; return; }
  b.dataset.confirm = "1"; b.textContent = "한 번 더 누르면 지웁니다";
  setTimeout(() => { b.textContent = "모두 지우기"; delete b.dataset.confirm; }, 3000);
};
$("#btn-csv").onclick = () => {
  const rows = [["저장시각", "상태", "어르신코드", "근무조", "언어", "보고우선순위", "요약", "보고필요변화", "인수인계초안", "AI"]];
  memoryReviews.forEach((x) => rows.push([x.at, x.status, x.code, x.shift, x.lang, lvl(x.urgency), x.summary, x.risks.join(" / "), x.draft, x.ai]));
  const csv = "﻿" + rows.map((r) => r.map((v) => `"${String(v ?? "").replace(/"/g, '""')}"`).join(",")).join("\r\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  a.download = `carebridge_검토함_${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
};

init();
