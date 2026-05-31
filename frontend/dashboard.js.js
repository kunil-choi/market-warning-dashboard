// ============================================================
// dashboard.js – 글로벌 주식시장 위기경보 대시보드 렌더러
// 수정:
//   Bug2 – toggleFlip: inner- → flip- 래퍼에 .flipped 토글
//   Bug3 – warning-bar 클래스명 styles.css 와 일치
//   Bug4 – 앞면: 현재수치 + 현재상황진단 + 투자시사점
//           뒷면: 수치해설 + 지표의미
//   Bug5 – W4 IPO 카드 중복 제거 및 테이블 통합
// ============================================================

const DATA_URL    = "./data/latest_scores.json";
const HISTORY_URL = "./data/history.jsonl";

const WEIGHTS = { w1: 0.25, w2: 0.30, w3: 0.20, w4: 0.25 };

const STATUS_WEIGHT = {
  "루머": 0.1, "검토중": 0.3,
  "신청완료": 1.0, "가격확정": 1.0, "상장완료": 0.0
};

const statusClassMap = {
  "루머": "Rumor", "검토중": "Considering",
  "신청완료": "Filed", "가격확정": "Priced", "상장완료": "Trading"
};

/* ── 유틸 ─────────────────────────────────────────────────── */
function scoreColor(s) {
  if (s >= 70) return "#ef4444";
  if (s >= 40) return "#f59e0b";
  return "#10b981";
}
function scoreLabel(s) {
  if (s >= 80) return "매우위험";
  if (s >= 70) return "위험";
  if (s >= 55) return "경고";
  if (s >= 40) return "주의";
  if (s >= 25) return "양호";
  return "안전";
}
function scoreGradeClass(s) {
  if (s >= 70) return "grade-red";
  if (s >= 40) return "grade-yellow";
  return "grade-green";
}

/* ── 카드 높이 균등화 ────────────────────────────────────── */
function equalizeCardHeights() {
  const wrappers = document.querySelectorAll(".card-flip-wrapper");
  wrappers.forEach(w => { w.style.height = ""; });
  let maxH = 0;
  wrappers.forEach(w => { maxH = Math.max(maxH, w.offsetHeight); });
  if (maxH > 0) {
    wrappers.forEach(w => { w.style.height = maxH + "px"; });
  }
}
window.addEventListener("resize", () => {
  clearTimeout(window._eqTimer);
  window._eqTimer = setTimeout(equalizeCardHeights, 150);
});

/* ── 플립 ────────────────────────────────────────────────── */
function toggleFlip(prefix) {
  const wrapper = document.getElementById(`flip-${prefix}`);
  if (wrapper) wrapper.classList.toggle("flipped");
}

/* ── 링 차트 ─────────────────────────────────────────────── */
function drawScoreRing(canvasId, score) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const W = canvas.width, H = canvas.height;
  const cx = W / 2, cy = H / 2, r = Math.min(W, H) / 2 - 8;
  ctx.clearRect(0, 0, W, H);
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.strokeStyle = "#1e3a5f";
  ctx.lineWidth = 12;
  ctx.stroke();
  const end = -Math.PI / 2 + (score / 100) * Math.PI * 2;
  ctx.beginPath();
  ctx.arc(cx, cy, r, -Math.PI / 2, end);
  ctx.strokeStyle = scoreColor(score);
  ctx.lineWidth = 12;
  ctx.lineCap = "round";
  ctx.stroke();
}

/* ── 미니바 차트 ─────────────────────────────────────────── */
function drawMiniBar(canvasId, score) {
  requestAnimationFrame(() => {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const parent = canvas.parentElement;
    const pw = parent ? parent.offsetWidth : 200;
    canvas.width  = pw > 0 ? pw : 200;
    canvas.height = 8;
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = "#1e3a5f";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = scoreColor(score);
    ctx.fillRect(0, 0, (score / 100) * canvas.width, canvas.height);
  });
}

/* ── IPO 테이블 렌더 ─────────────────────────────────────── */
function renderIPOTable(ipoList) {
  if (!ipoList || !ipoList.length) return "<p style='font-size:0.74rem;color:#64748b'>데이터 없음</p>";
  let html = `<table class="ipo-table">
    <thead><tr>
      <th>기업</th><th>기업가치</th><th>상태</th><th>가중치</th><th>위험환산</th>
    </tr></thead><tbody>`;
  ipoList.forEach(ipo => {
    // 백엔드 필드명 일치: valuation_bn (not valuation_b), company (not short_name)
    const val   = ipo.valuation_bn ?? ipo.valuation_b ?? 0;
    const st    = ipo.status || "루머";
    const wt    = STATUS_WEIGHT[st] ?? 0.1;
    const wVal  = (val * wt).toFixed(0);
    const cls   = statusClassMap[st] || "Rumor";
    const name  = ipo.company || ipo.short_name || ipo.name || "—";
    const isListed = st === "상장완료";
    html += `<tr style="${isListed ? 'opacity:0.5' : ''}">
      <td style="font-weight:600">${name}${ipo.ticker ? ` <span style="color:#64748b;font-size:0.7rem">(${ipo.ticker})</span>` : ''}</td>
      <td style="font-family:monospace">$${val}B</td>
      <td><span class="status-badge status-${cls}">${st}</span></td>
      <td style="font-family:monospace;text-align:center">${isListed ? '—' : (wt*100).toFixed(0)+'%'}</td>
      <td style="font-family:monospace;color:${isListed?'#64748b':'#f59e0b'}">${isListed ? '제외' : '$'+wVal+'B'}</td>
    </tr>`;
  });
  html += "</tbody></table>";
  return html;
}

