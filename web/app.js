// 원칙 알림 앱 화면. 서버 API에서 받은 숫자를 보여주기만 한다 (주문 기능 없음).
"use strict";

const $ = (sel) => document.querySelector(sel);
const view = $("#view");
const state = { status: null, page: "home" };

const TITLES = { home: "Top 10", mine: "내 종목", etf: "ETF", brief: "브리핑", alerts: "알림", settings: "설정" };
const WEEK = ["일", "월", "화", "수", "목", "금", "토"];
const KIND_LABEL = { buy: "매수권장", review: "매수검토", profit: "수익", loss: "손실", data_check: "데이터 확인" };
const BOARD_REFRESH_MS = 60 * 1000;

// ---------- 공통 ----------
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const usd = (n) => "$" + Number(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const pct = (n, digits = 1) => (n > 0 ? "+" : "") + Number(n).toFixed(digits) + "%";
const updown = (n) => (n > 0 ? "up" : n < 0 ? "down" : "");
function dayLabel(iso) {
  const d = new Date(iso + "T00:00:00");
  return `${d.getMonth() + 1}/${d.getDate()} (${WEEK[d.getDay()]})`;
}
const timeLabel = (iso) => (iso ? iso.slice(11, 16) : "");
function store(key, value) {
  try {
    if (value === undefined) return localStorage.getItem(key);
    localStorage.setItem(key, value);
  } catch { return null; }
}

async function api(path, body) {
  const res = await fetch("/api" + path, body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  if (res.status === 401 && path !== "/login") { showLogin(); throw new Error("login"); }
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "오류가 발생했습니다");
  return data;
}

let toastTimer;
function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), 3200);
}

const krw = (n) => Math.round(n).toLocaleString("ko-KR") + "원";
const krwShort = (n) => (n >= 1e8 ? (n / 1e8).toFixed(2).replace(/\.?0+$/, "") + "억" : Math.round(n / 1e4).toLocaleString("ko-KR") + "만") + " 원";
const tierTag = (t, big = false) => (t ? `<span class="tag ${t.key}${big ? " big" : ""}">${t.label}</span>` : "");

// ---------- Top 10 시세판 ----------
function stockCard(s) {
  const cls = s.tier ? s.tier.key : "";
  return `<a class="stock ${cls}" href="#/stock/${encodeURIComponent(s.symbol)}">
    <div class="name">${esc(s.name)}<span class="sym">${esc(s.symbol)}</span>
      ${tierTag(s.tier)}${s.new_high ? `<span class="tag newhigh">신고가</span>` : ""}${s.held ? `<span class="tag held">보유</span>` : ""}
      ${s.data_warning ? `<span class="tag warn">데이터 확인 필요</span>` : ""}</div>
    <div class="price num">${usd(s.price)}</div>
    <div class="high num">1년 고점 <b>${usd(s.high)}</b></div>
    <div class="chg num ${updown(s.change_pct)}">전일 ${pct(s.change_pct, 2)}</div>
    <div class="dd"><span class="k">1년 고점 대비</span><span class="v num">${pct(s.drawdown)}</span></div>
  </a>`;
}

async function renderHome() {
  const { stocks, updated } = await api("/board");
  const sort = store("sort") || "drop";
  const list = sort === "drop" ? [...stocks].sort((a, b) => a.drawdown - b.drawdown) : stocks;
  const count = (k) => stocks.filter((s) => s.tier?.key === k).length;
  const live = !state.status?.is_practice;
  view.innerHTML = `
    <div class="summary">
      <div class="sum buy"><div class="k">매수권장 (-20% 이상)</div><div class="v num">${count("buy")}<small> 종목</small></div></div>
      <div class="sum review"><div class="k">매수검토 (-5 ~ -15%)</div><div class="v num">${count("review")}<small> 종목</small></div></div>
    </div>
    <div class="board-head">
      <span class="board-time">${live ? `<b>${timeLabel(updated)}</b> 기준 · 1분마다 자동 갱신` : "연습용 데이터"}</span>
      <span class="sort">
        <button class="chip ${sort === "drop" ? "on" : ""}" data-sort="drop">하락률순</button>
        <button class="chip ${sort === "cap" ? "on" : ""}" data-sort="cap">시총순</button>
      </span>
    </div>
    ${list.map(stockCard).join("")}
    <p class="muted" style="margin:10px 4px">미국 시가총액 상위 10개 · 목록은 매월 1회 갱신합니다.</p>
  `;
  view.querySelectorAll("[data-sort]").forEach((b) => {
    b.onclick = () => { store("sort", b.dataset.sort); renderHome(); };
  });
}

