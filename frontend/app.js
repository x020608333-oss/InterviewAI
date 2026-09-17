"use strict";

/* ===================== 全局状态 ===================== */
const state = {
  token: localStorage.getItem("iv_token") || "",
  user: JSON.parse(localStorage.getItem("iv_user") || "null"),
  meta: null,
  interview: null,
  messages: [],
  selectedPosition: "",
  selectedDifficulty: "middle",
  authMode: "login",
  adminQuestions: [],
  adminEditing: null,
  adminDiff: "medium",
};

const DIFF_LABELS = { junior: "初级", middle: "中级", senior: "高级" };
const QDIFF_LABELS = { easy: "基础", medium: "核心", hard: "进阶" };

/* ===================== 工具 ===================== */
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function mdLite(s) {
  return escapeHtml(s).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
}

function truncate(s, n) {
  s = String(s || "");
  return s.length > n ? s.slice(0, n) + "…" : s;
}

function fmtDate(iso) {
  if (!iso) return "-";
  const d = new Date(iso.endsWith("Z") ? iso : iso + "Z");
  if (isNaN(d)) return iso;
  return d.toLocaleString("zh-CN", {
    year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
  });
}

function scoreColor(score) {
  return score >= 80 ? "#10b981" : score >= 60 ? "#f59e0b" : "#ef4444";
}

function levelClass(level) {
  if (["优秀", "良好"].includes(level)) return "level-ok";
  if (level === "一般") return "level-mid";
  return "level-bad";
}

let toastTimer = null;
function toast(msg, isError = false) {
  const el = $("#toast");
  el.textContent = msg;
  el.className = "toast" + (isError ? " error" : "");
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, 3000);
}

function showLoading(text) {
  $("#loadingText").textContent = text || "加载中…";
  $("#loading").hidden = false;
}
function hideLoading() { $("#loading").hidden = true; }

/* ===================== API ===================== */
async function api(path, opts = {}) {
  const { method = "GET", body } = opts;
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (state.token) headers["Authorization"] = "Bearer " + state.token;
  let res;
  try {
    res = await fetch("/api" + path, {
      method, headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (e) {
    throw new Error("无法连接服务器，请确认后端已启动");
  }
  let data = null;
  try { data = await res.json(); } catch (_) { /* 空响应 */ }
  if (!res.ok) {
    if (res.status === 401) { setSession(null, null); router(); }
    const detail = typeof (data && data.detail) === "string" ? data.detail : null;
    throw new Error(detail || `请求失败（${res.status}）`);
  }
  return data;
}

function setSession(token, user) {
  state.token = token || "";
  state.user = user || null;
  if (token) {
    localStorage.setItem("iv_token", token);
    localStorage.setItem("iv_user", JSON.stringify(user));
  } else {
    localStorage.removeItem("iv_token");
    localStorage.removeItem("iv_user");
  }
  applyChrome();
}

function applyChrome() {
  const logged = !!state.token;
  $("#topbar").hidden = !logged;
  $("#adminNav").hidden = !(logged && state.user && state.user.is_admin);
  if (logged && state.user) {
    $("#username").textContent = state.user.username;
    $("#userAvatar").textContent = (state.user.username || "U")[0].toUpperCase();
  }
}

/* ===================== 路由 ===================== */
function showView(name) {
  $$(".view").forEach((v) => { v.hidden = true; });
  $("#view-" + name).hidden = false;
  $$("#mainNav a").forEach((a) => a.classList.remove("active"));
  const navMap = { home: "home", history: "history", admin: "admin" };
  if (navMap[name]) {
    const el = document.querySelector(`#mainNav a[data-nav="${navMap[name]}"]`);
    if (el) el.classList.add("active");
  }
}

async function router() {
  applyChrome();
  if (!state.token) { showView("auth"); return; }
  const parts = (location.hash || "#/").replace(/^#\//, "").split("/").filter(Boolean);
  try {
    if (parts.length === 0) await renderHome();
    else if (parts[0] === "history") await renderHistory();
    else if (parts[0] === "admin") {
      if (!state.user || !state.user.is_admin) {
        toast("需要管理员权限", true);
        await renderHome();
      } else {
        await renderAdmin();
      }
    }
    else if (parts[0] === "interview" && parts[1]) await loadInterview(Number(parts[1]));
    else if (parts[0] === "report" && parts[1]) await renderReportView(Number(parts[1]));
    else await renderHome();
  } catch (e) {
    toast(e.message, true);
    showView("home");
  }
}

/* ===================== 登录 / 注册 ===================== */
function initAuth() {
  $$(".auth-tabs .tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      state.authMode = tab.dataset.tab;
      $$(".auth-tabs .tab").forEach((t) => t.classList.toggle("active", t === tab));
      $("#authSubmit").textContent = state.authMode === "login" ? "登 录" : "注 册";
    });
  });
  $("#authForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const username = $("#authUsername").value.trim();
    const password = $("#authPassword").value;
    if (!username || !password) return toast("请输入用户名和密码", true);
    showLoading(state.authMode === "login" ? "登录中…" : "注册中…");
    try {
      const data = await api(`/auth/${state.authMode}`, { method: "POST", body: { username, password } });
      setSession(data.token, data.user);
      location.hash = "#/";
      router();
      toast(state.authMode === "login" ? `欢迎回来，${data.user.username}` : "注册成功，开始你的第一场面试吧！");
    } catch (err) {
      toast(err.message, true);
    } finally {
      hideLoading();
    }
  });
}