/* ── 앞면 콘텐츠 빌더 (현재수치 + 상황진단 + 투자시사점) ── */
function buildFrontContent(prefix, score, raw) {
  const color = scoreColor(score);
  const label = scoreLabel(score);
  const gradeClass = scoreGradeClass(score);

  /* ── W1: 선도주 압축 ── */
  if (prefix === "w1") {
    // spy_ytd / rsp_ytd / rsp_1w_return 는 백엔드에서 이미 % 단위로 반환됨 (*100 불필요)
    const spy  = raw?.spy_ytd   != null ? parseFloat(raw.spy_ytd).toFixed(2)   : "—";
    const rsp  = raw?.rsp_ytd   != null ? parseFloat(raw.rsp_ytd).toFixed(2)   : "—";
    const sp   = raw?.current_spread != null ? raw.current_spread.toFixed(2) : "—";
    const pct  = raw?.spread_percentile ?? "—";
    const rsp1w = raw?.rsp_1w_return != null ? parseFloat(raw.rsp_1w_return).toFixed(2) : "—";
    const rspNeg = raw?.rsp_is_negative_while_spy_positive;

    const spread  = raw?.current_spread ?? 0;
    let sitColor  = "GREEN", sitText = "";
    if (spread >= 6)    { sitColor = "RED";    sitText = "🚨 극단적 쏠림: 소수 메가캡이 시장 전체를 떠받치고 있습니다. 광범위한 하락 위험이 매우 높습니다."; }
    else if (spread >= 4) { sitColor = "ORANGE"; sitText = "⚠️ 위험 수준 쏠림: 중소형주 대비 대형주 격차가 심화되고 있습니다. 조정 시 낙폭이 클 수 있습니다."; }
    else if (spread >= 2) { sitColor = "YELLOW"; sitText = "📢 주의 필요: 선도주 집중 현상이 나타나고 있습니다. 추세 지속 여부를 모니터링해야 합니다."; }
    else                  { sitText = "✅ 시장 균형 양호: 대형·중소형주 간 고른 상승이 유지되고 있습니다."; }

    let advice = "";
    if (score >= 70)  advice = "📌 메가캡 ETF(QQQ 등) 비중 축소 고려. 동일가중 ETF(RSP) 또는 방어주로 이동 권장.";
    else if (score >= 40) advice = "📌 추가 쏠림 심화 시 포트폴리오 분산 강화 필요. SPY↔RSP 스프레드 일별 모니터링.";
    else              advice = "📌 현재 구조는 안정적. 기존 전략 유지하되 스프레드 4% 이상 시 리밸런싱 검토.";

    return `
      <div class="front-metrics-block">
        <div class="front-metric-row"><span class="front-metric-label">SPY YTD</span><span class="front-metric-val ${(parseFloat(spy)||0)>=0?'val-green':'val-red'}">${spy}%</span></div>
        <div class="front-metric-row"><span class="front-metric-label">RSP YTD</span><span class="front-metric-val ${(parseFloat(rsp)||0)>=0?'val-green':'val-red'}">${rsp}%</span></div>
        <div class="front-metric-row"><span class="front-metric-label">SPY-RSP 스프레드</span><span class="front-metric-val ${spread>=4?'val-red':spread>=2?'val-yellow':'val-green'}">${sp}%p</span></div>
        <div class="front-metric-row"><span class="front-metric-label">스프레드 백분위</span><span class="front-metric-val ${(pct>=80)?'val-red':(pct>=60)?'val-yellow':'val-green'}">${pct}%ile</span></div>
        <div class="front-metric-row"><span class="front-metric-label">RSP 1주 수익률</span><span class="front-metric-val ${(parseFloat(rsp1w)||0)>=0?'val-green':'val-red'}">${rsp1w}%</span></div>
        <div class="front-metric-row"><span class="front-metric-label">RSP 역행 신호</span><span class="front-metric-val ${rspNeg?'val-red':'val-green'}">${rspNeg?'🚨 발생':'✅ 없음'}</span></div>
      </div>
      <div class="front-situation ${sitColor}">${sitText}</div>
      <div class="front-advice">💡 ${advice}</div>`;
  }

  /* ── W2: 채권·금리 ── */
  if (prefix === "w2") {
    // 백엔드 필드명 일치: us10y_yield, us2y_yield, is_inverted
    const t10  = raw?.us10y_yield ?? raw?.us_10yr ?? "—";
    const t2   = raw?.us2y_yield  ?? raw?.us_2yr  ?? "—";
    const term = raw?.term_spread != null ? raw.term_spread.toFixed(2) : "—";
    const inv  = raw?.is_inverted ?? raw?.inverted ?? false;
    // tips_10y_real_yield >= 2.0 이면 금리 인상 우려 신호로 간주
    const tipsReal = raw?.tips_10y_real_yield ?? 0;
    const hi   = raw?.rate_hike_concern ?? (tipsReal >= 2.0);

    const termNum = raw?.term_spread ?? 0;
    const t10Num  = parseFloat(t10) || 0;
    let sitColor = "GREEN", sitText = "";
    if (inv || termNum < -0.5) { sitColor = "RED";    sitText = "🚨 심각한 장단기 금리 역전: 과거 사례상 12~18개월 내 경기침체 가능성이 높습니다."; }
    else if (termNum < 0)      { sitColor = "ORANGE"; sitText = "⚠️ 금리 역전 진행 중: 시장이 미래 성장 둔화를 반영하고 있습니다."; }
    else if (score >= 40 || t10Num >= 4.5) { sitColor = "YELLOW"; sitText = "📢 금리 급등 경계: 10년물 고점에서의 변동성 확대 가능성을 주시해야 합니다."; }
    else                       { sitText = "✅ 금리 구조 안정: 장단기 스프레드가 정상 범위를 유지하고 있습니다."; }

    let advice = "";
    if (score >= 70)  advice = "📌 장기채 비중 축소. 듀레이션 단축(단기채·MMF 확대). TIPS 또는 변동금리 채권 편입 검토.";
    else if (score >= 40) advice = "📌 채권 포트폴리오 듀레이션 중립 유지. 금리 추가 상승 시 단기채 비율 증가 준비.";
    else              advice = "📌 현재 금리 환경 우호적. 투자등급 회사채 일부 편입 고려 가능.";

    return `
      <div class="front-metrics-block">
        <div class="front-metric-row"><span class="front-metric-label">미국 10년물</span><span class="front-metric-val ${t10Num>=4.5?'val-red':t10Num>=4?'val-yellow':'val-green'}">${t10}%</span></div>
        <div class="front-metric-row"><span class="front-metric-label">미국 2년물</span><span class="front-metric-val ${(parseFloat(t2)||0)>=5?'val-red':(parseFloat(t2)||0)>=4.5?'val-yellow':'val-green'}">${t2}%</span></div>
        <div class="front-metric-row"><span class="front-metric-label">장단기 스프레드</span><span class="front-metric-val ${termNum<0?'val-red':termNum<0.5?'val-yellow':'val-green'}">${term}%p</span></div>
        <div class="front-metric-row"><span class="front-metric-label">10년 실질금리(TIPS)</span><span class="front-metric-val ${tipsReal>=2.5?'val-red':tipsReal>=2.0?'val-yellow':'val-green'}">${tipsReal.toFixed(2)}%</span></div>
        <div class="front-metric-row"><span class="front-metric-label">장단기 역전</span><span class="front-metric-val ${inv?'val-red':'val-green'}">${inv?'🚨 역전':'✅ 정상'}</span></div>
        <div class="front-metric-row"><span class="front-metric-label">금리 인상 우려</span><span class="front-metric-val ${hi?'val-orange':'val-green'}">${hi?'⚠️ 있음':'✅ 없음'}</span></div>
      </div>
      <div class="front-situation ${sitColor}">${sitText}</div>
      <div class="front-advice">💡 ${advice}</div>`;
  }

  /* ── W3: 사모크레딧·스프레드 ── */
  if (prefix === "w3") {
    const hy     = raw?.hy_bps       ?? "—";
    const ig     = raw?.ig_bps       ?? "—";
    const hyChg  = raw?.hy_change_bps ?? "—";
    const igChg  = raw?.ig_change_bps ?? "—";
    const stress = raw?.stress_level  ?? "—";

    const hyNum  = raw?.hy_bps ?? 0;
    let sitColor = "GREEN", sitText = "";
    if (hyNum >= 600)      { sitColor = "RED";    sitText = "🚨 신용 위기 임박: HY 스프레드가 위기 임계치를 돌파했습니다. 신용 경색 현실화 단계입니다."; }
    else if (hyNum >= 450) { sitColor = "ORANGE"; sitText = "⚠️ 고위험 구간 진입: 하이일드 스프레드 급등으로 기업 자금조달 비용이 급증하고 있습니다."; }
    else if (hyNum >= 350) { sitColor = "YELLOW"; sitText = "📢 경계 수준: 크레딧 스트레스가 누적되고 있습니다. 부도율 상승 선행지표를 추가 모니터링하세요."; }
    else                   { sitText = "✅ 신용 시장 안정: HY/IG 스프레드 모두 역사적 평균 이하 수준을 유지하고 있습니다."; }

    let advice = "";
    if (score >= 70)  advice = "📌 HY 회사채 즉각 축소. 투자등급 이하 채권 및 레버리지론 전면 회피. 현금 비중 확대.";
    else if (score >= 40) advice = "📌 HY 신규 매입 자제. IG 중심으로 방어적 크레딧 포지션 유지.";
    else              advice = "📌 HY 선별적 편입 가능 구간. 단, 스프레드 변화율을 주간 단위로 점검.";

    return `
      <div class="front-metrics-block">
        <div class="front-metric-row"><span class="front-metric-label">HY 스프레드</span><span class="front-metric-val ${hyNum>=450?'val-red':hyNum>=350?'val-yellow':'val-green'}">${hy} bps</span></div>
        <div class="front-metric-row"><span class="front-metric-label">IG 스프레드</span><span class="front-metric-val ${(raw?.ig_bps??0)>=150?'val-red':(raw?.ig_bps??0)>=100?'val-yellow':'val-green'}">${ig} bps</span></div>
        <div class="front-metric-row"><span class="front-metric-label">HY 1개월 변화</span><span class="front-metric-val ${(parseFloat(hyChg)||0)>50?'val-red':(parseFloat(hyChg)||0)>20?'val-yellow':'val-green'}">${hyChg} bps</span></div>
        <div class="front-metric-row"><span class="front-metric-label">IG 1개월 변화</span><span class="front-metric-val ${(parseFloat(igChg)||0)>30?'val-red':(parseFloat(igChg)||0)>15?'val-yellow':'val-green'}">${igChg} bps</span></div>
        <div class="front-metric-row"><span class="front-metric-label">스트레스 레벨</span><span class="front-metric-val">${stress}</span></div>
      </div>
      <div class="front-situation ${sitColor}">${sitText}</div>
      <div class="front-advice">💡 ${advice}</div>`;
  }

  /* ── W4: IPO 유동성 ── */
  if (prefix === "w4") {
    // 백엔드 필드명 일치: total_valuation_bn (가중 합산값)
    const totalVal = raw?.total_valuation_bn ?? raw?.total_weighted_valuation ?? 0;
    // 실제 기업가치 합계 (가중치 미적용, 상장완료 제외)
    const ipoListRaw = raw?.ipo_list ?? [];
    const totalRaw = ipoListRaw
      .filter(ip => ip.status !== "상장완료")
      .reduce((s, ip) => s + (ip.valuation_bn ?? ip.valuation_b ?? 0), 0);
    const filed    = raw?.filed_count   ?? 0;
    const priced   = raw?.priced_count  ?? 0;
    const ipoList  = ipoListRaw;

    let pipelineLabel = "보통", pipelineClass = "val-green";
    if (totalVal >= 2000)      { pipelineLabel = "매우 높음 🚨"; pipelineClass = "val-red"; }
    else if (totalVal >= 1000) { pipelineLabel = "높음 ⚠️";     pipelineClass = "val-yellow"; }
    else if (totalVal >= 500)  { pipelineLabel = "주의 📢";     pipelineClass = "val-yellow"; }

    let sitColor = "GREEN", sitText = "";
    if (totalVal >= 2000)      { sitColor = "RED";    sitText = `🚨 유동성 흡수 위기: 가중 파이프라인 $${totalVal.toFixed(0)}B 규모가 시장 유동성을 대규모로 잠식할 위험이 있습니다.`; }
    else if (totalVal >= 1000) { sitColor = "ORANGE"; sitText = `⚠️ 높은 흡수 압력: $${totalVal.toFixed(0)}B 규모 IPO 대기로 중소형주 자금 이탈 가능성이 있습니다.`; }
    else if (totalVal >= 500)  { sitColor = "YELLOW"; sitText = `📢 파이프라인 누적: $${totalVal.toFixed(0)}B 규모로 시장 수급에 부분적 영향을 줄 수 있습니다.`; }
    else                       { sitText = `✅ IPO 파이프라인 정상 수준: $${totalVal.toFixed(0)}B 규모로 시장 유동성에 큰 영향 없음.`; }

    let advice = "";
    if (score >= 70)  advice = "📌 IPO 참여 최소화. 기존 포트폴리오 현금 비중 확대. 대형 IPO 락업 해제 일정 사전 점검.";
    else if (score >= 40) advice = "📌 신규 IPO 선별적 접근. 상장 첫날 매수보다 안정화 후 진입 전략 권장.";
    else              advice = "📌 IPO 환경 우호적. 우량 기업 공모 참여 고려 가능.";

    return `
      <div class="front-metrics-block">
        <div class="front-metric-row"><span class="front-metric-label">실제 파이프라인 총액</span><span class="front-metric-val val-red">$${totalRaw.toFixed(0)}B</span></div>
        <div class="front-metric-row"><span class="front-metric-label">가중 위험 환산액</span><span class="front-metric-val ${pipelineClass}">$${totalVal.toFixed(0)}B</span></div>
        <div class="front-metric-row"><span class="front-metric-label">위험 수준</span><span class="front-metric-val ${pipelineClass}">${pipelineLabel}</span></div>
        <div class="front-metric-row"><span class="front-metric-label">신청완료 기업 수</span><span class="front-metric-val ${filed>0?'val-yellow':'val-green'}">${filed}개</span></div>
        <div class="front-metric-row"><span class="front-metric-label">가격확정 기업 수</span><span class="front-metric-val ${priced>0?'val-red':'val-green'}">${priced}개</span></div>
      </div>
      <div class="front-situation ${sitColor}">${sitText}</div>
      <div class="front-advice">💡 ${advice}</div>`;
  }

  return "";
}