// 시세판을 보고 있는 동안 1분마다 새로 받아온다
setInterval(() => {
  if (document.visibilityState !== "visible" || state.status?.is_practice) return;
  if (state.page === "home") renderHome().catch(() => {});
  if (state.page === "mine") renderMine().catch(() => {});
}, BOARD_REFRESH_MS);

// ---------- 내 종목 ----------
function mineCard(h) {
  const cls = h.pl_level > 0 ? "profit" : h.pl_level < 0 ? "loss" : "";
  return `<a class="mine ${cls}" href="#/stock/${encodeURIComponent(h.symbol)}">
    <div class="name">${esc(h.name)}<span class="sym">${esc(h.symbol)}</span>
      ${h.pl_level ? `<span class="tag ${cls}">${h.pl_level > 0 ? "+" : ""}${h.pl_level}% 구간</span>` : ""}
      ${h.in_top10 ? "" : `<span class="tag out">Top 10 밖</span>`}
      ${h.data_warning ? `<span class="tag warn">데이터 확인 필요</span>` : ""}</div>
    <div class="ret num ${updown(h.return_pct)}">${pct(h.return_pct, 2)}</div>
    <div class="sub num">${h.qty.toLocaleString("en-US")}주 · 평단 <b>${usd(h.avg_price)}</b> · 현재 ${usd(h.price)}</div>
    <div class="val num">${usd(h.value_usd)}</div>
  </a>`;
}

async function renderMine() {
  const { holdings, total, fx, updated } = await api("/holdings");
  const live = !state.status?.is_practice;
  if (!holdings.length) { view.innerHTML = `<div class="empty">보유 종목이 없습니다</div>`; return; }
  view.innerHTML = `
    <section class="card total">
      <div class="k">총 평가금액</div>
      <div class="big num">${usd(total.value_usd)}</div>
      ${total.value_krw ? `<div class="krw num">약 ${krwShort(total.value_krw)} (환율 ${fx.toLocaleString("ko-KR")}원)</div>` : ""}
      <div class="row2 num">
        <span>총 수익률 <b class="${updown(total.return_pct)}">${pct(total.return_pct, 2)}</b></span>
        <span>오늘 <b class="${updown(total.day_change_pct)}">${pct(total.day_change_pct, 2)}</b></span>
      </div>
    </section>
    <div class="board-head"><span class="board-time">${live ? `<b>${timeLabel(updated)}</b> 기준 · 1분마다 자동 갱신` : "연습용 보유 종목 (실제 계좌 아님)"}</span></div>
    ${holdings.map(mineCard).join("")}
    <p class="muted" style="margin:10px 4px">평단 대비 수익 +10%마다, 손실 -20%마다 알림 · 키움 계좌는 조회만 합니다.</p>
  `;
}

// ---------- 알림 ----------
function alertCard(a) {
  return `<a class="alert ${a.kind}" href="#/stock/${encodeURIComponent(a.symbol)}">
    <div class="alert-head">
      <span class="tag ${a.kind === "data_check" ? "warn" : a.kind}">${KIND_LABEL[a.kind] || ""}</span>
      <strong>${esc(a.name)}</strong><span class="muted">${esc(a.symbol)}</span>
    </div>
    <div class="alert-msg num">${esc(a.message)}</div>
  </a>`;
}

function alertList(alerts) {
  if (!alerts.length) return `<div class="empty">아직 받은 알림이 없습니다</div>`;
  let html = "", day = "";
  for (const a of alerts) {
    if (a.market_date !== day) {
      day = a.market_date;
      html += `<div class="alert-day">${dayLabel(day)} 장 기준</div>`;
    }
    html += alertCard(a);
  }
  return html;
}