function logout() {
  setSession(null, null);
  location.hash = "#/";
  router();
  toast("已退出登录");
}

/* ===================== 首页 ===================== */
async function ensureMeta() {
  if (!state.meta) state.meta = await api("/meta");
  return state.meta;
}

async function renderHome() {
  const meta = await ensureMeta();
  showView("home");

  const badge = $("#modeBadge");
  if (meta.llm_mode === "api") {
    badge.textContent = `已连接大模型：${meta.model} · RAG + Agent + Function Calling 全链路`;
    badge.classList.remove("mock");
  } else {
    badge.textContent = "离线演示模式：内置规则引擎驱动 · 在 .env 配置 OPENAI_API_KEY 后启用真实大模型";
    badge.classList.add("mock");
  }

  const grid = $("#positionGrid");
  if (!grid.dataset.built) {
    grid.innerHTML = meta.positions.map((p) => `
      <div class="position-item" data-position="${escapeHtml(p.name)}">
        <b>${escapeHtml(p.name)}</b>
        <small>${p.skills.length ? "考察：" + p.skills.map(escapeHtml).join(" / ") : "AI 从 JD 提取考察点"}</small>
      </div>`).join("");
    grid.addEventListener("click", (e) => {
      const item = e.target.closest(".position-item");
      if (!item) return;
      state.selectedPosition = item.dataset.position;
      $$(".position-item").forEach((el) => el.classList.toggle("selected", el === item));
    });
    grid.dataset.built = "1";
  }

  const seg = $("#difficultySeg");
  if (!seg.dataset.built) {
    seg.innerHTML = meta.difficulties.map((d) => `<button data-value="${d.value}">${d.label}</button>`).join("");
    seg.addEventListener("click", (e) => {
      const btn = e.target.closest("button[data-value]");
      if (!btn) return;
      state.selectedDifficulty = btn.dataset.value;
      $$("#difficultySeg button").forEach((b) => b.classList.toggle("active", b === btn));
    });
    seg.dataset.built = "1";
  }

  if (!state.selectedPosition) state.selectedPosition = meta.positions[0].name;
  $$(".position-item").forEach((el) => el.classList.toggle("selected", el.dataset.position === state.selectedPosition));
  $$("#difficultySeg button").forEach((b) => b.classList.toggle("active", b.dataset.value === state.selectedDifficulty));

  $("#bankStats").innerHTML = Object.entries(meta.bank_stats)
    .map(([s, n]) => `<div class="bank-item"><b>${n}</b><span>${escapeHtml(s)}</span></div>`).join("");
}