/* ── 뒷면 콘텐츠 빌더 (수치해설 + 지표의미) ──────────────── */
function buildBackContent(prefix, score, raw) {

  if (prefix === "w1") {
    return `
      <div class="back-content">
        <div class="back-section">
          <h4>📐 수치 해설</h4>
          <div class="back-metric"><span class="back-label">SPY YTD</span><span class="back-value">S&amp;P500 시가총액 가중 ETF 연초 대비 수익률</span></div>
          <div class="back-metric"><span class="back-label">RSP YTD</span><span class="back-value">S&amp;P500 동일가중 ETF 연초 대비 수익률</span></div>
          <div class="back-metric"><span class="back-label">SPY-RSP 스프레드</span><span class="back-value">두 ETF의 수익률 차이 (클수록 쏠림 심화)</span></div>
          <div class="back-metric"><span class="back-label">스프레드 백분위</span><span class="back-value">과거 대비 현재 스프레드의 상대적 위치</span></div>
        </div>
        <div class="back-section">
          <h4>📌 지표 의미</h4>
          <p><strong>SPY vs RSP 스프레드</strong>는 시장 내 종목 쏠림을 측정하는 핵심 지표입니다. SPY는 시가총액 가중으로 애플·마이크로소프트·엔비디아 등 상위 10개 종목 비중이 30% 이상입니다. 반면 RSP는 500개 종목을 동일 비중으로 보유하므로, 두 ETF의 수익률 차이가 클수록 시장 상승이 소수 종목에 의존하는 '쏠림 장세'임을 의미합니다.</p>
          <p style="margin-top:0.5rem">역사적으로 스프레드 6%p 이상 유지 후 시장 조정이 발생한 사례(2000년 닷컴 버블 붕괴, 2022년 메가캡 급락)가 다수 존재합니다.</p>
        </div>
        <div class="back-section">
          <h4>🔢 점수 산출 방식</h4>
          <p>스프레드 크기(50%) + 스프레드 백분위(30%) + RSP 역행 여부(20%)를 가중합산. 0~100점 범위, 70점 이상 위험(RED).</p>
        </div>
      </div>`;
  }

  if (prefix === "w2") {
    return `
      <div class="back-content">
        <div class="back-section">
          <h4>📐 수치 해설</h4>
          <div class="back-metric"><span class="back-label">미국 10년물 국채금리</span><span class="back-value">장기 성장·인플레이션 기대치 반영</span></div>
          <div class="back-metric"><span class="back-label">미국 2년물 국채금리</span><span class="back-value">단기 연준 정책금리 기대치 반영</span></div>
          <div class="back-metric"><span class="back-label">장단기 스프레드(10Y-2Y)</span><span class="back-value">양수=정상, 음수=역전(경기침체 선행신호)</span></div>
        </div>
        <div class="back-section">
          <h4>📌 지표 의미</h4>
          <p><strong>장단기 금리 역전(10Y-2Y &lt; 0)</strong>은 1969년 이후 모든 미국 경기침체에 선행한 지표입니다. 역전 발생 후 평균 12~18개월 내 침체가 시작되었습니다.</p>
          <p style="margin-top:0.5rem">10년물 금리 수준 자체도 중요합니다. 4.5% 이상에서는 주식 밸류에이션 부담이 증가하며, 5% 이상에서는 역사적으로 주식시장 조정이 동반되었습니다.</p>
        </div>
        <div class="back-section">
          <h4>🔢 점수 산출 방식</h4>
          <p>10년물 금리 수준(40%) + 장단기 역전 여부·깊이(40%) + 금리 인상 우려 여부(20%) 가중합산.</p>
        </div>
      </div>`;
  }

  if (prefix === "w3") {
    return `
      <div class="back-content">
        <div class="back-section">
          <h4>📐 수치 해설</h4>
          <div class="back-metric"><span class="back-label">HY 스프레드 (bps)</span><span class="back-value">하이일드 채권과 국채의 금리 차이 (1bp = 0.01%)</span></div>
          <div class="back-metric"><span class="back-label">IG 스프레드 (bps)</span><span class="back-value">투자등급 회사채와 국채의 금리 차이</span></div>
          <div class="back-metric"><span class="back-label">1개월 변화 (bps)</span><span class="back-value">한 달 간 스프레드 변동폭 (급등 = 위험 신호)</span></div>
        </div>
        <div class="back-section">
          <h4>📌 지표 의미</h4>
          <p><strong>HY(하이일드) 스프레드</strong>는 신용 시장의 공포 지수로 불립니다. 기업들이 자금을 조달하는 비용이 얼마나 오르는지를 나타내며, 350bps 이상이면 경계, 600bps 이상이면 과거 금융위기 수준입니다.</p>
          <p style="margin-top:0.5rem"><strong>IG(투자등급) 스프레드</strong>가 HY보다 느리게 오르지만 함께 급등하면 신용 경색이 우량 기업까지 전이된 신호입니다. 두 지표가 동시 급등하면 매우 높은 위험 신호입니다.</p>
        </div>
        <div class="back-section">
          <h4>🔢 점수 산출 방식</h4>
          <p>HY 스프레드 절대치(50%) + HY 1개월 변화율(30%) + IG 스프레드 수준(20%) 가중합산.</p>
        </div>
      </div>`;
  }

  if (prefix === "w4") {
    return `
      <div class="back-content">
        <div class="back-section">
          <h4>📐 수치 해설</h4>
          <div class="back-metric"><span class="back-label">가중 파이프라인 총액</span><span class="back-value">각 IPO 기업가치 × 상태별 가중치 합산</span></div>
          <div class="back-metric"><span class="back-label">상태별 가중치</span><span class="back-value">루머 10% / 검토중 30% / 신청완료·가격확정 100% / 상장완료 0%</span></div>
          <div class="back-metric"><span class="back-label">위험 임계치</span><span class="back-value">$500B 주의 / $1,000B 경고 / $2,000B 위험</span></div>
        </div>
        <div class="back-section">
          <h4>📌 지표 의미</h4>
          <p><strong>대형 IPO 파이프라인</strong>은 시장 유동성을 직접 흡수합니다. 기관투자자들은 대형 IPO 참여를 위해 기존 보유 주식을 매도해 자금을 마련하므로, 파이프라인이 클수록 시장 매도 압력이 높아집니다.</p>
          <p style="margin-top:0.5rem">특히 SpaceX($1,800B), OpenAI($852B), Anthropic($965B) 등 초대형 기업의 상장 진행 여부가 핵심 변수입니다. 이 중 하나라도 신청완료 단계에 진입하면 수백억 달러 규모의 유동성이 즉각 흡수됩니다.</p>
        </div>
        <div class="back-section">
          <h4>🔢 점수 산출 방식</h4>
          <p>가중 파이프라인 총액 규모(60%) + 신청완료·가격확정 기업 수(40%) 기반 0~100점 산출.</p>
        </div>
      </div>`;
  }

  return "";
}

