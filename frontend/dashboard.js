"use strict";

const DATA_URL    = "./data/latest_scores.json";
const HISTORY_URL = "./data/history.jsonl";

// ──────────────────────────────────────────────
// 카드 플립
// ──────────────────────────────────────────────
function toggleFlip(prefix) {
  const wrapper = document.getElementById(`flip-${prefix}`);
  if (wrapper) wrapper.classList.toggle("flipped");
}

// ──────────────────────────────────────────────
// 뒷면 — 일반인 언어 자동 생성
// ──────────────────────────────────────────────
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

  let summary = "";
  let situation = "";
  let numbers = "";
  let advice = "";

  // ── W1: 주도주 압축 ──
  if (prefix === "w1") {
    const spy  = raw.spy_ytd  ?? 0;
    const rsp  = raw.rsp_ytd  ?? 0;
    const qqq  = raw.qqq_ytd  ?? 0;
    const diff = raw.current_spread ?? 0;
    const pct  = raw.spread_percentile ?? 0;
    const rspNeg = raw.rsp_is_negative_while_spy_positive;

    summary = score >= 70
      ? "소수의 대형주만 홀로 오르고 있습니다. 시장이 극도로 좁아졌습니다."
      : score >= 50
      ? "몇몇 대형주 중심으로 상승이 집중되고 있습니다. 주의가 필요합니다."
      : score >= 30
      ? "대형주 쏠림이 조금씩 나타나고 있지만 아직 큰 이상은 없습니다."
      : "시장 전반이 고르게 움직이고 있습니다. 건강한 상태입니다.";

    situation = `지금 주식시장은 마치 반 전체가 공부를 하는데 한두 명만 100점을 받는 상황과 비슷합니다. ` +
      `S&P 500 지수(대형주 위주)는 올해 ${spy > 0 ? "+" : ""}${spy.toFixed(1)}% 올랐지만, ` +
      `같은 종목을 똑같은 비중으로 담은 RSP(균등 지수)는 ${rsp > 0 ? "+" : ""}${rsp.toFixed(1)}%에 그쳤습니다. ` +
      (rspNeg
        ? "특히 RSP가 마이너스로 돌아섰는데, 이는 닷컴 버블 막바지에 나타났던 패턴입니다. 상당히 경계해야 합니다."
        : `나스닥(QQQ)은 ${qqq > 0 ? "+" : ""}${qqq.toFixed(1)}%로 가장 높은 상승을 보이며 기술주로의 쏠림이 뚜렷합니다.`);

    numbers = `대형주와 균등지수 간 괴리: ${diff.toFixed(1)}pt | 역대 상위 ${(100 - pct).toFixed(0)}% 수준의 쏠림`;

    advice = score >= 50
      ? "📌 지금 잘 오르는 대형주만 보지 말고, 나머지 종목들이 어떤지 함께 살펴보세요. 나머지가 빠지기 시작하면 그게 진짜 위험 신호입니다."
      : "📌 현재 특별한 경보는 없지만, 대형주 쏠림이 심화되는지 주간 단위로 확인해 두세요.";
  }

  // ── W2: 채권 자경단 ──
  else if (prefix === "w2") {
    const t10y      = raw.t10y_current      ?? 0;
    const fed       = raw.fed_funds_current ?? 0;
    const real10y   = raw.real10y_current   ?? 0;
    const cpi       = raw.cpi_yoy           ?? 0;
    const debt      = raw.debt_gdp_current  ?? 0;
    const vigilante = raw.vigilante_triggered;
    const checklist = raw.checklist_met_count ?? 0;

    summary = score >= 70
      ? "금리가 통제 범위를 벗어나고 있습니다. 채권 시장이 경고를 보내고 있습니다."
      : score >= 50
      ? "금리 환경이 불안정합니다. 주식 시장 밸류에이션에 부담이 커지고 있습니다."
      : score >= 30
      ? "금리가 조금씩 오르고 있지만 아직 위험 수준은 아닙니다."
      : "금리와 물가가 안정적입니다.";

    situation = `미국 10년 국채 금리는 현재 ${t10y.toFixed(2)}%입니다. ` +
      `쉽게 말하면, 미국 정부에 10년간 돈을 빌려줄 때 받는 이자가 ${t10y.toFixed(2)}%라는 뜻입니다. ` +
      `이 금리가 높을수록 주식의 상대적 매력이 떨어집니다. ` +
      `현재 물가 상승률(CPI)은 ${cpi.toFixed(1)}%이고, ` +
      `미국 국가 부채는 GDP의 ${debt.toFixed(0)}%에 달합니다. ` +
      (vigilante
        ? "채권 자경단 발동 조건이 충족됐습니다. 금리가 빠르게 오르고 있어 주식 시장에 직접적인 압력이 가해지고 있습니다."
        : `채권 자경단 발동 체크리스트 ${checklist}개 항목이 충족된 상태입니다.`);

    numbers = `10년 금리: ${t10y.toFixed(2)}% | 기준금리: ${fed.toFixed(2)}% | 실질금리: ${real10y.toFixed(2)}% | 물가: ${cpi.toFixed(1)}%`;

    advice = score >= 50
      ? "📌 금리가 오를수록 특히 많이 오른 성장주(AI, 기술주)의 조정 폭이 커질 수 있습니다. 부채 비율이 높은 종목은 더 주의하세요."
      : "📌 현재 금리 환경은 안정적입니다. 급격한 금리 변화 뉴스가 나오면 다시 확인해 보세요.";
  }

  // ── W3: 사모 크레딧 ──
  else if (prefix === "w3") {
    const hy      = raw.hy_spread_current  ?? 0;
    const ig      = raw.ig_spread_current  ?? 0;
    const hyChg   = raw.hy_change_1m       ?? 0;
    const volSpike = raw.volume_spike_ratio ?? 1;
    const rollover = raw.rollover_risk_elevated;

    summary = score >= 70
      ? "기업 대출 시장에 위험 신호가 켜졌습니다. 돈 빌리기가 갑자기 어려워지고 있습니다."
      : score >= 50
      ? "기업들의 자금 조달 비용이 높아지고 있습니다. 경계 구간입니다."
      : score >= 30
      ? "아직 큰 문제는 없지만 스프레드가 조금씩 넓어지고 있습니다."
      : "기업 신용 시장이 안정적입니다.";

    situation = `HY 스프레드 ${hy.toFixed(0)}bps는 쉽게 말해 '위험한 기업에 돈 빌려줄 때 얼마나 더 많은 이자를 요구하는가'를 나타냅니다. ` +
      `이 숫자가 클수록 투자자들이 기업 부도를 더 걱정한다는 뜻입니다. ` +
      `지난 한 달 동안 이 수치는 ${hyChg > 0 ? "+" : ""}${hyChg.toFixed(0)}bps 변했습니다. ` +
      (rollover
        ? "현재 복합 지표가 위험 임계값을 초과했습니다. 강남 아파트 30억에 6억 대출이 있는데 은행이 갑자기 연장을 거부하는 상황과 비슷합니다. 자산가들이 급매를 내놓을 수 있습니다."
        : `HYG ETF 거래량은 평소 대비 ${volSpike.toFixed(1)}배 수준으로, ${volSpike > 1.5 ? "평소보다 많은 매도세가 감지됩니다." : "비교적 정상 범위입니다."}`);

    numbers = `HY 스프레드: ${hy.toFixed(0)}bps | IG 스프레드: ${ig.toFixed(0)}bps | 한달 변화: ${hyChg > 0 ? "+" : ""}${hyChg.toFixed(0)}bps`;

    advice = score >= 50
      ? "📌 뉴스에서 '○○ 사모펀드 환매 중단' 기사가 나오기 시작하면 매우 위험한 신호입니다. 하나가 나오면 연쇄적으로 이어질 수 있습니다."
      : "📌 현재 사모 크레딧 시장은 안정적입니다. 특별한 조치는 필요하지 않습니다.";
  }

  // ── W4: 대어급 IPO ──
  else if (prefix === "w4") {
    const total    = raw.total_pipeline_bn    ?? 0;
    const weighted = raw.weighted_pipeline_bn ?? 0;
    const gdpRatio = raw.pipeline_vs_korea_gdp_ratio ?? 0;
    const vix      = raw.vix_current          ?? 20;
    const vixLow   = raw.vix_is_extreme_low;
    const active   = raw.active_ipo_count     ?? 0;
    const ipoRet   = (raw.ipo_etf_90d_returns ?? {}).IPO ?? 0;

    summary = score >= 70
      ? "초대형 기업들의 상장이 임박했습니다. 시장의 돈이 대규모로 빨려들어갈 수 있습니다."
      : score >= 50
      ? "대형 IPO 파이프라인이 상당합니다. 시장 유동성에 영향을 줄 수 있습니다."
      : score >= 30
      ? "IPO 준비 중인 기업들이 있지만 당장 큰 충격은 제한적입니다."
      : "IPO 시장은 현재 조용합니다.";

    situation = `스페이스X, 오픈AI 등 상장을 준비 중인 기업들의 추정 가치 합계가 무려 $${total.toFixed(0)}Bn(약 ${gdpRatio.toFixed(1)}배의 한국 GDP)에 달합니다. ` +
      `상태별 가중치를 적용한 실질 영향 규모는 $${weighted.toFixed(0)}Bn입니다. ` +
      `이 기업들이 상장하면 기관투자자들이 기존에 보유한 주식을 팔아서 청약 자금을 마련하기 때문에 시장 전체의 돈이 IPO 쪽으로 빨려들어 갑니다. ` +
      (active >= 1
        ? `현재 ${active}개 기업이 실제로 S-1(상장 신청서)을 제출한 상태입니다. 상장이 임박했다는 의미입니다. `
        : "") +
      (vixLow
        ? `공포 지수 VIX가 ${vix.toFixed(1)}로 매우 낮습니다. 투자자들이 지금 겁이 없는 상태, 즉 IPO가 가장 잘 팔리는 환경입니다.`
        : `공포 지수 VIX는 ${vix.toFixed(1)}입니다.`);

    numbers = `총 파이프라인: $${total.toFixed(0)}Bn | 가중 파이프라인: $${weighted.toFixed(0)}Bn | VIX: ${vix.toFixed(1)} | IPO ETF 90일: ${ipoRet > 0 ? "+" : ""}${ipoRet.toFixed(1)}%`;

    advice = score >= 50
      ? "📌 대형 IPO 청약 열기가 최고조에 달할 때가 오히려 시장의 꼭대기일 수 있습니다. '이번 IPO는 무조건 사야 해'라는 분위기가 강해질 때 경계하세요."
      : "📌 아직 IPO로 인한 직접적인 유동성 충격은 크지 않습니다.";
  }

  return `
    <div class="back-header">
      <span class="back-title">💬 쉬운 설명</span>
      <span class="back-grade-badge back-grade-${grade}">${gradeLabel}</span>
    </div>

    <div class="back-summary">${summary}</div>

    <div class="back-section">
      <span class="back-section-label">📰 지금 무슨 상황인가요?</span>
      <span class="back-section-text">${situation}</span>
    </div>

    <div class="back-section">
      <span class="back-section-label">📊 주요 수치</span>
      <span class="back-section-text" style="font-family:monospace; font-size:0.78rem;">${numbers}</span>
    </div>

    <div class="back-risk-meter">
      <span class="back-risk-label">위험도</span>
      <div class="back-risk-bar-track">
        <div class="back-risk-bar-fill"
             style="width:${score}%; background:${score>=70?"#ef4444":score>=50?"#f97316":score>=30?"#eab308":"#10b981"}">
        </div>
      </div>
      <span class="back-risk-value" style="color:${score>=70?"#ef4444":score>=50?"#f97316":score>=30?"#eab308":"#10b981"}">
        ${score.toFixed(0)}/100
      </span>
    </div>

    <div class="back-section">
      <span class="back-section-label">🎯 투자자로서 뭘 해야 하나요?</span>
      <span class="back-section-text">${advice}</span>
    </div>

    <div class="flip-hint-back">🔄 탭하면 원래 화면으로</div>
  `;
}