async function startInterview() {
  if (!state.selectedPosition) return toast("请先选择岗位", true);
  showLoading("正在提取技能点、检索题库并生成面试计划…");
  try {
    const data = await api("/interviews", {
      method: "POST",
      body: {
        position: state.selectedPosition,
        difficulty: state.selectedDifficulty,
        jd: $("#jdInput").value.trim(),
      },
    });
    state.interview = data.interview;
    state.messages = data.messages;
    location.hash = "#/interview/" + data.interview.id;
  } catch (e) {
    toast(e.message, true);
  } finally {
    hideLoading();
  }
}

/* ===================== 面试页 ===================== */
async function loadInterview(id) {
  showLoading("加载面试…");
  try {
    const data = await api("/interviews/" + id);
    state.interview = data.interview;
    state.messages = data.messages;
    state.report = data.report;
    renderInterview();
  } finally {
    hideLoading();
  }
}

function renderInterview() {
  showView("interview");
  renderChat();
}

function renderChat() {
  const iv = state.interview;
  if (!iv) return;
  const list = $("#chatList");
  list.innerHTML = state.messages.map(msgHtml).join("");
  list.scrollTop = list.scrollHeight;

  const total = iv.total || 1;
  const done = iv.status === "completed" ? total : Math.min(iv.current_index, total);
  $("#progressBar").style.width = Math.round((done / total) * 100) + "%";
  $("#chatTitle").textContent = `${iv.position} · ${DIFF_LABELS[iv.difficulty] || iv.difficulty}面试`;
  const cur = iv.items[Math.min(iv.current_index, total - 1)];
  $("#chatSub").textContent = iv.status === "completed"
    ? "本场面试已结束"
    : `第 ${Math.min(iv.current_index + 1, total)} / ${total} 题 · 当前考察点：${cur ? cur.skill : "-"}`;

  const ongoing = iv.status === "ongoing";
  $("#chatInput").disabled = !ongoing;
  $("#sendBtn").disabled = !ongoing;
  $("#endBtn").hidden = !ongoing;
  $("#chatInput").placeholder = ongoing
    ? "输入你的回答…（Enter 发送，Shift+Enter 换行）"
    : "本场面试已结束";
  renderPlan();
}

function msgHtml(msg) {
  const meta = msg.meta || {};
  if (msg.role === "assistant") {
    let tag = "";
    if (meta.kind === "question") tag = `<span class="q-tag">第 ${meta.q_index + 1} 题 · ${escapeHtml(meta.skill || "")}</span>`;
    else if (meta.kind === "follow_up") tag = `<span class="q-tag follow">追问 · ${escapeHtml(meta.skill || "")}</span>`;
    return `<div class="msg assistant"><div class="ai-avatar">AI</div><div class="bubble">${tag ? tag + "<br>" : ""}${mdLite(msg.content)}</div></div>`;
  }
  let chip = "";
  const a = meta.analysis;
  if (a) {
    const gaps = (a.gaps || []).length ? `<br>待补齐：${escapeHtml(a.gaps.join("；"))}` : "";
    chip = `<div class="msg-chip">面试官点评：<b>${a.score} 分</b> · <span class="${levelClass(a.level)}">${escapeHtml(a.level)}</span> —— ${escapeHtml(a.comment)}${gaps}</div>`;
  }
  return `<div class="msg user"><div class="bubble">${mdLite(msg.content)}</div></div>${chip}`;
}