/* ── 앞면 메트릭 그리드 (buildMetrics – 레거시 호환) ────── */
function buildMetrics(prefix, score, raw) {
  // 이제 buildFrontContent 로 통합. 빈 배열 반환.
  return [];
}

/* ── 카드 렌더 ───────────────────────────────────────────── */
function renderCard(prefix, score, raw) {
  // 점수 배지
  const badge = document.getElementById(`score-${prefix}`);
  if (badge) {
    badge.textContent = score.toFixed(1);
    badge.className   = `card-score-badge ${scoreGradeClass(score)}`;
  }
  // 가중치 배지
  const wBadge = document.getElementById(`weight-${prefix}`);
  if (wBadge) wBadge.textContent = `가중치 ${(WEIGHTS[prefix]*100).toFixed(0)}%`;

  // 미니바
  drawMiniBar(`bar-${prefix}`, score);

  // 시그널
  const sigList = document.getElementById(`signals-${prefix}`);
  if (sigList && raw?.signals) {
    sigList.innerHTML = raw.signals.map(sig => {
      let cls = "GREEN";
      if (sig.includes("🚨")) cls = "RED";
      else if (sig.includes("⚠️")) cls = "ORANGE";
      else if (sig.includes("📢") || sig.includes("🔍")) cls = "YELLOW";
      return `<div class="signal-item ${cls}">
        <div class="signal-dot ${cls}"></div>
        <span>${sig}</span>
      </div>`;
    }).join("");
  }

  // 앞면 콘텐츠 삽입 (메트릭 그리드 영역)
  const frontBody = document.getElementById(`front-body-${prefix}`);
  if (frontBody) {
    frontBody.innerHTML = buildFrontContent(prefix, score, raw);
  }

  // 뒷면 콘텐츠 삽입
  const backBody = document.getElementById(`back-body-${prefix}`);
  if (backBody) {
    backBody.innerHTML = buildBackContent(prefix, score, raw);
  }
}

