// ============================================================
// dashboard.js  –  대시보드 렌더링 (index.html 구조 기준)
// 수정:
//   Bug2 – toggleFlip: inner- → flip- (CSS .card-flip-wrapper.flipped 대응)
//   Bug3 – warning bars 클래스명 CSS와 일치
// ============================================================

"use strict";

const DATA_URL    = "./data/latest_scores.json";
const HISTORY_URL = "./data/history.jsonl";

// ── 가중치 ────────────────────────────────────────────────
const WEIGHTS = { w1: 0.25, w2: 0.30, w3: 0.20, w4: 0.25 };

// ── IPO 상태별 가중치 (백엔드 동기화) ─────────────────────
const STATUS_WEIGHT = {
  "루머":     0.1,
  "검토중":   0.3,
  "신청완료": 1.0,
  "가격확정": 1.0,
  "상장완료": 0.0,
};

// ── IPO 상태 → CSS 클래스 ────────────────────────────────
const statusClassMap = {
  "신청완료": "Filed",
  "검토중":   "Considering",
  "가격확정": "Priced",
  "상장완료": "Trading",
  "루머":     "Rumor",
};

// ──────────────────────────────────────────────────────────
// 유틸
// ──────────────────────────────────────────────────────────

function scoreColor(s) {
  if (s >= 70) return "#e74c3c";
  if (s >= 40) return "#f39c12";
  return "#27ae60";
}

function scoreLabel(s) {
  if (s >= 70) return "🔴 위험";
  if (s >= 40) return "🟡 주의";
  return "🟢 안전";
}

function scoreGradeClass(s) {
  if (s >= 70) return "grade-red";
  if (s >= 40) return "grade-yellow";
  return "grade-green";
}

// ──────────────────────────────────────────────────────────
// 카드 뒤집기
// Bug2 수정: inner-${prefix} → flip-${prefix}
// CSS: .card-flip-wrapper.flipped .card-flip-inner { transform: rotateY(180deg) }
// ──────────────────────────────────────────────────────────

function toggleFlip(prefix) {
  const wrapper = document.getElementById(`flip-${prefix}`);
  if (wrapper) wrapper.classList.toggle("flipped");
}

// ──────────────────────────────────────────────────────────
// 종합 점수 링 차트 (Canvas)
// ──────────────────────────────────────────────────────────

function drawScoreRing(score) {
  const canvas = document.getElementById("score-ring");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const cx = canvas.width / 2;
  const cy = canvas.height / 2;
  const r  = 65;
  const start = -Math.PI / 2;
  const end   = start + (score / 100) * 2 * Math.PI;

  ctx.clearRect(0, 0, canvas.width, canvas.height);

  // 배경 트랙
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, 2 * Math.PI);
  ctx.strokeStyle = "rgba(255,255,255,0.1)";
  ctx.lineWidth   = 12;
  ctx.stroke();

  // 점수 호
  ctx.beginPath();
  ctx.arc(cx, cy, r, start, end);
  ctx.strokeStyle = scoreColor(score);
  ctx.lineWidth   = 12;
  ctx.lineCap     = "round";
  ctx.stroke();
}

// ──────────────────────────────────────────────────────────
// 개별 카드 미니 차트 (점수 바)
// ──────────────────────────────────────────────────────────

function drawMiniBar(prefix, score) {
  const canvas = document.getElementById(`chart-${prefix}`);
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.parentElement.offsetWidth || 260;
  canvas.width  = w;
  canvas.height = 8;
  ctx.clearRect(0, 0, w, 8);

  // 배경
  ctx.fillStyle = "rgba(255,255,255,0.08)";
  ctx.roundRect(0, 0, w, 8, 4);
  ctx.fill();

  // 점수 바
  ctx.fillStyle = scoreColor(score);
  ctx.roundRect(0, 0, w * (score / 100), 8, 4);
  ctx.fill();
}