function renderPlan() {
  const iv = state.interview;
  $("#planMeta").textContent = `共 ${iv.total} 题 · 计划由 ${iv.planner_mode === "llm" ? "LLM + RAG 检索生成" : "RAG 检索引擎生成"}`;
  $("#planSkills").innerHTML = iv.skills.map((s) => `<span>${escapeHtml(s)}</span>`).join("");
  let html = iv.items.map((it, i) => {
    const finished = iv.status === "completed" || i < iv.current_index;
    const cls = finished ? "done" : i === iv.current_index ? "current" : "";
    const stateTxt = finished ? "✓ 已完成" : i === iv.current_index ? "▶ 进行中" : "待考察";
    const diffTxt = it.difficulty === "easy" ? "基础" : it.difficulty === "hard" ? "进阶" : "核心";
    return `<div class="plan-item ${cls}">
      <div class="idx">${i + 1}</div>
      <div class="pt"><b>${escapeHtml(it.skill)}</b>${escapeHtml(truncate(it.question, 40))}
        <span class="rag-score">RAG 匹配 ${Math.round((it.retrieval_score || 0) * 100)}% · ${diffTxt} · ${stateTxt}</span>
      </div>
    </div>`;
  }).join("");
  if (iv.status === "completed") {
    html += `<a class="btn btn-primary btn-block" style="margin-top:12px" href="#/report/${iv.id}">查看面试报告 →</a>`;
  }
  $("#planList").innerHTML = html;
}

async function sendAnswer() {
  const input = $("#chatInput");
  const content = input.value.trim();
  if (!content || !state.interview || state.interview.status !== "ongoing") return;
  input.value = "";

  renderChat();
  const list = $("#chatList");
  list.insertAdjacentHTML("beforeend",
    `<div class="msg user"><div class="bubble">${mdLite(content)}</div></div>`);
  list.scrollTop = list.scrollHeight;

  showLoading("AI 面试官正在分析你的回答…");
  try {
    const data = await api(`/interviews/${state.interview.id}/answer`, {
      method: "POST",
      body: { content },
    });
    state.messages.push(data.user_message, data.assistant_message);
    state.interview.current_index = data.progress.index;
    if (data.finished) state.interview.status = "completed";
    renderChat();
    if (data.finished) await doFinish();
  } catch (e) {
    toast(e.message, true);
    renderChat();
  } finally {
    hideLoading();
  }
}

async function doFinish() {
  if (!state.interview) return;
  showLoading("评估官正在汇总每一轮回答，生成面试报告…");
  try {
    const data = await api(`/interviews/${state.interview.id}/finish`, { method: "POST" });
    state.report = data.report;
    state.interview.status = "completed";
    location.hash = "#/report/" + state.interview.id;
  } catch (e) {
    toast(e.message, true);
  } finally {
    hideLoading();
  }
}

/* ===================== 报告页 ===================== */
async function renderReportView(id) {
  showLoading("加载报告…");
  try {
    const data = await api("/interviews/" + id);
    state.interview = data.interview;
    if (!data.report) {
      showView("report");
      $("#reportBody").innerHTML = `
        <div class="card empty-tip">
          <p>本场面试的问答已结束，报告尚未生成。</p>
          <button class="btn btn-primary" style="margin-top:14px" onclick="doFinish()">立即生成报告</button>
        </div>`;
      return;
    }
    renderReport(data.interview, data.report);
  } finally {
    hideLoading();
  }
}