/* ── 복합 점수 렌더 ─────────────────────────────────────── */
function renderComposite(data) {
  const score = data.composite_score ?? 0;
  const grade = data.grade ?? "GREEN";

  // 링
  drawScoreRing("composite-ring", score);
  const numEl = document.getElementById("composite-number");
  if (numEl) { numEl.textContent = score.toFixed(1); numEl.style.color = scoreColor(score); }
  const labelEl = document.getElementById("composite-label");
  if (labelEl) labelEl.textContent = scoreLabel(score);
  const compCard = document.querySelector(".composite-card");
  if (compCard) compCard.className = `composite-card grade-${grade}`;
  const overallEl = document.getElementById("overall-label");
  if (overallEl) {
    overallEl.textContent = `종합 위험도: ${scoreLabel(score)}`;
    overallEl.style.color = scoreColor(score);
  }

  // 액션 추천
  const actionEl = document.getElementById("action-rec");
  if (actionEl) {
    let action = "현재 시장은 안정적입니다. 기존 전략을 유지하세요.";
    if (score >= 80) action = "🚨 즉각적인 리스크 감축이 필요합니다. 주식 비중을 대폭 줄이고 현금 및 안전자산으로 이동하세요.";
    else if (score >= 70) action = "⚠️ 위험 수준 도달. 방어적 포지션 강화 및 헤지 전략 실행을 권장합니다.";
    else if (score >= 55) action = "📢 경고 단계 진입. 포트폴리오 리밸런싱 및 익스포저 점검이 필요합니다.";
    else if (score >= 40) action = "🔍 주의 단계. 위험 지표를 지속 모니터링하며 방어적 준비를 시작하세요.";
    actionEl.textContent = action;
  }

  // 시그널
  const sigBadge = document.getElementById("algo-signal-badge");
  const sigDesc  = document.getElementById("algo-signal-desc");
  if (sigBadge && sigDesc) {
    if (score >= 70) { sigBadge.textContent = "RISK-OFF"; sigBadge.style.background = "#ef4444"; sigDesc.textContent = "전체 위험 지표가 임계치를 초과했습니다."; }
    else if (score >= 40) { sigBadge.textContent = "CAUTION"; sigBadge.style.background = "#f59e0b"; sigDesc.textContent = "복수의 경고 신호가 감지되고 있습니다."; }
    else { sigBadge.textContent = "RISK-ON"; sigBadge.style.background = "#10b981"; sigDesc.textContent = "전반적인 시장 환경이 우호적입니다."; }
  }

  // 헤지 추천
  const hedgeEl = document.getElementById("hedge-rec");
  if (hedgeEl) {
    if (score >= 70) hedgeEl.textContent = "헤지 권장: VIX 콜옵션, 인버스 ETF, 금·달러 비중 확대";
    else if (score >= 40) hedgeEl.textContent = "부분 헤지 권장: 방어주 비중 확대, 포트폴리오 분산 강화";
    else hedgeEl.textContent = "헤지 불필요: 위험 지표 정상 범위 내 유지 중";
  }

  // 경고 바
  const bars = [
    { id: "bar-w1", label: "선도주압축", score: data.w1?.score ?? 0 },
    { id: "bar-w2", label: "채권·금리",  score: data.w2?.score ?? 0 },
    { id: "bar-w3", label: "사모크레딧", score: data.w3?.score ?? 0 },
    { id: "bar-w4", label: "대형IPO",    score: data.w4?.score ?? 0 },
  ];
  const barsContainer = document.getElementById("warning-bars");
  if (barsContainer) {
    barsContainer.innerHTML = bars.map(b => `
      <div class="warning-bar-item">
        <span class="warning-bar-label">${b.label}</span>
        <div class="warning-bar-track">
          <div class="warning-bar-fill" style="width:${b.score}%;background:${scoreColor(b.score)}"></div>
        </div>
        <span class="warning-bar-val" style="color:${scoreColor(b.score)}">${b.score.toFixed(0)}</span>
      </div>`).join("");
  }

  // 스톰 배너
  const stormSection = document.getElementById("storm-section");
  if (stormSection) {
    stormSection.style.display = score >= 80 ? "block" : "none";
  }

  // 마지막 업데이트
  const tsEl = document.getElementById("last-updated");
  if (tsEl && data.timestamp) {
    const d = new Date(data.timestamp);
    tsEl.textContent = `Last updated: ${d.toLocaleString("ko-KR", { timeZone: "Asia/Seoul" })} KST`;
  }
}