async function renderAlerts() {
  const { alerts } = await api("/alerts");
  if (alerts.length) store("seenAlert", String(alerts[0].id));
  updateBadge(alerts);
  view.innerHTML = alertList(alerts);
}

// ---------- 아침 브리핑 ----------
const briefErr = (part) => (part && part.error ? `<p class="muted">이 면을 만들지 못했습니다: ${esc(part.error)}</p>` : "");

function briefAccount(a) {
  if (!a || a.error) return briefErr(a);
  return `<div class="row2 num">
      <span>총 수익률 <b class="${updown(a.return_pct)}">${pct(a.return_pct, 2)}</b></span>
      <span>전날 대비 <b class="${updown(a.day_change_pct)}">${pct(a.day_change_pct, 2)}</b></span>
    </div>
    <p class="num" style="margin-top:6px">평가금액 ${usd(a.value_usd)}${a.value_krw ? ` · 약 ${krwShort(a.value_krw)}` : ""}</p>
    ${a.alerts.length ? `<ul class="brief-list">${a.alerts.map((x) =>
      `<li><span class="tag ${x.kind}">${KIND_LABEL[x.kind]}</span> <b>${esc(x.name)}</b> 평단 대비 ${x.level > 0 ? "+" : ""}${x.level}% 구간 진입</li>`).join("")}</ul>`
      : `<p class="muted" style="margin-top:6px">밤사이 수익·손실 구간에 새로 들어간 종목 없음</p>`}`;
}

function briefZones(z) {
  if (!z || z.error) return briefErr(z);
  if (!z.stocks.length) return `<p class="muted">매수권장·매수검토 구간 종목 없음</p>`;
  return `<ul class="brief-list">${z.stocks.map((x) => `<li>
      <a href="#/stock/${encodeURIComponent(x.symbol)}">${tierTag(x.tier)} <b>${esc(x.name)}</b></a>
      1년 고점 대비 <b class="num">${pct(x.drawdown)}</b>${x.new ? ` <span class="tag newhigh">NEW</span>` : ""}
      ${x.next_split ? `<span class="muted"> · ${x.next_split.n}차 ${krwShort(x.next_split.amount)}</span>` : ""}
    </li>`).join("")}</ul>`;
}

function briefIssues(is) {
  if (!is || is.error) return briefErr(is);
  return `${is.stocks.map((x) => `<div class="issue">
      <div class="issue-head"><b>${esc(x.name)}</b>
        <span class="num">전일 <b class="${updown(x.change_pct)}">${pct(x.change_pct, 2)}</b> · 1년 고점 대비 ${pct(x.drawdown)}</span></div>
      ${x.items.length ? `<ul class="brief-list">${x.items.map((it) =>
        `<li>${it.kind === "filing" ? `<span class="tag drop">공시</span> ` : ""}${esc(it.text)}
          <a class="src" href="${esc(it.link)}" target="_blank" rel="noopener">원문</a></li>`).join("")}</ul>`
        : `<p class="muted">특이사항 없음</p>`}
    </div>`).join("")}
    ${is.summary_on ? "" : `<p class="muted" style="margin-top:8px">뉴스 요약은 Claude 연결 후 표시됩니다. 지금은 공시만 보여줍니다.</p>`}
    ${(is.warnings || []).map((w) => `<p class="muted">⚠ ${esc(w)}</p>`).join("")}`;
}

function briefSchedule(s) {
  if (!s || s.error) return briefErr(s);
  if (!s.earnings.length) return `<p class="muted">이번 주 예정된 실적 발표 없음</p>`;
  return `<ul class="brief-list">${s.earnings.map((e) =>
    `<li><b>${esc(e.name)}</b> 실적 발표 <span class="num">${dayLabel(e.date)}</span>${e.time ? ` · ${esc(e.time)}` : ""} <span class="muted">(미국 날짜)</span></li>`).join("")}</ul>`;
}