function renderReport(iv, report) {
  showView("report");
  const skills = report.skill_scores || [];
  $("#reportBody").innerHTML = `
    <div class="card report-hero">
      ${scoreRing(report.overall_score)}
      <div class="report-title">
        <h1>${escapeHtml(iv.position)} 面试报告<span class="grade-badge">${escapeHtml(report.grade)}</span></h1>
        <p class="muted">${DIFF_LABELS[iv.difficulty] || iv.difficulty}难度 · ${iv.total} 题 · ${fmtDate(iv.created_at)} · 评估：${iv.planner_mode === "llm" ? "LLM + RAG" : "RAG 规则引擎"}</p>
        <p style="margin-top:8px;font-size:14px;">${escapeHtml(report.summary)}</p>
      </div>
      <div class="report-actions">
        <button class="btn btn-ghost" id="exportBtn">导出 Markdown</button>
        <a class="btn btn-primary" href="#/">再来一场</a>
      </div>
    </div>
    <div class="report-grid">
      <div class="card radar-wrap">${skills.length >= 3 ? radarChart(skills) : '<p class="muted small">考察点不足 3 个，暂无雷达图<br>（完成更多技能的题目后展示）</p>'}</div>
      <div class="card">
        <h3 class="card-title">技能得分</h3>
        <div class="skill-bars">${skills.map(skillBar).join("") || '<p class="muted small">无数据</p>'}</div>
      </div>
    </div>
    <div class="tri-grid">
      <div class="card tri-good"><h3>优势</h3><ul>${(report.strengths || []).map((s) => `<li>${escapeHtml(s)}</li>`).join("") || '<li class="muted">-</li>'}</ul></div>
      <div class="card tri-bad"><h3>薄弱点</h3><ul>${(report.weaknesses || []).map((s) => `<li>${escapeHtml(s)}</li>`).join("") || '<li class="muted">-</li>'}</ul></div>
      <div class="card tri-tip"><h3>建议</h3><ul>${(report.suggestions || []).map((s) => `<li>${escapeHtml(s)}</li>`).join("") || '<li class="muted">-</li>'}</ul></div>
    </div>
    <div class="card">
      <h3 class="card-title">逐题点评 <span class="optional">点击展开</span></h3>
      <div class="qr-list">${(report.question_reviews || []).map(qrHtml).join("") || '<p class="muted small">无记录</p>'}</div>
    </div>
    <div class="card" style="margin-top:18px;">
      <h3 class="card-title">下一阶段学习计划</h3>
      <div class="plan-timeline">${(report.learning_plan || []).map(tlHtml).join("") || '<p class="muted small">无数据</p>'}</div>
    </div>`;
  $("#exportBtn").addEventListener("click", () => exportReport(iv, report));
}

function skillBar(s) {
  return `<div class="skill-bar">
    <div class="sb-head"><b>${escapeHtml(s.skill)}</b><span>${s.score} 分</span></div>
    <div class="track"><div class="fill" style="width:${s.score}%"></div></div>
    ${s.comment ? `<div class="muted small">${escapeHtml(s.comment)}</div>` : ""}
  </div>`;
}

function qrHtml(qr) {
  return `<div class="qr-item">
    <div class="qr-head" onclick="this.nextElementSibling.classList.toggle('hidden')">
      <div class="score-pill" style="background:${scoreColor(qr.score)}">${qr.score}</div>
      <h4>${escapeHtml(qr.question)}</h4>
      <span class="muted small">展开 ▾</span>
    </div>
    <div class="qr-body hidden">${escapeHtml(qr.comment || "无点评")}</div>
  </div>`;
}

function tlHtml(p) {
  return `<div class="tl-item">
    <div class="tl-phase">${escapeHtml(p.phase)}</div>
    <h4>${escapeHtml(p.goal)}</h4>
    ${p.resources && p.resources.length ? `<p class="res">推荐资料：${p.resources.map(escapeHtml).join(" · ")}</p>` : ""}
  </div>`;
}