/* ── 히스토리 차트 ───────────────────────────────────────── */
// drawHistoryChart 는 charts.js 에서 정의됨 (먼저 로드)
// dashboard.js 에서는 loadHistory() 만 정의

function loadHistory() {
  fetch(HISTORY_URL)
    .then(r => r.text())
    .then(text => {
      // charts.js drawHistoryChart 는 [{date, score}] 형식을 기대
      const entries = text.trim().split("\n")
        .filter(l => l.trim())
        .map(l => {
          try {
            const obj = JSON.parse(l);
            // history.jsonl 은 {date, score} 형식으로 통일됨
            const score = obj.score ?? obj.composite_score;
            const date  = obj.date ?? "";
            if (score != null && date) return { date, score: parseFloat(score) };
            return null;
          } catch { return null; }
        })
        .filter(s => s != null);
      if (entries.length) drawHistoryChart(entries);
      else {
        // 폴백: 더미 데이터
        const fallback = [35,38,32,40,45,42,38,35,30,32,35,38,42,40,38,35,32,35,42,35].map((s, i) => ({
          date: `Day-${20-i}`, score: s
        }));
        drawHistoryChart(fallback);
      }
    })
    .catch(() => {
      const fallback = [35,38,32,40,45,42,38,35,30,32,35,38,42,40,38,35,32,35,42,35].map((s, i) => ({
        date: `Day-${20-i}`, score: s
      }));
      drawHistoryChart(fallback);
    });
}

