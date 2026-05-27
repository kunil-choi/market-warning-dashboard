"use strict";

const DATA_URL    = "./data/latest_scores.json";
const HISTORY_URL = "./data/history.jsonl";

function scoreBarColor(score) {
  if (score >= 70) return "#ef4444";
  if (score >= 50) return "#f97316";
  if (score >= 35) return "#eab308";
  return "#10b981";
}

function gradeClass(grade) {
  const map = {
    HIGH: "grade-HIGH",
    CRITICAL: "grade-CRITICAL",
    PERFECT_STORM: "grade-CRITICAL",
  };
  return map[grade] || "";
}

// ── 전체 렌더 ──
function renderDashboard(data) {
  const comp   = data.composite;
  const warns  = data.warnings;
  const signal = data.algo_signal;

  // 종합 스코어 링
  drawScoreRing(comp.final_score);

  // 카드 등급
  const compCard = document.getElementById("composite-card");
  compCard.className = `composite-card ${gradeClass(comp.overall_grade)}`;

  // 헤더 텍스트
  const labelEl = document.getElementById("overall-label");
  labelEl.textContent  = comp.overall_label;
  labelEl.style.color  = comp.overall_color;

  document.getElementById("action-rec").textContent = `📌 ${comp.action_recommended}`;

  // 시그널
  const badge = document.getElementById("signal-badge");
  badge.textContent       = signal.signal;
  badge.style.background  = signal.signal_color;
  document.getElementById("signal-desc").textContent = signal.signal_desc;
  document.getElementById("hedge-rec").textContent   = signal.hedge_rec;

  // 마지막 갱신
  const dt = new Date(data.meta.generated_at);
  document.getElementById("last-updated").textContent =
    `마지막 갱신: ${dt.toLocaleString("ko-KR")}`;

  // 퍼펙트 스톰 배너
  document.getElementById("storm-section").style.display =
    comp.overall_grade === "PERFECT_STORM" ? "block" : "none";

  // 경고등 바
  const warningList = [
    { id: "w1_liquidity", label: "W1 주도주 압축" },
    { id: "w2_rates",     label: "W2 채권 자경단" },
    { id: "w3_credit",    label: "W3 사모 크레딧" },
    { id: "w4_ipo",       label: "W4 대어급 IPO"  },
  ];

  document.getElementById("warning-bars").innerHTML = warningList.map(w => {
    const s = warns[w.id].score;
    const c = scoreBarColor(s);
    return `
      <div class="warning-bar-item">
        <span class="warning-bar-label">${w.label}</span>
        <div class="warning-bar-track">
          <div class="warning-bar-fill" style="width:${s}%;background:${c}"></div>
        </div>
        <span class="warning-bar-val" style="color:${c}">${s.toFixed(0)}</span>
      </div>`;
  }).join("");

  // 4개 카드
  renderWarningCard("w1", warns.w1_liquidity);
  renderWarningCard("w2", warns.w2_rates);
  renderWarningCard("w3", warns.w3_credit);
  renderWarningCard("w4", warns.w4_ipo);

  // 차트
  const liqRaw = warns.w1_liquidity.raw_data;
  if (liqRaw?.history_90d) drawLiquidityChart("chart-w1", liqRaw.history_90d);

  const ratesRaw = warns.w2_rates.raw_data;
  if (ratesRaw?.history) drawRatesChart("chart-w2", ratesRaw.history);

  const creditRaw = warns.w3_credit.raw_data;
  if (creditRaw?.history) drawCreditChart("chart-w3", creditRaw.history);

  // IPO 테이블
  renderIPOTable(warns.w4_ipo.raw_data);
}

// ── 경고등 카드 ──
function renderWarningCard(prefix, warn) {
  const card = document.getElementById(`card-${prefix}`);
  if (!card) return;

  card.className = `warning-card ${gradeClass(warn.grade)}`;

  const scoreBadge = document.getElementById(`score-${prefix}`);
  if (scoreBadge) {
    scoreBadge.textContent  = warn.score.toFixed(1);
    scoreBadge.style.color  = warn.grade_color;
  }

  // 지표
  const metricsEl = document.getElementById(`metrics-${prefix}`);
  if (metricsEl && warn.key_metrics) {
    metricsEl.innerHTML = Object.entries(warn.key_metrics).map(([k, v]) => `
      <div class="metric-item">
        <div class="metric-label">${k}</div>
        <div class="metric-value">${v}</div>
      </div>`).join("");
  }

  // 시그널
  const signalsEl = document.getElementById(`signals-${prefix}`);
  if (signalsEl) {
    signalsEl.innerHTML = (warn.signals && warn.signals.length > 0)
      ? warn.signals.map(sig => `
          <div class="signal-item ${sig.level}">
            <span class="signal-dot ${sig.level}"></span>
            <span>${sig.msg}</span>
          </div>`).join("")
      : `<div class="signal-item GREEN">
           <span class="signal-dot GREEN"></span>
           <span>이상 없음</span>
         </div>`;
  }
}

// ── IPO 테이블 ──
function renderIPOTable(rawData) {
  const el = document.getElementById("ipo-table");
  if (!el || !rawData?.mega_ipo_pipeline) return;

  el.innerHTML = `
    <table class="ipo-table">
      <thead>
        <tr>
          <th>기업</th><th>섹터</th><th>추정 기업가치</th><th>상태</th>
        </tr>
      </thead>
      <tbody>
        ${rawData.mega_ipo_pipeline.map(p => `
          <tr>
            <td><strong>${p.company}</strong></td>
            <td>${p.sector}</td>
            <td>$${p.est_valuation_bn}B</td>
            <td><span class="status-badge status-${p.status}">${p.status}</span></td>
          </tr>`).join("")}
        <tr style="background:rgba(239,68,68,0.08)">
          <td colspan="2"><strong>총 파이프라인</strong></td>
          <td><strong style="color:#ef4444">$${rawData.total_pipeline_bn}B</strong></td>
          <td><small style="color:#64748b">한국 GDP의 ${rawData.pipeline_vs_korea_gdp_ratio}배</small></td>
        </tr>
      </tbody>
    </table>`;
}

// ── 히스토리 ──
async function loadHistory() {
  try {
    const res  = await fetch(HISTORY_URL);
    const text = await res.text();
    const history = text.trim().split("\n")
      .filter(l => l.trim())
      .map(l => JSON.parse(l))
      .slice(-90);
    drawHistoryChart(history);
  } catch (e) {
    console.warn("히스토리 로드 실패:", e);
  }
}

// ── 메인 로드 ──
async function loadData() {
  try {
    const res = await fetch(DATA_URL);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    renderDashboard(data);
    await loadHistory();
  } catch (e) {
    console.error("데이터 로드 실패:", e);
    document.getElementById("overall-label").textContent = "⚠️ 데이터 로드 실패";
    document.getElementById("overall-label").style.color = "#ef4444";
  }
}

// ── 초기화 ──
document.addEventListener("DOMContentLoaded", () => {
  loadData();
  setInterval(loadData, 30 * 60 * 1000);
});