function scoreRing(score) {
  const size = 132, r = 52, c = 2 * Math.PI * r;
  const dash = (c * score) / 100;
  return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
    <circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="#eef1f6" stroke-width="12"/>
    <circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="url(#ringGrad)" stroke-width="12" stroke-linecap="round"
      stroke-dasharray="${dash.toFixed(1)} ${c.toFixed(1)}" transform="rotate(-90 ${size / 2} ${size / 2})"/>
    <defs><linearGradient id="ringGrad" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#4f46e5"/><stop offset="100%" stop-color="#22d3ee"/>
    </linearGradient></defs>
    <text x="${size / 2}" y="${size / 2 + 2}" text-anchor="middle" dominant-baseline="middle" class="ring-num">${score}</text>
  </svg>`;
}

function radarChart(skills) {
  const size = 300, cx = size / 2, cy = size / 2, R = size / 2 - 46, n = skills.length;
  const angle = (i) => -Math.PI / 2 + (2 * Math.PI * i) / n;
  let rings = "";
  for (let g = 1; g <= 4; g++) {
    const rr = (R * g) / 4;
    const pts = skills.map((_, i) =>
      `${(cx + rr * Math.cos(angle(i))).toFixed(1)},${(cy + rr * Math.sin(angle(i))).toFixed(1)}`).join(" ");
    rings += `<polygon points="${pts}" class="radar-grid"/>`;
  }
  const axes = skills.map((_, i) => {
    const x = cx + R * Math.cos(angle(i)), y = cy + R * Math.sin(angle(i));
    return `<line x1="${cx}" y1="${cy}" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}" class="radar-axis"/>`;
  }).join("");
  const pt = (s, i) => {
    const v = Math.max(0.04, s.score / 100);
    return [cx + R * v * Math.cos(angle(i)), cy + R * v * Math.sin(angle(i))];
  };
  const value = skills.map((s, i) => pt(s, i).map((x) => x.toFixed(1)).join(",")).join(" ");
  const dots = skills.map((s, i) => {
    const [x, y] = pt(s, i);
    return `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="3.5" fill="#4f46e5"/>`;
  }).join("");
  const labels = skills.map((s, i) => {
    const lx = cx + (R + 28) * Math.cos(angle(i)), ly = cy + (R + 28) * Math.sin(angle(i));
    return `<text x="${lx.toFixed(1)}" y="${ly.toFixed(1)}" text-anchor="middle" dominant-baseline="middle" class="radar-label">${escapeHtml(s.skill)} ${s.score}</text>`;
  }).join("");
  return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" style="overflow:visible">${rings}${axes}<polygon points="${value}" class="radar-value"/>${dots}${labels}</svg>`;
}