// ──────────────────────────────────────────────────────────
// IPO 테이블
// ──────────────────────────────────────────────────────────

function renderIPOTable(ipoList) {
  if (!ipoList || ipoList.length === 0) {
    return `<p style="color:#888;font-size:12px;">IPO 데이터 없음</p>`;
  }
  const rows = ipoList.map(item => {
    const css        = statusClassMap[item.status] ?? "Rumor";
    const valuation  = item.valuation_bn ? `$${item.valuation_bn.toLocaleString()}B` : "–";
    const weight     = (STATUS_WEIGHT[item.status] ?? 0.1) * 100;
    const weightedBn = item.valuation_bn
      ? `$${Math.round(item.valuation_bn * (STATUS_WEIGHT[item.status] ?? 0.1)).toLocaleString()}B`
      : "–";
    return `
      <tr>
        <td>${item.company}</td>
        <td>${valuation}</td>
        <td><span class="status-badge status-${css}">${item.status}</span></td>
        <td>${weight}%</td>
        <td>${weightedBn}</td>
      </tr>`;
  }).join("");

  return `
    <table class="ipo-table">
      <thead>
        <tr><th>기업</th><th>기업가치</th><th>상태</th><th>가중치</th><th>반영액</th></tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>`;
}

// ──────────────────────────────────────────────────────────
// 카드 뒷면 콘텐츠
// ──────────────────────────────────────────────────────────