async function renderBrief(date) {
  const { briefing: b, dates } = await api("/briefing" + (date ? `?date=${encodeURIComponent(date)}` : ""));
  if (!b) {
    view.innerHTML = `<div class="empty">아직 브리핑이 없습니다.<br>매일 오전 9시 전에 만들어집니다.</div>
      <p style="text-align:center"><button class="btn" id="brief-now">지금 만들기</button></p>`;
    $("#brief-now").onclick = makeBriefing;
    return;
  }
  const sec = (n, title, body) => `<section class="card brief"><h2><span class="page">${n}면</span>${title}</h2>${body}</section>`;
  view.innerHTML = `
    <div class="board-head">
      <span class="board-time"><b>${dayLabel(b.date)}</b> 아침 브리핑 · ${timeLabel(b.created_at)} 작성${b.is_practice ? " · 연습용 데이터" : ""}</span>
      <select id="brief-date" class="chip">${dates.map((d) => `<option value="${d}" ${d === b.date ? "selected" : ""}>${d}</option>`).join("")}</select>
    </div>
    ${sec(1, "내 계좌", briefAccount(b.account))}
    ${b.market_day ? sec(2, "매수권장 · 매수검토", briefZones(b.zones)) + sec(3, "Top 10 이슈", briefIssues(b.issues))
      : `<p class="muted" style="margin:0 4px 12px">일·월요일 아침은 전날 미국 장이 없어 계좌와 일정만 담습니다.</p>`}
    ${sec(4, "이번 주 일정", briefSchedule(b.schedule))}
    <p class="muted" style="margin:10px 4px">사실만 모았습니다. 3·4면 뉴스·공시는 알림 판단에 쓰지 않습니다.</p>
    <p style="text-align:center"><button class="btn ghost" id="brief-now">지금 다시 만들기</button></p>`;
  $("#brief-date").onchange = (e) => renderBrief(e.target.value);
  $("#brief-now").onclick = makeBriefing;
}

async function makeBriefing() {
  const btn = $("#brief-now");
  btn.disabled = true;
  btn.textContent = "만드는 중… (1분쯤 걸려요)";
  try {
    await api("/briefing", {});
    await renderBrief();
  } catch (e) {
    if (e.message !== "login") toast(e.message);
    btn.disabled = false;
    btn.textContent = "지금 만들기";
  }
}

function renderStage(stage, title, body) {
  view.innerHTML = `<section class="card"><span class="stage">${stage}</span><h2>${title}</h2><p>${body}</p></section>`;
}

// ---------- 종목 상세 ----------
function holdingSection(d) {
  const h = d.holding;
  if (!h) return "";
  const cls = h.pl_level > 0 ? "profit" : h.pl_level < 0 ? "loss" : "";
  return `<section class="card">
      <h2>내 보유</h2>
      <div class="stats">
        <div class="stat"><div class="k">수익률</div><div class="v num ${updown(h.return_pct)}">${pct(h.return_pct, 2)}</div></div>
        <div class="stat"><div class="k">평단</div><div class="v num" style="color:var(--avg)">${usd(h.avg_price)}</div></div>
        <div class="stat"><div class="k">보유</div><div class="v num">${h.qty.toLocaleString("en-US")}주</div></div>
      </div>
      ${h.pl_level ? `<p style="margin-top:10px"><span class="tag ${cls}">평단 대비 ${h.pl_level > 0 ? "+" : ""}${h.pl_level}% 구간</span></p>` : ""}
      <table class="zones" style="margin-top:12px">
        <thead><tr><th>평단 대비</th><th>가격</th></tr></thead>
        <tbody>${h.pl_prices.map((p) => {
          const hit = p.level > 0 ? h.return_pct >= p.level : h.return_pct <= p.level;
          return `<tr class="${hit ? "hit" : ""}"><td class="num ${p.level > 0 ? "up" : "down"}">${p.level > 0 ? "+" : ""}${p.level}%${hit ? " ✓" : ""}</td><td class="num">${usd(p.price)}</td></tr>`;
        }).join("")}</tbody>
      </table>
    </section>`;
}