/* ── 데이터 로드 ─────────────────────────────────────────── */
function loadData() {
  fetch(DATA_URL)
    .then(r => r.json())
    .then(data => {
      renderComposite(data);
      const cards = [
        { prefix: "w1", scoreKey: "w1", rawKey: "w1" },
        { prefix: "w2", scoreKey: "w2", rawKey: "w2" },
        { prefix: "w3", scoreKey: "w3", rawKey: "w3" },
        { prefix: "w4", scoreKey: "w4", rawKey: "w4" },
      ];
      cards.forEach(c => {
        const score = data[c.scoreKey]?.score ?? 0;
        const raw   = data[c.rawKey] ?? {};
        renderCard(c.prefix, score, raw);
      });
      loadHistory();
      setTimeout(equalizeCardHeights, 100);
      setTimeout(equalizeCardHeights, 500);
    })
    .catch(err => {
      console.error("데이터 로드 실패:", err);
      // 폴백 데이터
      const fallback = {
        composite_score: 62, grade: "YELLOW", timestamp: new Date().toISOString(),
        w1: { score: 58, spy_ytd: 0.1124, rsp_ytd: 0.0948, current_spread: 1.76, spread_percentile: 55, rsp_1w_return: 0.015, rsp_is_negative_while_spy_positive: false, signals: ["📢 스프레드 주의 수준"] },
        w2: { score: 65, us_10yr: 4.42, us_2yr: 4.18, term_spread: 0.24, inverted: false, rate_hike_concern: false, signals: ["⚠️ 10년물 4.4% 상회"] },
        w3: { score: 55, hy_bps: 320, ig_bps: 95, hy_change_bps: 15, ig_change_bps: 8, stress_level: "보통", signals: ["📢 HY 스프레드 확대 중"] },
        w4: { score: 72, total_weighted_valuation: 2523, filed_count: 3, priced_count: 0,
          signals: ["🚨 가중 파이프라인 $2,523B"],
          ipo_list: [
            { name:"Space Exploration Technologies Corp", short_name:"SpaceX",   valuation_b:1800, status:"신청완료" },
            { name:"OpenAI",                             short_name:"OpenAI",    valuation_b:852,  status:"검토중" },
            { name:"Anthropic",                          short_name:"Anthropic", valuation_b:965,  status:"검토중" },
            { name:"Databricks",                         short_name:"Databricks",valuation_b:134,  status:"검토중" },
            { name:"Stripe",                             short_name:"Stripe",    valuation_b:159,  status:"검토중" },
            { name:"Cerebras Systems",                   short_name:"Cerebras",  valuation_b:95,   status:"상장완료" },
            { name:"Revolut",                            short_name:"Revolut",   valuation_b:75,   status:"신청완료" },
            { name:"Discord",                            short_name:"Discord",   valuation_b:15,   status:"신청완료" },
          ]
        },
      };
      renderComposite(fallback);
      ["w1","w2","w3","w4"].forEach(p => renderCard(p, fallback[p].score, fallback[p]));
      loadHistory();
      setTimeout(equalizeCardHeights, 100);
      setTimeout(equalizeCardHeights, 500);
    });
}

document.addEventListener("DOMContentLoaded", loadData);