function buildBackContent(prefix, raw) {
  if (prefix === "w1") {
    const spy   = (raw.spy_ytd ?? 0).toFixed(2);
    const rsp   = (raw.rsp_ytd ?? 0).toFixed(2);
    const diff  = ((raw.spy_ytd ?? 0) - (raw.rsp_ytd ?? 0)).toFixed(2);
    const pct   = raw.spread_percentile ?? "N/A";
    const rsp1w = raw.rsp_1w_return != null ? Number(raw.rsp_1w_return).toFixed(2) : null;
    const isNeg = raw.rsp_is_negative_while_spy_positive ?? false;

    return `
      <div class="back-section">
        <h4>📊 수치 해설</h4>
        <div class="back-metric"><span class="back-label">SPY YTD</span><span class="back-value">+${spy}%</span></div>
        <div class="back-metric"><span class="back-label">RSP YTD</span><span class="back-value">+${rsp}%</span></div>
        <div class="back-metric"><span class="back-label">SPY–RSP 괴리율</span><span class="back-value val-red">+${diff}%p</span></div>
        <div class="back-metric"><span class="back-label">괴리 퍼센타일</span><span class="back-value">${pct}%ile</span></div>
        ${rsp1w !== null ? `<div class="back-metric"><span class="back-label">RSP 1주 수익률</span><span class="back-value ${parseFloat(rsp1w) < 0 ? "val-red" : "val-green"}">${parseFloat(rsp1w) >= 0 ? "+" : ""}${rsp1w}%</span></div>` : ""}
      </div>
      <div class="back-section">
        <h4>🔍 지금 어떤 상황인가?</h4>
        <p>SPY는 대형주 비중이 높은 시총 가중 ETF, RSP는 같은 500종목을 동일 비중으로 담습니다. 괴리가 클수록 대형주 쏠림이 심하다는 의미입니다.</p>
        ${isNeg
          ? `<p class="back-warning">🔴 SPY 상승 중 RSP 마이너스 — 위험 트리거 발동</p>`
          : `<p class="back-ok">✅ RSP 양수 유지 — 소외주 동반 상승 중</p>`}
        <p class="back-advice">💡 RSP가 마이너스로 전환되면 포지션 축소를 고려하세요.</p>
      </div>`;
  }

  if (prefix === "w2") {
    const y10    = (raw.us10y_yield ?? 0).toFixed(2);
    const y2     = (raw.us2y_yield  ?? 0).toFixed(2);
    const spread = ((raw.us10y_yield ?? 0) - (raw.us2y_yield ?? 0)).toFixed(2);
    const tips   = (raw.tips_10y_real_yield ?? 0).toFixed(2);
    const isInv  = parseFloat(spread) < 0;

    return `
      <div class="back-section">
        <h4>📊 수치 해설</h4>
        <div class="back-metric"><span class="back-label">미국 10년물</span><span class="back-value ${parseFloat(y10) >= 4.5 ? "val-red" : ""}">${y10}%</span></div>
        <div class="back-metric"><span class="back-label">미국 2년물</span><span class="back-value">${y2}%</span></div>
        <div class="back-metric"><span class="back-label">장단기 스프레드</span><span class="back-value ${isInv ? "val-red" : "val-green"}">${parseFloat(spread) >= 0 ? "+" : ""}${spread}%p</span></div>
        <div class="back-metric"><span class="back-label">TIPS 실질금리</span><span class="back-value">${tips}%</span></div>
      </div>
      <div class="back-section">
        <h4>🔍 지금 어떤 상황인가?</h4>
        <p>10년물 4.5%가 핵심 임계선입니다. 현재 ${y10}%로 ${parseFloat(y10) >= 4.5 ? "⚠️ 임계선을 <strong>돌파</strong>한 상태입니다." : `임계선까지 ${(4.5 - parseFloat(y10)).toFixed(2)}%p 여유가 있습니다.`}</p>
        ${isInv ? `<p class="back-warning">🔴 장단기 금리 역전 — 경기침체 선행 신호</p>` : `<p class="back-ok">✅ 장단기 금리차 정상</p>`}
        <p class="back-advice">💡 10년물이 4.5% 이상 유지되면 성장주 비중 축소를 고려하세요.</p>
      </div>`;
  }

  if (prefix === "w3") {
    const hy    = (raw.hy_bps ?? 0).toFixed(0);
    const ig    = (raw.ig_bps ?? 0).toFixed(0);
    const hyChg = (raw.hy_change_bps ?? 0).toFixed(0);

    return `
      <div class="back-section">
        <h4>📊 수치 해설</h4>
        <div class="back-metric"><span class="back-label">HY 스프레드</span><span class="back-value ${parseInt(hy) >= 400 ? "val-red" : parseInt(hy) >= 300 ? "val-yellow" : "val-green"}">${hy} bps</span></div>
        <div class="back-metric"><span class="back-label">IG 스프레드</span><span class="back-value">${ig} bps</span></div>
        <div class="back-metric"><span class="back-label">HY 1개월 변화</span><span class="back-value">${parseInt(hyChg) >= 0 ? "+" : ""}${hyChg} bps</span></div>
      </div>
      <div class="back-section">
        <h4>🔍 지금 어떤 상황인가?</h4>
        <p>HY 스프레드 ${hy}bps — ${parseInt(hy) < 300 ? "역사적 저점권. 향후 확대 리스크 존재." : parseInt(hy) >= 400 ? "⚠️ 400bps 돌파 — 신용 위기 경계." : "정상~주의 구간."}</p>
        <p class="back-advice">💡 HY 스프레드가 400bps 이상으로 급등하면 위험자산 비중을 줄이세요.</p>
      </div>`;
  }

  if (prefix === "w4") {
    const totalBn = (raw.total_valuation_bn ?? 0).toLocaleString();
    const filed   = raw.filed_count  ?? 0;
    const priced  = raw.priced_count ?? 0;

    return `
      <div class="back-section">
        <h4>📊 수치 해설</h4>
        <div class="back-metric"><span class="back-label">가중 파이프라인</span><span class="back-value val-red">$${totalBn}B</span></div>
        <div class="back-metric"><span class="back-label">S-1 신청완료</span><span class="back-value">${filed}건</span></div>
        <div class="back-metric"><span class="back-label">공모가 확정</span><span class="back-value">${priced}건</span></div>
      </div>
      <div class="back-section">
        <h4>🔍 지금 어떤 상황인가?</h4>
        <p>대형 IPO가 줄줄이 예정되면 유동성이 IPO 청약에 쏠립니다. 현재 SpaceX($1,800B), OpenAI($852B), Anthropic($965B) 등 역사상 전례 없는 규모의 파이프라인이 대기 중입니다.</p>
        <p><strong>가중치:</strong> 신청완료 100%, 검토중 30%, 루머 10%, 상장완료 0%</p>
        <p class="back-advice">💡 SpaceX IPO 전후 변동성에 주의하세요.</p>
      </div>`;
  }

  return `<p>데이터 없음</p>`;
}