function exportReport(iv, report) {
  const blob = new Blob([buildMarkdown(iv, report)], { type: "text/markdown;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `InterviewAI面试报告-${iv.position}-${iv.id}.md`;
  a.click();
  URL.revokeObjectURL(a.href);
  toast("报告已导出为 Markdown");
}

function buildMarkdown(iv, report) {
  const L = [];
  L.push("# InterviewAI 面试报告", "");
  L.push(`- **岗位**：${iv.position}（${DIFF_LABELS[iv.difficulty] || iv.difficulty}）`);
  L.push(`- **时间**：${fmtDate(iv.created_at)}`);
  L.push(`- **综合评分**：${report.overall_score}（${report.grade}）`, "");
  L.push(`> ${report.summary}`, "");
  L.push("## 技能得分");
  (report.skill_scores || []).forEach((s) => L.push(`- **${s.skill}**：${s.score} 分 —— ${s.comment || ""}`));
  L.push("", "## 优势");
  (report.strengths || []).forEach((s) => L.push(`- ${s}`));
  L.push("", "## 薄弱点");
  (report.weaknesses || []).forEach((s) => L.push(`- ${s}`));
  L.push("", "## 建议");
  (report.suggestions || []).forEach((s) => L.push(`- ${s}`));
  L.push("", "## 逐题点评");
  (report.question_reviews || []).forEach((q, i) => L.push(`${i + 1}. **【${q.score} 分】** ${q.question}`, `   - ${q.comment || ""}`));
  L.push("", "## 下一阶段学习计划");
  (report.learning_plan || []).forEach((p) => {
    L.push(`- **${p.phase}**：${p.goal}`);
    (p.resources || []).forEach((r) => L.push(`  - 资料：${r}`));
  });
  L.push("", "---", "由 InterviewAI 生成 · RAG 题库检索 + Agent 动态追问 + 结构化评估");
  return L.join("\n");
}

/* ===================== 历史页 ===================== */
async function renderHistory() {
  showLoading("加载历史记录…");
  try {
    const data = await api("/interviews");
    showView("history");
    const list = $("#historyList");
    if (!data.items.length) {
      list.innerHTML = '<div class="empty-tip">还没有面试记录，去开始第一场吧！</div>';
      return;
    }
    list.innerHTML = data.items.map((iv) => `
      <div class="history-item">
        <div class="score-pill" style="background:${iv.overall_score != null ? scoreColor(Math.round(iv.overall_score)) : "#94a3b8"}">${iv.overall_score != null ? Math.round(iv.overall_score) : "–"}</div>
        <div class="hi-main">
          <b>${escapeHtml(iv.position)}</b>
          <span class="status-tag ${iv.status === "completed" ? "done" : ""}">${iv.status === "completed" ? "已完成" : "进行中"}</span>
          <div class="muted">${DIFF_LABELS[iv.difficulty] || iv.difficulty} · ${iv.total} 题 · ${fmtDate(iv.created_at)}</div>
        </div>
        ${iv.status === "completed"
          ? `<a class="btn btn-ghost" href="#/report/${iv.id}">查看报告</a>`
          : `<a class="btn btn-primary" href="#/interview/${iv.id}">继续面试</a>`}
      </div>`).join("");
  } finally {
    hideLoading();
  }
}

/* ===================== 题库管理（管理员） ===================== */
function initAdmin() {
  $("#newQBtn").addEventListener("click", () => openQForm(null));
  $("#cancelQBtn").addEventListener("click", closeQForm);
  $("#saveQBtn").addEventListener("click", saveQForm);
  $("#skillFilter").addEventListener("change", loadAdminList);
  $("#diffFilter").addEventListener("change", loadAdminList);
  $("#qSearch").addEventListener("keydown", (e) => {
    if (e.key === "Enter") loadAdminList();
  });

  const seg = $("#fDiffSeg");
  seg.innerHTML = ["easy", "medium", "hard"]
    .map((d) => `<button type="button" data-value="${d}">${QDIFF_LABELS[d]}</button>`)
    .join("");
  seg.addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-value]");
    if (!btn) return;
    state.adminDiff = btn.dataset.value;
    $$("#fDiffSeg button").forEach((b) => b.classList.toggle("active", b === btn));
  });

  $("#qTable").addEventListener("click", async (e) => {
    const editBtn = e.target.closest("[data-edit]");
    const delBtn = e.target.closest("[data-del]");
    if (editBtn) {
      const q = state.adminQuestions.find((x) => x.id === editBtn.dataset.edit);
      if (q) openQForm(q);
    } else if (delBtn) {
      const qid = delBtn.dataset.del;
      if (!confirm(`确定删除题目 ${qid} 吗？删除会写入题库文件并立即热更新 RAG 索引。`)) return;
      showLoading("删除中…");
      try {
        await api(`/admin/questions/${qid}`, { method: "DELETE" });
        toast("已删除，索引已热更新");
        state.meta = null;
        await loadAdminList();
      } catch (err) {
        toast(err.message, true);
      } finally {
        hideLoading();
      }
    }
  });
}

async function renderAdmin() {
  showView("admin");
  closeQForm();
  await loadAdminList();
}

