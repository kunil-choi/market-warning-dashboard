"use strict";

const DATA_URL    = "./data/latest_scores.json";
const HISTORY_URL = "./data/history.jsonl";

/* ════════════════════════════════════════════
   가중치 정의 (요구사항 5번)
   W2 금리 30% — 가장 강력한 선행지표
   W1·W4 각 25% — 독립적 선행지표
   W3 크레딧 20% — W2와 상관관계 높아 하향
   ════════════════════════════════════════════ */
const WEIGHTS = {
  w1_liquidity: 0.25,
  w2_rates:     0.30,
  w3_credit:    0.20,
  w4_ipo:       0.25,
};

const WEIGHT_LABELS = {
  w1: "가중치 25%",
  w2: "가중치 30%",
  w3: "가중치 20%",
  w4: "가중치 25%",
};

/* ════════════════════════════════════════════
   카드 플립
   ════════════════════════════════════════════ */
function toggleFlip(prefix) {
  const wrapper = document.getElementById(`flip-${prefix}`);
  if (wrapper) wrapper.classList.toggle("flipped");
}

/* ════════════════════════════════════════════
   가중치 기반 종합 점수 계산 (요구사항 5번)
   ════════════════════════════════════════════ */
function calcWeightedScore(warns) {
  return (
    warns.w1_liquidity.score * WEIGHTS.w1_liquidity +
    warns.w2_rates.score     * WEIGHTS.w2_rates     +
    warns.w3_credit.score    * WEIGHTS.w3_credit    +
    warns.w4_ipo.score       * WEIGHTS.w4_ipo
  );
}

/* ════════════════════════════════════════════
   4개 카드 높이 통일 (JS equalizer)
   ════════════════════════════════════════════ */
function equalizeCardHeights() {
  const prefixes = ["w1", "w2", "w3", "w4"];

  prefixes.forEach(p => {
    const inner = document.getElementById(`inner-${p}`);
    if (inner) inner.style.height = "auto";
  });

  requestAnimationFrame(() => {
    let maxH = 0;
    prefixes.forEach(p => {
      const front = document.getElementById(`card-${p}`);
      if (front) maxH = Math.max(maxH, front.offsetHeight);
    });
    if (maxH > 0) {
      prefixes.forEach(p => {
        const inner = document.getElementById(`inner-${p}`);
        if (inner) inner.style.height = `${maxH}px`;
      });
    }
  });
}

/* ════════════════════════════════════════════
   뒷면 — 수치 해설 + 현재 상황 (요구사항 1번)
   ════════════════════════════════════════════ */