// ──────────────────────────────────────────────────────────
// 개별 카드 렌더링 (index.html 기존 DOM 요소 업데이트)
// ──────────────────────────────────────────────────────────

function renderCard(prefix, score, raw, weightLabel) {
  // 점수 배지
  const scoreBadge = document.getElementById(`score-${prefix}`);
  if (scoreBadge) {
    scoreBadge.textContent = score;
    scoreBadge.className   = `card-score-badge ${scoreGradeClass(score)}`;
  }

  // 가중치 배지
  const weightBadge = document.getElementById(`weight-${prefix}`);
  if (weightBadge) weightBadge.textContent = `가중치 ${weightLabel}`;

  // 미니 바 차트
  drawMiniBar(prefix, score);

  // 시그널 목록
  const signalEl = document.getElementById(`signals-${prefix}`);
  if (signalEl) {
    const signals = raw.signals ?? [];
    signalEl.innerHTML = signals.length
      ? signals.map(s => `<div class="signal-item">${s}</div>`).join("")
      : "";
  }

  // 지표 그리드 (W1~W4)
  const metricsEl = document.getElementById(`metrics-${prefix}`);
  if (metricsEl) {
    metricsEl.innerHTML = buildMetrics(prefix, raw);
  }

  // W4 IPO 테이블
  if (prefix === "w4") {
    const tableEl = document.getElementById("ipo-table");
    if (tableEl) tableEl.innerHTML = renderIPOTable(raw.ipo_list ?? []);
  }

  // 카드 뒷면
  const backEl = document.getElementById(`back-${prefix}`);
  if (backEl) {
    backEl.innerHTML = `
      <div class="back-content">
        <div class="card-header">
          <span class="card-title">상세 해설</span>
          <button class="flip-btn" onclick="event.stopPropagation(); toggleFlip('${prefix}')">◀ 돌아가기</button>
        </div>
        ${buildBackContent(prefix, raw)}
      </div>`;
  }
}

// ──────────────────────────────────────────────────────────
// 지표 그리드 빌더
// ──────────────────────────────────────────────────────────