function splitSection(d) {
  if (!d.fx) return "";
  const sp = d.split;
  const rows = sp ? sp.parts.map((p) => `<tr class="${p.done ? "done" : sp.next && sp.next.n === p.n ? "next" : ""}">
      <td>${p.n}차 (${p.ratio}%)${p.done ? " ✓" : ""}</td>
      <td class="num">${krw(p.amount)}</td>
      <td class="num">${p.done ? "완료" : "약 " + p.shares + "주"}</td></tr>`).join("") : "";
  return `<section class="card">
      <h2>3분할 계산기</h2>
      <p class="muted">이 종목에 넣을 총 투자금을 입력하면 30/30/40으로 나눕니다. 주문은 하지 않습니다.</p>
      <form class="split-form" id="split-form">
        <input id="split-total" inputmode="numeric" placeholder="총 투자금 (원)" value="${sp ? sp.total.toLocaleString("ko-KR") : ""}" aria-label="총 투자금 (원)">
        <button class="btn">계산</button>
      </form>
      ${sp ? `<table class="split">
        <thead><tr><th>차수</th><th>금액</th><th>현재가 기준</th></tr></thead>
        <tbody>${rows}</tbody></table>
        <p class="muted" style="margin-top:8px">지금까지 산 금액 약 ${krw(sp.invested)} · 남은 금액 ${krw(sp.remaining)} · 환율 ${d.fx.toLocaleString("ko-KR")}원</p>` : ""}
    </section>`;
}

async function renderStock(symbol) {
  const d = await api("/stock/" + encodeURIComponent(symbol));
  $("#title").textContent = d.name;
  const hit = (z) => d.drawdown <= -z.level;
  const showTier = d.in_top10;
  view.innerHTML = `
    <section class="card detail-head">
      <div class="muted">${esc(d.symbol)} · ${dayLabel(d.date)} 장 기준${d.in_top10 ? "" : " · Top 10 밖 보유 종목"}</div>
      <div class="price num">${usd(d.price)} <span class="num ${updown(d.change_pct)}" style="font-size:16px">전일 ${pct(d.change_pct, 2)}</span></div>
      ${showTier ? tierTag(d.tier, true) : ""}${d.new_high ? `<span class="tag newhigh big">신고가</span>` : ""}
      ${d.data_warning ? `<span class="tag warn big">오늘 데이터 확인 필요</span>` : ""}
      <div class="stats">
        <div class="stat high"><div class="k">1년 고점</div><div class="v num">${usd(d.high)}</div></div>
        <div class="stat"><div class="k">고점 대비</div><div class="v num">${pct(d.drawdown)}</div></div>
        <div class="stat"><div class="k">현재 구간</div><div class="v num">${d.level ? "-" + d.level + "%" : "-"}</div></div>
      </div>
    </section>
    ${holdingSection(d)}
    <section class="card">
      <h2>1년 가격</h2>
      <div class="chart-wrap" id="chart"></div>
      <div class="legend">
        <span><i style="border-color:var(--series)"></i>종가</span>
        <span><i style="border-color:var(--high)"></i>1년 고점</span>
        ${d.holding ? `<span><i style="border-color:var(--avg);border-top-style:dotted"></i>내 평단</span>` : ""}
        ${showTier ? `<span><i style="border-color:var(--review);border-top-style:dashed"></i>매수검토 시작 -5%</span>
        <span><i style="border-color:var(--buy);border-top-style:dashed"></i>매수권장 시작 -20%</span>` : ""}
      </div>
    </section>
    ${splitSection(d)}
    ${showTier ? `<section class="card">
      <h2>구간별 가격</h2>
      <p class="muted" style="margin-bottom:10px">1년 고점 ${usd(d.high)} 기준 · 이 가격 이하로 내려가면 알림</p>
      <table class="zones">
        <thead><tr><th>구간</th><th>가격</th></tr></thead>
        <tbody>${d.zones.map((z) => `<tr class="${hit(z) ? "hit" : ""}">
          <td class="num">-${z.level}%${hit(z) ? " ✓" : ""}<span class="lbl">${tierTag(z.tier)}</span></td>
          <td class="num">${usd(z.price)}</td></tr>`).join("")}</tbody>
      </table>
    </section>` : ""}
    <div class="section-title">이 종목 알림 기록</div>
    ${alertList(d.alerts)}
  `;
  drawChart($("#chart"), d);
  const form = $("#split-form");
  if (form) form.onsubmit = async (e) => {
    e.preventDefault();
    const total = Number($("#split-total").value.replace(/[^0-9]/g, "")) || 0;
    await api("/split/" + encodeURIComponent(d.symbol), { total_krw: total });
    toast(total ? "3분할 계획을 저장했습니다" : "3분할 계획을 지웠습니다");
    renderStock(d.symbol);
  };
}