async function loadAdminList() {
  const params = new URLSearchParams();
  if ($("#skillFilter").value) params.set("skill", $("#skillFilter").value);
  if ($("#diffFilter").value) params.set("difficulty", $("#diffFilter").value);
  if ($("#qSearch").value.trim()) params.set("q", $("#qSearch").value.trim());
  const data = await api("/admin/questions?" + params.toString());
  state.adminQuestions = data.items;

  const selected = $("#skillFilter").value;
  $("#skillFilter").innerHTML =
    '<option value="">全部技能</option>' +
    data.skills.map((s) => `<option value="${escapeHtml(s)}">${escapeHtml(s)}（${data.stats[s]}）</option>`).join("");
  $("#skillFilter").value = selected;
  $("#skillOptions").innerHTML = data.skills.map((s) => `<option value="${escapeHtml(s)}">`).join("");
  $("#qCount").textContent = `共 ${data.items.length} 题`;

  const rows = data.items.map((q) => `
    <tr>
      <td><code>${escapeHtml(q.id)}</code></td>
      <td><span class="skill-tag">${escapeHtml(q.skill)}</span></td>
      <td>${QDIFF_LABELS[q.difficulty] || q.difficulty}</td>
      <td class="qt-title">${escapeHtml(truncate(q.question, 52))}
        <div class="muted small">要点 ${q.key_points.length} · 追问 ${(q.follow_ups || []).length}</div>
      </td>
      <td class="qt-actions">
        <button class="btn btn-ghost btn-sm" data-edit="${escapeHtml(q.id)}">编辑</button>
        <button class="btn btn-ghost btn-danger btn-sm" data-del="${escapeHtml(q.id)}">删除</button>
      </td>
    </tr>`).join("");
  $("#qTable").innerHTML = `
    <thead><tr><th>ID</th><th>技能</th><th>难度</th><th>题目</th><th>操作</th></tr></thead>
    <tbody>${rows || '<tr><td colspan="5" class="empty-tip">没有匹配的题目</td></tr>'}</tbody>`;
}

function openQForm(q) {
  state.adminEditing = q ? q.id : null;
  state.adminDiff = q ? q.difficulty : "medium";
  $("#qFormTitle").textContent = q ? `编辑题目 ${q.id}` : "新增题目";
  $("#fSkill").value = q ? q.skill : "";
  $("#fQuestion").value = q ? q.question : "";
  $("#fKeyPoints").value = q ? q.key_points.join("\n") : "";
  $("#fReference").value = q ? q.reference_answer : "";
  $("#fFollowUps").value = q && q.follow_ups ? q.follow_ups.join("\n") : "";
  $$("#fDiffSeg button").forEach((b) => b.classList.toggle("active", b.dataset.value === state.adminDiff));
  $("#qForm").classList.remove("hidden");
  $("#qForm").scrollIntoView({ behavior: "smooth", block: "start" });
}

function closeQForm() {
  state.adminEditing = null;
  $("#qForm").classList.add("hidden");
}

async function saveQForm() {
  const body = {
    skill: $("#fSkill").value.trim(),
    difficulty: state.adminDiff,
    question: $("#fQuestion").value.trim(),
    key_points: $("#fKeyPoints").value.split("\n").map((s) => s.trim()).filter(Boolean),
    reference_answer: $("#fReference").value.trim(),
    follow_ups: $("#fFollowUps").value.split("\n").map((s) => s.trim()).filter(Boolean),
  };
  if (!body.skill) return toast("请填写技能名", true);
  if (body.question.length < 4) return toast("题干太短", true);
  if (!body.key_points.length) return toast("至少填写一条考察要点", true);
  if (!body.reference_answer) return toast("请填写参考答案", true);
  showLoading("保存中…");
  try {
    if (state.adminEditing) {
      await api(`/admin/questions/${state.adminEditing}`, { method: "PUT", body });
    } else {
      await api("/admin/questions", { method: "POST", body });
    }
    toast("已保存，RAG 索引已热更新，新面试立即可用");
    state.meta = null;
    closeQForm();
    await loadAdminList();
  } catch (e) {
    toast(e.message, true);
  } finally {
    hideLoading();
  }
}

/* ===================== 初始化 ===================== */
function init() {
  initAuth();
  initAdmin();
  $("#startBtn").addEventListener("click", startInterview);
  $("#sendBtn").addEventListener("click", sendAnswer);
  $("#chatInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendAnswer(); }
  });
  $("#endBtn").addEventListener("click", () => {
    if (confirm("确定要提前结束本场面试并生成报告吗？")) doFinish();
  });
  $("#logoutBtn").addEventListener("click", logout);
  window.addEventListener("hashchange", router);
  router();
}

document.addEventListener("DOMContentLoaded", init);