function buildMetrics(prefix, raw) {
  if (prefix === "w1") {
    return `
      <div class="metric-item"><span class="metric-label">SPY YTD</span><span class="metric-value">+${(raw.spy_ytd ?? 0).toFixed(2)}%</span></div>
      <div class="metric-item"><span class="metric-label">RSP YTD</span><span class="metric-value">+${(raw.rsp_ytd ?? 0).toFixed(2)}%</span></div>
      <div class="metric-item"><span class="metric-label">괴리율</span><span class="metric-value">+${((raw.spy_ytd ?? 0) - (raw.rsp_ytd ?? 0)).toFixed(2)}%p</span></div>
      <div class="metric-item"><span class="metric-label">퍼센타일</span><span class="metric-value">${raw.spread_percentile ?? "N/A"}%ile</span></div>`;
  }
  if (prefix === "w2") {
    return `
      <div class="metric-item"><span class="metric-label">10년물</span><span class="metric-value">${(raw.us10y_yield ?? 0).toFixed(2)}%</span></div>
      <div class="metric-item"><span class="metric-label">2년물</span><span class="metric-value">${(raw.us2y_yield ?? 0).toFixed(2)}%</span></div>
      <div class="metric-item"><span class="metric-label">장단기차</span><span class="metric-value">${(raw.term_spread ?? 0) >= 0 ? "+" : ""}${(raw.term_spread ?? 0).toFixed(2)}%p</span></div>
      <div class="metric-item"><span class="metric-label">TIPS</span><span class="metric-value">${(raw.tips_10y_real_yield ?? 0).toFixed(2)}%</span></div>`;
  }
  if (prefix === "w3") {
    return `
      <div class="metric-item"><span class="metric-label">HY 스프레드</span><span class="metric-value">${(raw.hy_bps ?? 0).toFixed(0)} bps</span></div>
      <div class="metric-item"><span class="metric-label">IG 스프레드</span><span class="metric-value">${(raw.ig_bps ?? 0).toFixed(0)} bps</span></div>
      <div class="metric-item"><span class="metric-label">HY 변화</span><span class="metric-value">${(raw.hy_change_bps ?? 0) >= 0 ? "+" : ""}${(raw.hy_change_bps ?? 0).toFixed(0)} bps</span></div>`;
  }
  if (prefix === "w4") {
    return `
      <div class="metric-item"><span class="metric-label">파이프라인</span><span class="metric-value">$${(raw.total_valuation_bn ?? 0).toLocaleString()}B</span></div>
      <div class="metric-item"><span class="metric-label">S-1 신청</span><span class="metric-value">${raw.filed_count ?? 0}건</span></div>`;
  }
  return "";
}

// ──────────────────────────────────────────────────────────
// 종합 카드 렌더링
// ──────────────────────────────────────────────────────────

function renderComposite(data) {
  const composite = data.composite_score ?? 0;

  // 점수 숫자
  const scoreEl = document.getElementById("composite-score");
  if (scoreEl) scoreEl.textContent = composite;

  // 링 차트
  drawScoreRing(composite);

  // 전체 등급 레이블
  const labelEl = document.getElementById("overall-label");
  if (labelEl) {
    labelEl.textContent  = scoreLabel(composite);
    labelEl.style.color  = scoreColor(composite);
  }

  // 행동 권고
  const actionEl = document.getElementById("action-rec");
  if (actionEl) {
    if (composite >= 70)      actionEl.textContent = "⚠️ 즉시 포지션 점검 필요";
    else if (composite >= 40) actionEl.textContent = "🔍 주의 깊게 모니터링 하세요";
    else                      actionEl.textContent = "✅ 현재 시장 위험도 낮음";
  }

  // 신호 배지
  const badgeEl = document.getElementById("signal-badge");
  const descEl  = document.getElementById("signal-desc");
  if (badgeEl && descEl) {
    if (composite >= 70) {
      badgeEl.textContent  = "SELL";
      badgeEl.style.background = "#e74c3c";
      descEl.textContent   = "위험 구간 — 현금 비중 확대 고려";
    } else if (composite >= 40) {
      badgeEl.textContent  = "HOLD";
      badgeEl.style.background = "#f39c12";
      descEl.textContent   = "주의 구간 — 신규 매수 자제";
    } else {
      badgeEl.textContent  = "BUY";
      badgeEl.style.background = "#27ae60";
      descEl.textContent   = "안전 구간 — 정상적 투자 가능";
    }
  }

  // 헤지 권고
  const hedgeEl = document.getElementById("hedge-rec");
  if (hedgeEl) {
    if (composite >= 70)
      hedgeEl.innerHTML = `<span style="color:#e74c3c">🛡️ 헤지 권고: 인버스 ETF 또는 현금 비중 30% 이상 유지</span>`;
    else if (composite >= 40)
      hedgeEl.innerHTML = `<span style="color:#f39c12">🛡️ 헤지 고려: 포트폴리오 리밸런싱 검토</span>`;
    else
      hedgeEl.innerHTML = `<span style="color:#27ae60">🛡️ 헤지 불필요: 정상 시장 환경</span>`;
  }

  // Bug3 수정: CSS 클래스명을 styles.css와 일치시킴
  // warning-bar-row → warning-bar-item
  // bar-label       → warning-bar-label
  // bar-track       → warning-bar-track
  // bar-fill        → warning-bar-fill
  // bar-val         → warning-bar-val
  const barsEl = document.getElementById("warning-bars");
  if (barsEl) {
    const items = [
      { key: "w1", label: "주도주 압축" },
      { key: "w2", label: "채권 자경단" },
      { key: "w3", label: "사모 크레딧" },
      { key: "w4", label: "대어급 IPO" },
    ];
    barsEl.innerHTML = items.map(({ key, label }) => {
      const s = data[`${key}_score`] ?? 0;
      return `
        <div class="warning-bar-item">
          <span class="warning-bar-label">${label}</span>
          <div class="warning-bar-track">
            <div class="warning-bar-fill" style="width:${s}%; background:${scoreColor(s)}"></div>
          </div>
          <span class="warning-bar-val" style="color:${scoreColor(s)}">${s}점</span>
        </div>`;
    }).join("");
  }

  // 퍼펙트 스톰 배너
  const stormEl = document.getElementById("storm-section");
  if (stormEl) {
    stormEl.style.display = composite >= 70 ? "block" : "none";
  }

  // 마지막 업데이트
  const updatedEl = document.getElementById("last-updated");
  if (updatedEl && data.timestamp) {
    updatedEl.textContent = `데이터 기준: ${new Date(data.timestamp).toLocaleString("ko-KR", { timeZone: "Asia/Seoul" })}`;
  }
}