// 1년 가격 선 하나 + 1년 고점·단계 시작선. 손가락을 대면 그날 가격이 보인다.
function drawChart(el, d) {
  // 화면 폭 그대로 그려야 글자가 작아지지 않는다
  const W = Math.max(280, el.clientWidth), H = 240, L = 4, R = 104, T = 12, B = 24;
  const pts = d.series;
  const closes = pts.map((p) => p.close);
  const refs = [{ cls: "high", v: d.high, label: "고점 " + usd(d.high) }];
  if (d.holding) refs.push({ cls: "avg", v: d.holding.avg_price, label: "평단 " + usd(d.holding.avg_price) });
  for (const z of d.in_top10 ? d.zones : []) {
    if (z.level === 5) refs.push({ cls: "review", v: z.price, label: "-5% " + usd(z.price) });
    if (z.level === 20) refs.push({ cls: "buy", v: z.price, label: "-20% " + usd(z.price) });
    if (z.level > 20 && d.level != null && z.level <= d.level) refs.push({ cls: "buy", v: z.price, label: `-${z.level}% ${usd(z.price)}` });
  }
  const lo = Math.min(...closes, ...refs.map((r) => r.v)) * 0.97;
  const hi = Math.max(d.high, ...closes) * 1.03;
  const x = (i) => L + (i / (pts.length - 1)) * (W - L - R);
  const y = (v) => T + (1 - (v - lo) / (hi - lo)) * (H - T - B);

  let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(d.name)} 1년 가격 그래프">`;
  let lastMonth = "";
  pts.forEach((p, i) => {
    const m = p.date.slice(0, 7);
    if (m !== lastMonth && i > 10 && i < pts.length - 10 && Number(m.slice(5)) % 3 === 1) {
      svg += `<line class="grid" x1="${x(i)}" x2="${x(i)}" y1="${T}" y2="${H - B}"/>`;
      svg += `<text class="axis" x="${x(i)}" y="${H - 8}" text-anchor="middle">${Number(m.slice(5))}월</text>`;
    }
    lastMonth = m;
  });
  // 기준선 라벨이 겹치면 아래로 밀어낸다
  refs.sort((a, b) => b.v - a.v);
  let lastY = -99;
  for (const r of refs) {
    const ry = y(r.v);
    const ly = Math.max(ry + 4, lastY + 14);
    lastY = ly;
    svg += `<line class="ref ${r.cls}" x1="${L}" x2="${W - R + 4}" y1="${ry}" y2="${ry}"/>`;
    svg += `<text class="ref-label ${r.cls}" x="${W - R + 8}" y="${ly}">${r.label}</text>`;
  }
  svg += `<path class="line" d="${pts.map((p, i) => (i ? "L" : "M") + x(i).toFixed(1) + " " + y(p.close).toFixed(1)).join("")}"/>`;
  svg += `<circle class="now" cx="${x(pts.length - 1)}" cy="${y(closes.at(-1))}" r="5"/>`;
  svg += `<line class="cross" id="cross" y1="${T}" y2="${H - B}" visibility="hidden"/>`;
  svg += `<circle class="hover-dot" id="hdot" r="5" visibility="hidden"/>`;
  svg += `<rect x="0" y="0" width="${W}" height="${H}" fill="transparent" id="hit"/></svg>`;
  svg += `<div class="tip" id="tip" hidden></div>`;
  el.innerHTML = svg;

  const svgEl = el.querySelector("svg"), cross = el.querySelector("#cross"),
    dot = el.querySelector("#hdot"), tip = el.querySelector("#tip");
  const move = (ev) => {
    const box = svgEl.getBoundingClientRect();
    const sx = ((ev.clientX - box.left) / box.width) * W;
    const i = Math.max(0, Math.min(pts.length - 1, Math.round(((sx - L) / (W - L - R)) * (pts.length - 1))));
    const p = pts[i], px = x(i), py = y(p.close);
    cross.setAttribute("x1", px); cross.setAttribute("x2", px); cross.setAttribute("visibility", "visible");
    dot.setAttribute("cx", px); dot.setAttribute("cy", py); dot.setAttribute("visibility", "visible");
    tip.hidden = false;
    tip.innerHTML = `${dayLabel(p.date)}<br><b class="num">${usd(p.close)}</b> · 고점 대비 ${pct((p.close / d.high - 1) * 100)}`;
    const left = (px / W) * box.width;
    tip.style.left = Math.max(70, Math.min(box.width - 70, left)) + "px";
  };
  const leave = () => { cross.setAttribute("visibility", "hidden"); dot.setAttribute("visibility", "hidden"); tip.hidden = true; };
  const hit = el.querySelector("#hit");
  hit.addEventListener("pointermove", move);
  hit.addEventListener("pointerdown", move);
  // 마우스는 벗어나면 숨기고, 손가락은 뗀 뒤에도 마지막 값을 보여준다
  hit.addEventListener("pointerleave", (e) => { if (e.pointerType === "mouse") leave(); });
}

