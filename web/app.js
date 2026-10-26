// 원칙 알림 앱 화면. 서버 API에서 받은 숫자를 보여주기만 한다 (주문 기능 없음).
"use strict";

const $ = (sel) => document.querySelector(sel);
const view = $("#view");
const state = { status: null };

const TITLES = { home: "홈", watch: "관심 종목", etf: "ETF", brief: "브리핑", alerts: "알림", settings: "설정" };
const WEEK = ["일", "월", "화", "수", "목", "금", "토"];

// ---------- 공통 ----------
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const usd = (n) => "$" + Number(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const pct = (n, digits = 1) => (n > 0 ? "+" : "") + Number(n).toFixed(digits) + "%";
const updown = (n) => (n > 0 ? "up" : n < 0 ? "down" : "");
function dayLabel(iso) {
  const d = new Date(iso + "T00:00:00");
  return `${d.getMonth() + 1}/${d.getDate()} (${WEEK[d.getDay()]})`;
}
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

// ---------- 종목 행 ----------
function stockRow(s) {
  if (s.price === undefined) {
    return `<a class="row" href="#/stock/${encodeURIComponent(s.symbol)}">
      <div class="name">${esc(s.name)}<span class="sym">${esc(s.symbol)}</span></div>
      <div><span class="tag warn">데이터 확인 필요</span></div></a>`;
  }
  const inZone = s.level != null;
  const fall = Math.min(Math.abs(s.drawdown), 60);
  const toNext = (s.next_price / s.price - 1) * 100;
  return `<a class="row ${inZone ? "in-zone" : ""}" href="#/stock/${encodeURIComponent(s.symbol)}">
    <div class="name">${esc(s.name)}<span class="sym">${esc(s.symbol)}</span></div>
    <div class="price num">${usd(s.price)}</div>
    <div class="sub">${inZone ? `<span class="tag zone">매수 검토 -${s.level}% 구간</span>` : "1년 고점 " + usd(s.high)}
      ${s.data_warning ? ` <span class="tag warn">데이터 확인 필요</span>` : ""}</div>
    <div class="chg num ${updown(s.change_pct)}">${pct(s.change_pct, 2)}</div>
    <div class="dd">
      <span class="dd-val num">${pct(s.drawdown)}</span>
      <span class="meter" role="img" aria-label="1년 고점 대비 ${pct(s.drawdown)}">
        <span class="fill" style="width:${(fall / 60) * 100}%"></span>
        <span class="mark" style="left:50%"></span>
      </span>
    </div>
    <div class="next num">다음 알림 -${s.next_level}% · ${usd(s.next_price)} (지금보다 ${toNext.toFixed(1)}%)</div>
  </a>`;
}

function alertCard(a) {
  const isWarn = a.kind === "data_check";
  return `<a class="alert" href="#/stock/${encodeURIComponent(a.symbol)}">
    <div class="alert-head">
      <span class="tag ${isWarn ? "warn" : "zone"}">${isWarn ? "데이터 확인" : "매수 검토"}</span>
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

// ---------- 화면들 ----------
async function renderHome() {
  const [{ stocks }, { alerts }] = await Promise.all([api("/watchlist"), api("/alerts")]);
  const inZone = stocks.filter((s) => s.level != null);
  view.innerHTML = `
    <section class="card">
      <span class="stage">2단계에서 연결</span>
      <h2>내 보유 현황</h2>
      <p>키움 계좌를 연결하면 총 평가금액, 수익률, 보유 종목 카드가 여기에 나옵니다.</p>
    </section>
    <section class="card hero">
      <div class="label">시총 Top 10 중 매수 검토 구간 (1년 고점 대비 -30% 이상)</div>
      <div class="big num">${inZone.length}개 <span class="muted">/ ${stocks.length}개</span></div>
    </section>
    ${inZone.length ? `<div class="list">${inZone.map(stockRow).join("")}</div>` : ""}
    <div class="section-title">최근 알림 <a href="#/alerts">전체 보기</a></div>
    ${alerts.length ? alerts.slice(0, 3).map(alertCard).join("") : `<div class="empty">아직 받은 알림이 없습니다</div>`}
  `;
}

async function renderWatch() {
  const { stocks } = await api("/watchlist");
  view.innerHTML = `
    <p class="muted" style="margin:0 4px 10px">미국 시가총액 상위 10개 · 1년 고점 대비 하락률 큰 순서</p>
    <div class="list">${stocks.map(stockRow).join("")}</div>
    <p class="muted" style="margin:10px 4px">막대의 세로선이 -30% 지점입니다. 감시 목록은 매월 1회 갱신합니다.</p>
  `;
}

function renderStage(stage, title, body) {
  view.innerHTML = `<section class="card"><span class="stage">${stage}</span><h2>${title}</h2><p>${body}</p></section>`;
}

async function renderAlerts() {
  const { alerts } = await api("/alerts");
  if (alerts.length) store("seenAlert", String(alerts[0].id));
  updateBadge(alerts);
  view.innerHTML = alertList(alerts);
}

async function renderStock(symbol) {
  const d = await api("/stock/" + encodeURIComponent(symbol));
  $("#title").textContent = d.name;
  if (d.price === undefined) {
    view.innerHTML = `<section class="card"><span class="tag warn">데이터 확인 필요</span><p style="margin-top:8px">들어온 가격이 비정상이라 알림 판단에서 제외했습니다.</p></section>`;
    return;
  }
  const inZone = d.level != null;
  view.innerHTML = `
    <section class="card detail-head">
      <div class="muted">${esc(d.symbol)} · ${dayLabel(d.date)} 장 기준</div>
      <div class="price num">${usd(d.price)} <span class="num ${updown(d.change_pct)}" style="font-size:16px">${pct(d.change_pct, 2)}</span></div>
      ${inZone ? `<span class="tag zone">매수 검토 -${d.level}% 구간</span>` : ""}
      ${d.data_warning ? `<span class="tag warn">오늘 데이터 확인 필요</span>` : ""}
      <div class="stats">
        <div class="stat"><div class="k">1년 고점</div><div class="v num">${usd(d.high)}</div></div>
        <div class="stat"><div class="k">고점 대비</div><div class="v num">${pct(d.drawdown)}</div></div>
        <div class="stat"><div class="k">다음 알림</div><div class="v num">-${d.next_level}%</div></div>
      </div>
    </section>
    <section class="card">
      <h2>1년 가격</h2>
      <div class="chart-wrap" id="chart"></div>
      <div class="legend">
        <span><i style="border-color:var(--series)"></i>종가</span>
        <span><i style="border-color:var(--text-2);border-top-style:dashed"></i>1년 고점</span>
        <span><i style="border-color:var(--accent);border-top-style:dashed"></i>알림 구간</span>
      </div>
    </section>
    <section class="card">
      <h2>알림 구간 가격</h2>
      <p class="muted" style="margin-bottom:10px">1년 고점 ${usd(d.high)} 기준</p>
      <table class="zones">
        <thead><tr><th>구간</th><th>이 가격 이하면 알림</th></tr></thead>
        <tbody>${d.zones.map((z) => `<tr class="${d.level != null && z.level <= d.level ? "hit" : ""}">
          <td>-${z.level}%${d.level != null && z.level <= d.level ? " ✓" : ""}</td><td class="num">${usd(z.price)}</td></tr>`).join("")}</tbody>
      </table>
    </section>
    <section class="card">
      <span class="stage">2단계에서 연결</span>
      <h2>내 평단 · 3분할 계산기</h2>
      <p>키움 계좌를 연결하면 내 평단 선과 30/30/40 분할 금액이 여기에 나옵니다.</p>
    </section>
    <div class="section-title">이 종목 알림 기록</div>
    ${alertList(d.alerts)}
  `;
  drawChart($("#chart"), d);
}

// 1년 가격 선 하나 + 1년 고점·알림 구간 가로선. 손가락을 대면 그날 가격이 보인다.
function drawChart(el, d) {
  // 화면 폭 그대로 그려야 글자가 작아지지 않는다
  const W = Math.max(280, el.clientWidth), H = 240, L = 4, R = 96, T = 12, B = 24;
  const pts = d.series;
  const closes = pts.map((p) => p.close);
  const zoneLines = d.zones.filter((z) => z.level === 30 || (d.level != null && z.level <= d.level + 5));
  const lo = Math.min(...closes, ...zoneLines.map((z) => z.price)) * 0.97;
  const hi = d.high * 1.03;
  const x = (i) => L + (i / (pts.length - 1)) * (W - L - R);
  const y = (v) => T + (1 - (v - lo) / (hi - lo)) * (H - T - B);

  let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(d.name)} 1년 가격 그래프">`;
  // 월 눈금
  let lastMonth = "";
  pts.forEach((p, i) => {
    const m = p.date.slice(0, 7);
    if (m !== lastMonth && i > 10 && i < pts.length - 10 && Number(m.slice(5)) % 3 === 1) {
      svg += `<line class="grid" x1="${x(i)}" x2="${x(i)}" y1="${T}" y2="${H - B}"/>`;
      svg += `<text class="axis" x="${x(i)}" y="${H - 8}" text-anchor="middle">${Number(m.slice(5))}월</text>`;
    }
    lastMonth = m;
  });
  // 기준선: 라벨이 겹치면 아래로 밀어낸다
  const refs = [{ cls: "high", v: d.high, label: "고점 " + usd(d.high) },
    ...zoneLines.map((z) => ({ cls: "zone", v: z.price, label: `-${z.level}% ${usd(z.price)}` }))];
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

async function renderSettings() {
  const s = await api("/status");
  state.status = s;
  view.innerHTML = `
    <section class="card">
      <h2>알림 규칙</h2>
      <div class="setting"><span class="k">매수 검토 알림</span><span class="v">1년 고점 대비 -${s.buy_zone_start}%부터 ${s.buy_zone_step}%p마다</span></div>
      <div class="setting"><span class="k">같은 종목·같은 구간</span><span class="v">하루 최대 1번</span></div>
      <div class="setting"><span class="k">하루 50% 이상 변동</span><span class="v">알림 대신 "데이터 확인"</span></div>
      <div class="setting"><span class="k">보유 종목 알림</span><span class="v muted">2단계</span></div>
    </section>
    <section class="card">
      <h2>연결 상태</h2>
      <div class="setting"><span class="k">시세</span><span class="v">${esc(s.data_source)}</span></div>
      <div class="setting"><span class="k">키움 계좌</span><span class="v muted">2단계에서 연결</span></div>
      <div class="setting"><span class="k">마지막 확인</span><span class="v num">${s.last_check ? esc(s.last_check.replace("T", " ").slice(0, 16)) : "-"}</span></div>
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
    const { stocks } = await api("/watchlist");
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
  const tab = page === "stock" ? null : page;
  document.querySelectorAll(".tabs a").forEach((a) => a.classList.toggle("active", a.dataset.tab === tab));
  $("#back").hidden = !(page === "stock" || page === "settings");
  $("#settings-btn").hidden = page === "settings";
  $("#title").textContent = TITLES[page] || "";
  try {
    if (page === "watch") await renderWatch();
    else if (page === "etf") renderStage("4단계에서 추가", "ETF Top 10", "규모(순자산) 상위 10개 ETF를 관심 종목과 같은 방식으로 보여줍니다. 알림 기준도 같습니다 (-30%부터 5%p마다).");
    else if (page === "brief") renderStage("3단계에서 추가", "아침 브리핑", "매일 오전 9시, 밤사이 알림과 Top 10 이슈를 신문처럼 한 번에 모아 보여줍니다. 지난 브리핑도 날짜별로 다시 볼 수 있습니다.");
    else if (page === "alerts") await renderAlerts();
    else if (page === "stock" && arg) await renderStock(decodeURIComponent(arg));
    else if (page === "settings") await renderSettings();
    else await renderHome();
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