// ──────────────────────────────────────────────
// 경고등 해설 패널 (앞면 하단)
// ──────────────────────────────────────────────
const WARNING_EXPLANATIONS = {
  w1: {
    title: "왜 위험한가?",
    background: "시장 상승이 소수의 대형 종목(SPY)에만 집중되고 나머지 종목(RSP·IWM)이 소외될수록, 얇아진 유동성이 한꺼번에 빠져나갈 때 낙폭이 극대화됩니다. 닷컴 버블(2000년)과 2021년 말 랠리가 대표적 사례입니다.",
    howToRead: "SPY–RSP 괴리 퍼센타일이 90%ile을 초과하면 위험 신호, RSP 1주 수익률이 음전하면 트리거로 간주합니다."
  },
  w2: {
    title: "왜 위험한가?",
    background: "재정 적자가 지속되는 상황에서 인플레이션이 재발하면 채권 투자자들이 국채 매입을 거부(채권 자경단)하고 장기금리가 급등합니다. 금리 상승은 주식 밸류에이션을 직격합니다.",
    howToRead: "10년물 금리가 6개월 전 대비 1.0%p 이상 상승하면 자경단 발동으로 판정합니다."
  },
  w3: {
    title: "왜 위험한가?",
    background: "사모 크레딧(Private Credit) 시장은 유동성이 낮아 환매 요청이 집중되면 자산을 헐값에 매각해야 합니다. HY 스프레드 확대는 신용 위험이 공개 시장 전체로 전이되는 신호입니다.",
    howToRead: "HY 스프레드 400bps 초과 또는 1개월 내 50bps 이상 확대, 역대 80%ile 초과 시 경고로 봅니다."
  },
  w4: {
    title: "왜 위험한가?",
    background: "초대형 IPO가 집중되면 기관 투자자들이 기존 보유 주식을 팔아 청약 자금을 마련합니다. 유동성이 IPO로 빨려들어 가면서 기존 상장 주식, 특히 중소형주가 동반 하락하는 스펀지 효과가 나타납니다.",
    howToRead: "가중 파이프라인 $500Bn 초과 시 주목 구간, $1,000Bn 초과 시 고위험 구간입니다."
  }
};