// ---------- 설정 ----------
async function renderSettings() {
  const s = await api("/status");
  state.status = s;
  view.innerHTML = `
    <section class="card">
      <h2>알림 규칙</h2>
      <div class="setting"><span class="k">알림</span><span class="v">1년 고점 대비 -5%부터 5%p마다</span></div>
      <div class="setting"><span class="k"><span class="tag review">매수검토</span></span><span class="v">-5% ~ -15%</span></div>
      <div class="setting"><span class="k"><span class="tag buy">매수권장</span></span><span class="v">-20%부터 끝까지</span></div>
      <div class="setting"><span class="k"><span class="tag profit">수익</span> 내 종목</span><span class="v">평단 대비 +${s.profit_step}%마다</span></div>
      <div class="setting"><span class="k"><span class="tag loss">손실</span> 내 종목</span><span class="v">평단 대비 -${s.loss_step}%마다</span></div>
      <div class="setting"><span class="k">같은 종목·같은 구간</span><span class="v">하루 최대 1번</span></div>
      <div class="setting"><span class="k">경계선 여유</span><span class="v">${s.hysteresis}%p 이상 회복해야 구간 이탈</span></div>
      <div class="setting"><span class="k">하루 50% 이상 변동</span><span class="v">알림 대신 "데이터 확인"</span></div>
    </section>
    <section class="card">
      <h2>연결 상태</h2>
      <div class="setting"><span class="k">시세</span><span class="v">${esc(s.data_source)}</span></div>
      <div class="setting"><span class="k">키움 계좌</span><span class="v">${s.is_practice ? "연습용 보유 종목" : "연결됨 (조회 전용)"}</span></div>
      <div class="setting"><span class="k">마지막 알림 확인</span><span class="v num">${s.last_check ? esc(s.last_check.replace("T", " ").slice(0, 16)) : "-"}</span></div>
    </section>
    <button class="btn" id="check-now">지금 확인하기</button>
    ${s.login_required ? `<button class="btn secondary" id="logout">로그아웃</button>` : ""}
    <p class="muted" style="margin:16px 4px">이 앱은 조회만 합니다. 매수·매도 주문 기능은 없습니다.</p>
  `;
  $("#check-now").onclick = async () => {
    const r = await api("/check", {});
    toast(r.new_alerts.length ? `새 알림 ${r.new_alerts.length}개` : "새 알림이 없습니다");
    refreshStatus();
  };
  const lo = $("#logout");
  if (lo) lo.onclick = async () => { await api("/logout", {}); showLogin(); };
}