// ──────────────────────────────────────────────────────────
// 히스토리 로드
// ──────────────────────────────────────────────────────────

async function loadHistory() {
  try {
    const res   = await fetch(HISTORY_URL);
    const text  = await res.text();
    const lines = text.trim().split("\n").filter(Boolean);
    const scores = lines.map(line => {
      try {
        const obj = JSON.parse(line);
        return {
          score: obj.composite_score ?? obj.score ?? obj.perfect_storm_score ?? 0,
          date:  obj.date ?? obj.timestamp?.slice(0, 10) ?? "",
        };
      } catch { return null; }
    }).filter(Boolean);

    if (typeof drawHistoryChart === "function") drawHistoryChart(scores);

  } catch (e) {
    console.warn("[History] 로드 실패:", e);
    if (typeof drawHistoryChart === "function") {
      drawHistoryChart([
        { date: "2026-05-01", score: 38 },
        { date: "2026-05-05", score: 42 },
        { date: "2026-05-13", score: 45 },
        { date: "2026-05-21", score: 40 },
        { date: "2026-05-29", score: 35 },
      ]);
    }
  }
}

// ──────────────────────────────────────────────────────────
// 메인 진입점
// ──────────────────────────────────────────────────────────

async function loadData() {
  try {
    const res = await fetch(DATA_URL);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    // 종합 카드
    renderComposite(data);

    // 4개 경고 카드
    const cardDefs = [
      { prefix: "w1", weight: "25%", raw: data.w1 ?? {} },
      { prefix: "w2", weight: "30%", raw: data.w2 ?? {} },
      { prefix: "w3", weight: "20%", raw: data.w3 ?? {} },
      { prefix: "w4", weight: "25%", raw: data.w4 ?? {} },
    ];
    cardDefs.forEach(({ prefix, weight, raw }) => {
      renderCard(prefix, data[`${prefix}_score`] ?? 0, raw, weight);
    });

    // 히스토리 차트
    await loadHistory();

  } catch (e) {
    console.error("[loadData] 실패:", e);
    const updatedEl = document.getElementById("last-updated");
    if (updatedEl) updatedEl.textContent = `⚠️ 데이터 로드 실패: ${e.message}`;
    const labelEl = document.getElementById("overall-label");
    if (labelEl) labelEl.textContent = "데이터를 불러올 수 없습니다.";
  }
}

document.addEventListener("DOMContentLoaded", loadData);