function scoreBarColor(score) {
  if (score >= 70) return "#ef4444";
  if (score >= 50) return "#f97316";
  if (score >= 35) return "#eab308";
  return "#10b981";
}

function gradeClass(grade) {
  const map = {
    HIGH:         "grade-HIGH",
    CRITICAL:     "grade-CRITICAL",
    PERFECT_STORM:"grade-CRITICAL",
  };
  return map[grade] || "";
}

// ──────────────────────────────────────────────
// 전체 렌더
// ──────────────────────────────────────────────
function renderDashboard(data) {
  const comp   = data.composite;
  const warns  = data.warnings;
  const signal = data.algo_signal;

  drawScoreRing(comp.final_score);

  const compCard = document.getElementById("composite-card");
  compCard.className = `composite-card ${gradeClass(comp.overall_grade)}`;

  const labelEl = document.getElementById("overall-label");
  labelEl.textContent = comp.overall_label;
  labelEl.style.color = comp.overall_color;

  document.getElementById("action-rec").textContent = `📌 ${comp.action_recommended}`;

  const badge = document.getElementById("signal-badge");
  badge.textContent      = signal.signal;
  badge.style.background = signal.signal_color;
  document.getElementById("signal-desc").textContent = signal.signal_desc;
  document.getElementById("hedge-rec").textContent   = signal.hedge_rec;

  const generatedAt = data.meta?.generated_at;
  if (generatedAt) {
    const dt = new Date(generatedAt);
    document.getElementById("last-updated").textContent =
      `데이터 기준: ${dt.toLocaleString("ko-KR")}`;
  }

  document.getElementById("storm-section").style.display =
    comp.overall_grade === "PERFECT_STORM" ? "block" : "none";

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

  // 앞면 렌더
  renderWarningCard("w1", warns.w1_liquidity);
  renderWarningCard("w2", warns.w2_rates);
  renderWarningCard("w3", warns.w3_credit);
  renderWarningCard("w4", warns.w4_ipo);

  // 해설 패널
  renderWarningExplanation("w1", warns.w1_liquidity);
  renderWarningExplanation("w2", warns.w2_rates);
  renderWarningExplanation("w3", warns.w3_credit);
  renderWarningExplanation("w4", warns.w4_ipo);

  // 뒷면 렌더 (raw_data 포함 전달)
  const backMap = {
    w1: warns.w1_liquidity,
    w2: warns.w2_rates,
    w3: warns.w3_credit,
    w4: warns.w4_ipo,
  };
  for (const [prefix, warn] of Object.entries(backMap)) {
    const backEl = document.getElementById(`back-${prefix}`);
    if (backEl) backEl.innerHTML = buildBackContent(prefix, warn);
  }

  // 차트
  const liqRaw = warns.w1_liquidity.raw_data;
  if (liqRaw?.history_90d) drawLiquidityChart("chart-w1", liqRaw.history_90d);

  const ratesRaw = warns.w2_rates.raw_data;
  if (ratesRaw?.history) drawRatesChart("chart-w2", ratesRaw.history);

  const creditRaw = warns.w3_credit.raw_data;
  if (creditRaw?.history) drawCreditChart("chart-w3", creditRaw.history);

  renderIPOTable(warns.w4_ipo.raw_data);
}