function showLogin() {
  document.body.classList.add("logged-out");
  $("#practice").hidden = true;
  $("#title").textContent = "로그인";
  view.innerHTML = `<form class="login" id="login">
      <h2>원칙 알림</h2>
      <p class="muted">사장님 전용 앱입니다</p>
      <input type="password" id="pw" autocomplete="current-password" placeholder="비밀번호" required>
      <div class="error" id="err"></div>
      <button class="btn">들어가기</button>
    </form>`;
  $("#login").onsubmit = async (e) => {
    e.preventDefault();
    try {
      await api("/login", { password: $("#pw").value });
      document.body.classList.remove("logged-out");
      await refreshStatus();
      route();
    } catch (err) { $("#err").textContent = err.message; }
  };
}

// ---------- 연습 모드 ----------
async function refreshStatus() {
  const s = await api("/status");
  state.status = s;
  if (!s.logged_in) { showLogin(); return s; }
  const bar = $("#practice");
  bar.hidden = !s.is_practice;
  if (s.is_practice) {
    const { stocks } = await api("/board");
    const day = stocks.map((x) => x.date).sort().at(-1);
    $("#practice-date").textContent = `${day ? dayLabel(day) + " 장 · " : ""}실제 시세가 아닙니다`;
    document.querySelectorAll("[data-advance]").forEach((b) => (b.disabled = !s.can_advance));
  }
  updateBadge((await api("/alerts")).alerts);
  return s;
}

function updateBadge(alerts) {
  const seen = Number(store("seenAlert") || 0);
  const n = alerts.filter((a) => a.id > seen).length;
  const b = $("#alert-badge");
  b.hidden = n === 0;
  b.textContent = n > 99 ? "99+" : n;
}

document.querySelectorAll("[data-advance]").forEach((btn) => {
  btn.onclick = async () => {
    btn.disabled = true;
    try {
      const r = await api("/practice/advance", { days: Number(btn.dataset.advance) });
      toast(r.new_alerts.length
        ? r.new_alerts.map((a) => `${a.name} ${a.kind === "data_check" ? "데이터 확인" : "-" + a.level + "%"}`).join(", ")
        : "새 알림 없음");
      await refreshStatus();
      route();
    } finally { btn.disabled = !state.status?.can_advance; }
  };
});
$("#practice-reset").onclick = async () => {
  await api("/practice/reset", {});
  store("seenAlert", "0");
  toast("연습을 처음부터 다시 시작합니다");
  await refreshStatus();
  route();
};

// ---------- 화면 이동 ----------
async function route() {
  if (document.body.classList.contains("logged-out")) return;
  const [, page = "home", arg] = location.hash.split("/");
  state.page = page;
  const tab = page === "stock" || page === "settings" ? null : page;
  document.querySelectorAll(".tabs a").forEach((a) => a.classList.toggle("active", a.dataset.tab === tab));
  $("#back").hidden = !(page === "stock" || page === "settings");
  $("#settings-btn").hidden = page === "settings";
  $("#title").textContent = TITLES[page] || "";
  try {
    if (page === "etf") renderStage("4단계에서 추가", "ETF Top 10", "규모(순자산) 상위 10개 ETF를 Top 10과 같은 방식으로 보여줍니다. 알림 기준도 같습니다.");
    else if (page === "brief") await renderBrief();
    else if (page === "mine") await renderMine();
    else if (page === "alerts") await renderAlerts();
    else if (page === "stock" && arg) await renderStock(decodeURIComponent(arg));
    else if (page === "settings") await renderSettings();
    else { state.page = "home"; await renderHome(); }
  } catch (e) {
    if (e.message !== "login") view.innerHTML = `<div class="empty">${esc(e.message)}</div>`;
  }
}

$("#back").onclick = () => (history.length > 1 ? history.back() : (location.hash = "#/home"));
$("#settings-btn").onclick = () => (location.hash = "#/settings");
window.addEventListener("hashchange", () => { route(); window.scrollTo(0, 0); });

(async () => {
  try {
    const s = await refreshStatus();
    if (s.logged_in) route();
  } catch (e) {
    if (e.message !== "login") view.innerHTML = `<div class="empty">서버에 연결할 수 없습니다</div>`;
  }
})();

if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