function buildBackContent(prefix, warn) {
  const score = warn.score || 0;
  const grade = warn.grade || "LOW";
  const raw   = warn.raw_data || {};

  const gradeLabel = {
    CRITICAL: "🔴 매우 위험",
    HIGH:     "🟠 경계 필요",
    MEDIUM:   "🟡 주의",
    LOW:      "🟢 안정",
    UNKNOWN:  "⚪ 확인 중",
  }[grade] || "⚪ 확인 중";

  const situationColor = { CRITICAL:"RED", HIGH:"ORANGE", MEDIUM:"YELLOW", LOW:"GREEN" }[grade] || "GREEN";

  let metricsExplain = "";
  let situationText  = "";
  let advice         = "";

  /* ── W1: 주도주 압축 ── */
  if (prefix === "w1") {
    const spy  = raw.spy_ytd             ?? 0;
    const rsp  = raw.rsp_ytd             ?? 0;
    const pct  = raw.spread_percentile   ?? 0;
    const rsp1w = raw.rsp_1w_return      ?? null;
    const rspNeg = raw.rsp_is_negative_while_spy_positive;

    metricsExplain = `
      <div class="back-metric-row">
        <div class="back-metric-name">SPY-RSP 괴리 퍼센타일 — ${pct.toFixed(0)}%ile</div>
        <div class="back-metric-desc">
          SPY는 엔비디아·애플 같은 대형주에 비중이 쏠린 지수, RSP는 500개 종목을 <strong>똑같은 비중</strong>으로 담은 지수입니다.
          두 지수의 수익률 차이를 역대 데이터와 비교했을 때 <strong>상위 ${(100-pct).toFixed(0)}% 수준</strong>으로 격차가 크다는 뜻입니다.
          숫자가 높을수록 소수 대형주에만 돈이 몰리고 있다는 신호입니다.
        </div>
      </div>
      <div class="back-metric-row">
        <div class="back-metric-name">RSP 1주 수익률 — ${rsp1w !== null ? (rsp1w > 0 ? "+" : "") + rsp1w.toFixed(2) + "%" : "데이터 없음"}</div>
        <div class="back-metric-desc">
          균등 지수(RSP)가 최근 1주일 동안 얼마나 움직였는지입니다.
          <strong>핵심은 부호</strong>입니다. 플러스(+)면 소외주도 함께 오르는 중,
          마이너스(-)로 돌아서면 대형주만 오르고 나머지는 빠지는 진짜 위험 신호입니다.
        </div>
      </div>
      <div class="back-metric-row">
        <div class="back-metric-name">SPY YTD ${spy > 0 ? "+" : ""}${spy.toFixed(2)}% vs RSP YTD ${rsp > 0 ? "+" : ""}${rsp.toFixed(2)}%</div>
        <div class="back-metric-desc">
          올해 1월 1일부터 지금까지의 누적 수익률입니다.
          SPY가 RSP보다 <strong>${(spy - rsp).toFixed(1)}%p 더 높습니다.</strong>
          이 차이가 클수록 시장 상승이 소수 종목에 집중됐다는 의미입니다.
        </div>
      </div>`;

    situationText = rspNeg
      ? `⚠️ RSP가 마이너스로 돌아선 상태입니다. 대형주만 홀로 오르고 나머지 종목은 떨어지고 있습니다. 닷컴 버블 막바지(2000년 1~3월)에 나타났던 패턴과 동일합니다. 포트폴리오 점검이 필요합니다.`
      : score >= 50
      ? `SPY는 +${spy.toFixed(1)}%, RSP는 +${rsp.toFixed(1)}%로 ${(spy-rsp).toFixed(1)}%p 격차가 역대 상위 ${(100-pct).toFixed(0)}% 수준입니다. 상승이 일부 대형주에 집중되고 있습니다. RSP가 마이너스로 전환되는지 주시하세요.`
      : `SPY +${spy.toFixed(1)}%, RSP +${rsp.toFixed(1)}%로 시장이 비교적 고르게 상승 중입니다. 현재 특별한 경보는 없습니다.`;

    advice = score >= 50
      ? "📌 잘 오르는 대형주에만 집중하지 말고 RSP, IWM(소형주 ETF) 방향을 함께 확인하세요. RSP가 마이너스로 전환되는 순간이 진짜 위험 신호입니다."
      : "📌 시장이 비교적 건강하게 움직이고 있습니다. 대형주 쏠림 심화 여부를 주간 단위로 모니터링하세요.";
  }

  /* ── W2: 채권 자경단 ── */
  else if (prefix === "w2") {
    const t10y      = raw.t10y_current      ?? 0;
    const fed       = raw.fed_funds_current ?? 0;
    const real10y   = raw.real10y_current   ?? 0;
    const cpi       = raw.cpi_yoy           ?? 0;
    const debt      = raw.debt_gdp_current  ?? 0;
    const t10y6mChg = raw.t10y_6m_change    ?? 0;
    const vigilante = raw.vigilante_triggered;

    metricsExplain = `
      <div class="back-metric-row">
        <div class="back-metric-name">10년 국채 금리 — ${t10y.toFixed(2)}%</div>
        <div class="back-metric-desc">
          미국 정부에 10년간 돈을 빌려줄 때 받는 이자율입니다.
          이 금리가 높을수록 주식·부동산 등 위험자산의 상대적 매력이 떨어집니다.
          6개월 전 대비 <strong>${t10y6mChg > 0 ? "+" : ""}${t10y6mChg.toFixed(2)}%p 변동</strong>했습니다.
        </div>
      </div>
      <div class="back-metric-row">
        <div class="back-metric-name">실질 금리 — ${real10y.toFixed(2)}%</div>
        <div class="back-metric-desc">
          10년 금리에서 물가 상승률을 뺀 값입니다. 플러스(+)면 돈을 빌려줬을 때 물가를 이기는 실제 수익이 생긴다는 뜻으로,
          주식 등 위험자산 매력이 더 떨어집니다.
        </div>
      </div>
      <div class="back-metric-row">
        <div class="back-metric-name">물가(CPI) — ${cpi.toFixed(1)}% | 국가부채/GDP — ${debt.toFixed(0)}%</div>
        <div class="back-metric-desc">
          물가가 높을수록 연준이 금리를 낮추기 어렵고, 국가 부채가 GDP 대비 ${debt.toFixed(0)}%라는 것은
          미국이 세금으로 버는 것보다 훨씬 많은 빚을 지고 있다는 뜻입니다.
          채권 투자자들이 이를 보고 국채 매입을 거부하면(채권 자경단) 금리가 강제로 올라갑니다.
        </div>
      </div>`;

    situationText = vigilante
      ? `🚨 채권 자경단 발동 조건이 충족됐습니다. 10년 금리가 6개월 새 ${t10y6mChg.toFixed(2)}%p 급등했습니다. 주식 밸류에이션에 직접적인 압력이 가해지고 있습니다.`
      : score >= 50
      ? `10년 금리 ${t10y.toFixed(2)}%, 실질금리 ${real10y.toFixed(2)}%로 금리 환경이 불안정합니다. 채권 자경단 발동 조건이 일부 충족되고 있습니다.`
      : `10년 금리 ${t10y.toFixed(2)}%, 물가 ${cpi.toFixed(1)}%로 현재 금리 환경은 비교적 안정적입니다.`;

    advice = score >= 50
      ? "📌 금리가 오를수록 많이 오른 성장주(AI·기술주)의 조정 폭이 커질 수 있습니다. 고PER 종목 비중을 점검하세요."
      : "📌 현재 금리 환경은 안정적입니다. 연준 발언과 CPI 발표 시점을 확인해 두세요.";
  }

  /* ── W3: 사모 크레딧 ── */
  else if (prefix === "w3") {
    const hy       = raw.hy_spread_current  ?? 0;
    const ig       = raw.ig_spread_current  ?? 0;
    const hyChg    = raw.hy_change_1m       ?? 0;
    const hyPct    = raw.hy_percentile      ?? 0;
    const volSpike = raw.volume_spike_ratio ?? 1;
    const rollover = raw.rollover_risk_elevated;

    metricsExplain = `
      <div class="back-metric-row">
        <div class="back-metric-name">HY 스프레드 — ${hy.toFixed(0)}bps (역대 ${hyPct.toFixed(0)}%ile)</div>
        <div class="back-metric-desc">
          위험한 기업에 돈을 빌려줄 때 안전한 국채보다 <strong>얼마나 더 많은 이자를 요구하는가</strong>입니다.
          숫자가 클수록 시장이 기업 부도를 더 걱정한다는 뜻입니다.
          지난 한 달 동안 <strong>${hyChg > 0 ? "+" : ""}${hyChg.toFixed(0)}bps 변동</strong>했습니다.
        </div>
      </div>
      <div class="back-metric-row">
        <div class="back-metric-name">IG 스프레드 — ${ig.toFixed(0)}bps</div>
        <div class="back-metric-desc">
          비교적 안전한 우량 기업(Investment Grade)의 가산 금리입니다.
          HY와 IG가 동시에 오르면 단순한 개별 기업 문제가 아니라
          <strong>신용 시장 전체가 경색</strong>되고 있다는 신호입니다.
        </div>
      </div>
      <div class="back-metric-row">
        <div class="back-metric-name">HYG 거래량 — 평소 대비 ${volSpike.toFixed(1)}배</div>
        <div class="back-metric-desc">
          HYG는 고위험 채권 ETF입니다. 거래량이 평소보다 급격히 늘어난다는 것은
          누군가 대규모로 팔고 있다는 뜻으로, <strong>사모펀드 환매 요청의 전조</strong>일 수 있습니다.
        </div>
      </div>`;

    situationText = rollover
      ? `🚨 복합 지표가 위험 임계값을 초과했습니다. 강남 아파트 30억에 6억 대출이 있는데 은행이 갑자기 연장을 거부하는 상황과 비슷합니다. 자산가들이 급매를 내놓는 연쇄 반응이 시작될 수 있습니다.`
      : score >= 50
      ? `HY 스프레드 ${hy.toFixed(0)}bps로 역대 상위 ${(100-hyPct).toFixed(0)}% 수준입니다. 기업 신용 시장에 경계 신호가 나타나고 있습니다.`
      : `HY 스프레드 ${hy.toFixed(0)}bps, IG 스프레드 ${ig.toFixed(0)}bps로 기업 신용 시장이 안정적입니다.`;

    advice = score >= 50
      ? "📌 뉴스에서 '○○ 사모펀드 환매 중단' 기사가 하나라도 나오면 매우 위험한 신호입니다. 연쇄 가능성이 높습니다."
      : "📌 현재 사모 크레딧 시장은 안정적입니다. HY 스프레드 월간 변화를 주시하세요.";
  }

  /* ── W4: 대어급 IPO ── */
  else if (prefix === "w4") {
    const total    = raw.total_pipeline_bn            ?? 0;
    const weighted = raw.weighted_pipeline_bn         ?? 0;
    const gdpRatio = raw.pipeline_vs_korea_gdp_ratio  ?? 0;
    const vix      = raw.vix_current                  ?? 20;
    const vixLow   = raw.vix_is_extreme_low;
    const active   = raw.active_ipo_count             ?? 0;
    const ipoRet   = (raw.ipo_etf_90d_returns ?? {}).IPO ?? 0;

    metricsExplain = `
      <div class="back-metric-row">
        <div class="back-metric-name">총 IPO 파이프라인 — $${total.toFixed(0)}Bn (한국 GDP의 ${gdpRatio.toFixed(1)}배)</div>
        <div class="back-metric-desc">
          현재 상장을 준비 중인 기업들의 추정 가치 합계입니다.
          이 기업들이 상장하면 기관투자자들이 기존 보유 주식을 팔아 청약 자금을 마련하기 때문에
          <strong>시장 전체의 돈이 IPO로 빨려들어 가는 스펀지 효과</strong>가 발생합니다.
        </div>
      </div>
      <div class="back-metric-row">
        <div class="back-metric-name">가중 파이프라인 — $${weighted.toFixed(0)}Bn</div>
        <div class="back-metric-desc">
          S-1 제출 완료(가중치 1.0), 검토중(0.3), 루머(0.1) 등 상장 진행 단계를 반영한 실질 영향 규모입니다.
          ${active >= 1 ? `현재 <strong>${active}개 기업이 S-1(상장신청서)을 실제로 제출</strong>한 상태로, 상장이 임박했습니다.` : "아직 실제 S-1 제출 기업은 없습니다."}
        </div>
      </div>
      <div class="back-metric-row">
        <div class="back-metric-name">VIX — ${vix.toFixed(1)} | IPO ETF 90일 — ${ipoRet > 0 ? "+" : ""}${ipoRet.toFixed(1)}%</div>
        <div class="back-metric-desc">
          VIX는 시장 공포 지수입니다. ${vixLow
            ? `<strong>${vix.toFixed(1)}로 매우 낮습니다.</strong> 투자자들이 겁이 없는 상태, 즉 IPO가 가장 잘 팔리는 환경입니다. 파티의 마지막 신호일 수 있습니다.`
            : `${vix.toFixed(1)}로 보통 수준입니다.`}
          IPO ETF 90일 수익률 ${ipoRet > 0 ? "+" : ""}${ipoRet.toFixed(1)}%는 최근 신규 상장 종목들의 성과를 나타냅니다.
        </div>
      </div>`;

    situationText = active >= 1 && vixLow
      ? `🚨 S-1 제출 완료 기업 ${active}개 + VIX 극단 저점이 동시에 발생했습니다. 초대형 IPO가 임박한 상황에서 시장이 가장 무방비 상태입니다. 역사적으로 이 조합이 나타난 직후 시장이 꺾였습니다.`
      : score >= 50
      ? `가중 파이프라인 $${weighted.toFixed(0)}Bn으로 시장 유동성에 상당한 영향을 줄 수 있는 규모입니다. IPO 청약 일정을 주시하세요.`
      : `IPO 파이프라인은 존재하지만 현재 직접적인 유동성 충격은 제한적입니다.`;

    advice = score >= 50
      ? "📌 '이번 IPO는 무조건 사야 해'라는 분위기가 정점에 달할 때가 오히려 시장의 꼭대기입니다. 청약 열기와 시장 전체 유동성을 함께 보세요."
      : "📌 아직 IPO로 인한 직접적 충격은 크지 않습니다.";
  }

  return `
    <div class="back-header">
      <span class="back-title">💬 수치 해설</span>
      <span class="back-grade-badge back-grade-${grade}">${gradeLabel}</span>
    </div>

    <div class="back-metrics-explain">
      ${metricsExplain}
    </div>

    <div class="back-situation ${situationColor}">
      ${situationText}
    </div>

    <div class="back-risk-meter">
      <span class="back-risk-label">위험도</span>
      <div class="back-risk-bar-track">
        <div class="back-risk-bar-fill"
             style="width:${score}%;background:${score>=70?"#ef4444":score>=50?"#f97316":score>=30?"#eab308":"#10b981"}">
        </div>
      </div>
      <span class="back-risk-value"
            style="color:${score>=70?"#ef4444":score>=50?"#f97316":score>=30?"#eab308":"#10b981"}">
        ${score.toFixed(0)}/100
      </span>
    </div>

    <div class="back-advice">${advice}</div>

    <div class="flip-hint-back">🔄 탭하면 원래 화면으로</div>
  `;
}