// ──────────────────────────────────────────────
// 경고등 앞면 카드 렌더
// ──────────────────────────────────────────────
function renderWarningCard(prefix, warn) {
  const card = document.getElementById(`card-${prefix}`);
  if (!card) return;

  card.className = `card-front warning-card ${gradeClass(warn.grade)}`;

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

// ──────────────────────────────────────────────
// 해설 패널 (앞면 하단)
// ──────────────────────────────────────────────
function renderWarningExplanation(prefix, warn) {
  const el = document.getElementById(`explain-${prefix}`);
  if (!el) return;

  const exp   = WARNING_EXPLANATIONS[prefix];
  const score = warn.score || 0;
  const grade = warn.grade || "LOW";

  let statusText  = "";
  let statusClass = "";
  if (grade === "CRITICAL") {
    statusText  = "🔴 현재 상황: 위험 수위 초과 — 즉각적인 포트폴리오 점검이 필요합니다.";
    statusClass = "explain-status-red";
  } else if (grade === "HIGH") {
    statusText  = "🟠 현재 상황: 경계 구간 진입 — 추가 상승 시 단계적 비중 축소를 고려하세요.";
    statusClass = "explain-status-orange";
  } else if (grade === "MEDIUM") {
    statusText  = "🟡 현재 상황: 주의 구간 — 지표 방향성을 지속 모니터링하세요.";
    statusClass = "explain-status-yellow";
  } else {
    statusText  = "🟢 현재 상황: 안정 구간 — 현재 뚜렷한 위험 신호는 없습니다.";
    statusClass = "explain-status-green";
  }

  const signalSummary = (warn.signals && warn.signals.length > 0)
    ? `<div class="explain-signals">
        ${warn.signals.map(s =>
          `<span class="explain-signal-tag ${s.level}">${s.msg}</span>`
        ).join("")}
       </div>`
    : "";

  el.innerHTML = `
    <div class="explain-panel">
      <div class="explain-why">
        <span class="explain-section-label">⚠️ ${exp.title}</span>
        <p>${exp.background}</p>
      </div>
      <div class="explain-how">
        <span class="explain-section-label">📐 판단 기준</span>
        <p>${exp.howToRead}</p>
      </div>
      <div class="explain-current ${statusClass}">
        <span>${statusText}</span>
        <span class="explain-score-tag">현재 점수: ${score.toFixed(1)} / 100</span>
      </div>
      ${signalSummary}
    </div>`;
}

// ──────────────────────────────────────────────
// IPO 테이블
// ──────────────────────────────────────────────
function renderIPOTable(rawData) {
  const el = document.getElementById("ipo-table");
  if (!el || !rawData?.mega_ipo_pipeline) return;

  el.innerHTML = `
    <table class="ipo-table">
      <thead>
        <tr><th>기업</th><th>섹터</th><th>추정 기업가치</th><th>상태</th></tr>
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

// ──────────────────────────────────────────────
// 히스토리 — 날짜별 1포인트
// ──────────────────────────────────────────────
async function loadHistory() {
  try {
    const res  = await fetch(HISTORY_URL);
    const text = await res.text();

    const raw = text.trim().split("\n")
      .filter(l => l.trim())
      .map(l => { try { return JSON.parse(l); } catch { return null; } })
      .filter(Boolean);

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

// ──────────────────────────────────────────────
// 메인 로드 — 자동 새로고침 없음
// ──────────────────────────────────────────────
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

document.addEventListener("DOMContentLoaded", () => {
  loadData();
});