/* ════════════════════════════════════════════
   유틸
   ════════════════════════════════════════════ */
function scoreBarColor(score) {
  if (score >= 70) return "#ef4444";
  if (score >= 50) return "#f97316";
  if (score >= 35) return "#eab308";
  return "#10b981";
}

function gradeClass(grade) {
  return { HIGH:"grade-HIGH", CRITICAL:"grade-CRITICAL", PERFECT_STORM:"grade-CRITICAL" }[grade] || "";
}

/* ════════════════════════════════════════════
   전체 렌더
   ════════════════════════════════════════════ */
function renderDashboard(data) {
  const comp   = data.composite;
  const warns  = data.warnings;
  const signal = data.algo_signal;

  /* 가중치 기반 종합 점수 재계산 (요구사항 5번) */
  const weightedScore = calcWeightedScore(warns);

  drawScoreRing(weightedScore);
  document.getElementById("composite-card").className = `composite-card ${gradeClass(comp.overall_grade)}`;

  const labelEl = document.getElementById("overall-label");
  labelEl.textContent = comp.overall_label;
  labelEl.style.color = comp.overall_color;

  document.getElementById("action-rec").textContent  = `📌 ${comp.action_recommended}`;

  const badge = document.getElementById("signal-badge");
  badge.textContent      = signal.signal;
  badge.style.background = signal.signal_color;
  document.getElementById("signal-desc").textContent = signal.signal_desc;
  document.getElementById("hedge-rec").textContent   = signal.hedge_rec;

  /* 데이터 기준 시각 */
  const generatedAt = data.meta?.generated_at;
  if (generatedAt) {
    const dt = new Date(generatedAt);
    document.getElementById("last-updated").textContent =
      `데이터 기준: ${dt.toLocaleString("ko-KR")}`;
  }

  document.getElementById("storm-section").style.display =
    comp.overall_grade === "PERFECT_STORM" ? "block" : "none";

  /* 종합 경고 바 — 가중치 포함 레이블 */
  const warningList = [
    { id: "w1_liquidity", label: `W1 주도주 압축 (${(WEIGHTS.w1_liquidity*100).toFixed(0)}%)` },
    { id: "w2_rates",     label: `W2 채권 자경단 (${(WEIGHTS.w2_rates*100).toFixed(0)}%)` },
    { id: "w3_credit",    label: `W3 사모 크레딧 (${(WEIGHTS.w3_credit*100).toFixed(0)}%)` },
    { id: "w4_ipo",       label: `W4 대어급 IPO (${(WEIGHTS.w4_ipo*100).toFixed(0)}%)` },
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

  /* 가중치 배지 표시 */
  ["w1","w2","w3","w4"].forEach(p => {
    const el = document.getElementById(`weight-${p}`);
    if (el) el.textContent = WEIGHT_LABELS[p];
  });

  /* 앞면 렌더 */
  renderWarningCard("w1", warns.w1_liquidity);
  renderWarningCard("w2", warns.w2_rates);
  renderWarningCard("w3", warns.w3_credit);
  renderWarningCard("w4", warns.w4_ipo);

  /* 뒷면 렌더 */
  [["w1", warns.w1_liquidity], ["w2", warns.w2_rates],
   ["w3", warns.w3_credit],    ["w4", warns.w4_ipo]].forEach(([p, w]) => {
    const el = document.getElementById(`back-${p}`);
    if (el) el.innerHTML = buildBackContent(p, w);
  });

  /* 개별 차트 */
  const liqRaw = warns.w1_liquidity.raw_data;
  if (liqRaw?.history_90d) drawLiquidityChart("chart-w1", liqRaw.history_90d);

  const ratesRaw = warns.w2_rates.raw_data;
  if (ratesRaw?.history) drawRatesChart("chart-w2", ratesRaw.history);

  const creditRaw = warns.w3_credit.raw_data;
  if (creditRaw?.history) drawCreditChart("chart-w3", creditRaw.history);

  renderIPOTable(warns.w4_ipo.raw_data);

  /* 카드 높이 통일 */
  setTimeout(equalizeCardHeights, 50);
  window.removeEventListener("resize", equalizeCardHeights);
  window.addEventListener("resize", equalizeCardHeights);
}

/* ════════════════════════════════════════════
   경고등 앞면 카드 렌더
   ════════════════════════════════════════════ */
function renderWarningCard(prefix, warn) {
  const card = document.getElementById(`card-${prefix}`);
  if (!card) return;

  card.className = `card-front ${gradeClass(warn.grade)}`;

  const scoreBadge = document.getElementById(`score-${prefix}`);
  if (scoreBadge) {
    scoreBadge.textContent = warn.score.toFixed(1);
    scoreBadge.style.color = warn.grade_color;
  }

  const metricsEl = document.getElementById(`metrics-${prefix}`);
  if (metricsEl && warn.key_metrics) {
    metricsEl.innerHTML = Object.entries(warn.key_metrics).map(([k, v]) => `
      <div class="metric-item">
        <div class="metric-label">${k}</div>
        <div class="metric-value">${v}</div>
      </div>`).join("");
  }

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

/* ════════════════════════════════════════════
   IPO 테이블
   ════════════════════════════════════════════ */
function renderIPOTable(rawData) {
  const el = document.getElementById("ipo-table");
  if (!el || !rawData?.mega_ipo_pipeline) return;

  const statusClassMap = {
    "신청완료":"Filed", "검토중":"Considering",
    "공모가확정":"Priced", "거래중":"Trading", "루머":"Rumor",
  };

  el.innerHTML = `
    <table class="ipo-table">
      <thead>
        <tr><th>기업</th><th>섹터</th><th>추정 기업가치</th><th>상태</th></tr>
      </thead>
      <tbody>
        ${rawData.mega_ipo_pipeline.map(p => {
          const cssKey = statusClassMap[p.status] || p.status;
          return `
            <tr>
              <td><strong>${p.company}</strong></td>
              <td>${p.sector}</td>
              <td>$${p.est_valuation_bn}B</td>
              <td><span class="status-badge status-${cssKey}">${p.status}</span></td>
            </tr>`;
        }).join("")}
        <tr style="background:rgba(239,68,68,0.08)">
          <td colspan="2"><strong>총 파이프라인</strong></td>
          <td><strong style="color:#ef4444">$${rawData.total_pipeline_bn}B</strong></td>
          <td><small style="color:#64748b">한국 GDP의 ${rawData.pipeline_vs_korea_gdp_ratio}배</small></td>
        </tr>
      </tbody>
    </table>`;
}

/* ════════════════════════════════════════════
   히스토리 — 종합 점수 단일 라인 (요구사항 3번)
   ════════════════════════════════════════════ */
async function loadHistory() {
  try {
    const res  = await fetch(HISTORY_URL);
    const text = await res.text();

    const raw = text.trim().split("\n")
      .filter(l => l.trim())
      .map(l => { try { return JSON.parse(l); } catch { return null; } })
      .filter(Boolean);

    /* 날짜별 중복 제거 — 하루 1포인트 */
    const byDate = new Map();
    for (const entry of raw) {
      if (entry.date) byDate.set(entry.date, entry);
    }

    const history = Array.from(byDate.values())
      .sort((a, b) => a.date.localeCompare(b.date))
      .slice(-90);

    drawHistoryChart(history);
  } catch (e) {
    console.warn("히스토리 로드 실패:", e);
  }
}

/* ════════════════════════════════════════════
   메인 로드
   ════════════════════════════════════════════ */
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

document.addEventListener("DOMContentLoaded", () => { loadData(); });
