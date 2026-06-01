// ============================================================
// dashboard.js – 글로벌 주식시장 위기경보 대시보드 렌더러
// 수정:
//   Bug2 – toggleFlip: flip- 래퍼에 .flipped 토글
//   Bug3 – warning-bar 클래스명 styles.css 와 일치
//   Bug4 – 앞면: 현재수치 + 현재상황진단 + 투자시사점
//           뒷면: 수치해설 + 위험기준 + 점수산출
//   Bug5 – W4 IPO 카드 중복 제거 및 테이블 통합
//   Fix6 – W4 뒷면 시총 대비 비율 기준 임계치로 교체
//   Fix7 – 폴백 데이터 valuation_b → valuation_bn 키 통일
//   Fix8 – W4 앞면 pipeline_ratio_pct 표시 추가
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
    const val      = ipo.valuation_bn ?? ipo.valuation_b ?? 0;
    const st       = ipo.status || "루머";
    const wt       = STATUS_WEIGHT[st] ?? 0.1;
    const wVal     = (val * wt).toFixed(0);
    const cls      = statusClassMap[st] || "Rumor";
    const name     = ipo.company || ipo.short_name || ipo.name || "—";
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

/* ── 앞면 콘텐츠 빌더 ────────────────────────────────────── */
function buildFrontContent(prefix, score, raw) {
  const color      = scoreColor(score);
  const label      = scoreLabel(score);
  const gradeClass = scoreGradeClass(score);

  /* ── W1: 선도주 압축 ── */
  if (prefix === "w1") {
    const spy    = raw?.spy_ytd        != null ? parseFloat(raw.spy_ytd).toFixed(2)        : "—";
    const rsp    = raw?.rsp_ytd        != null ? parseFloat(raw.rsp_ytd).toFixed(2)        : "—";
    const sp     = raw?.current_spread != null ? raw.current_spread.toFixed(2)             : "—";
    const pct    = raw?.spread_percentile ?? "—";
    const rsp1w  = raw?.rsp_1w_return  != null ? parseFloat(raw.rsp_1w_return).toFixed(2) : "—";
    const rspNeg = raw?.rsp_is_negative_while_spy_positive;
    const spread = raw?.current_spread ?? 0;

    let sitColor = "GREEN", sitText = "";
    if      (spread >= 6) { sitColor = "RED";    sitText = "🚨 극단적 쏠림: 소수 메가캡이 시장 전체를 떠받치고 있습니다. 광범위한 하락 위험이 매우 높습니다."; }
    else if (spread >= 4) { sitColor = "ORANGE"; sitText = "⚠️ 위험 수준 쏠림: 중소형주 대비 대형주 격차가 심화되고 있습니다. 조정 시 낙폭이 클 수 있습니다."; }
    else if (spread >= 2) { sitColor = "YELLOW"; sitText = "📢 주의 필요: 선도주 집중 현상이 나타나고 있습니다. 추세 지속 여부를 모니터링해야 합니다."; }
    else                  { sitText  = "✅ 시장 균형 양호: 대형·중소형주 간 고른 상승이 유지되고 있습니다."; }

    let advice = "";
    if      (score >= 70) advice = "📌 메가캡 ETF(QQQ 등) 비중 축소 고려. 동일가중 ETF(RSP) 또는 방어주로 이동 권장.";
    else if (score >= 40) advice = "📌 추가 쏠림 심화 시 포트폴리오 분산 강화 필요. SPY↔RSP 스프레드 일별 모니터링.";
    else                  advice = "📌 현재 구조는 안정적. 기존 전략 유지하되 스프레드 4% 이상 시 리밸런싱 검토.";

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
    const t10      = raw?.us10y_yield ?? raw?.us_10yr ?? "—";
    const t2       = raw?.us2y_yield  ?? raw?.us_2yr  ?? "—";
    const term     = raw?.term_spread != null ? raw.term_spread.toFixed(2) : "—";
    const inv      = raw?.is_inverted ?? raw?.inverted ?? false;
    const tipsReal = raw?.tips_10y_real_yield ?? 0;
    const hi       = raw?.rate_hike_concern ?? (tipsReal >= 2.0);
    const termNum  = raw?.term_spread ?? 0;
    const t10Num   = parseFloat(t10) || 0;

    let sitColor = "GREEN", sitText = "";
    if      (inv || termNum < -0.5)        { sitColor = "RED";    sitText = "🚨 심각한 장단기 금리 역전: 과거 사례상 12~18개월 내 경기침체 가능성이 높습니다."; }
    else if (termNum < 0)                  { sitColor = "ORANGE"; sitText = "⚠️ 금리 역전 진행 중: 시장이 미래 성장 둔화를 반영하고 있습니다."; }
    else if (score >= 40 || t10Num >= 4.5) { sitColor = "YELLOW"; sitText = "📢 금리 급등 경계: 10년물 고점에서의 변동성 확대 가능성을 주시해야 합니다."; }
    else                                   { sitText  = "✅ 금리 구조 안정: 장단기 스프레드가 정상 범위를 유지하고 있습니다."; }

    let advice = "";
    if      (score >= 70) advice = "📌 장기채 비중 축소. 듀레이션 단축(단기채·MMF 확대). TIPS 또는 변동금리 채권 편입 검토.";
    else if (score >= 40) advice = "📌 채권 포트폴리오 듀레이션 중립 유지. 금리 추가 상승 시 단기채 비율 증가 준비.";
    else                  advice = "📌 현재 금리 환경 우호적. 투자등급 회사채 일부 편입 고려 가능.";

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
    const hy    = raw?.hy_bps        ?? "—";
    const ig    = raw?.ig_bps        ?? "—";
    const hyChg = raw?.hy_change_bps ?? "—";
    const igChg = raw?.ig_change_bps ?? "—";
    const stress= raw?.stress_level  ?? "—";
    const hyNum = raw?.hy_bps        ?? 0;

    let sitColor = "GREEN", sitText = "";
    if      (hyNum >= 600) { sitColor = "RED";    sitText = "🚨 신용 위기 임박: HY 스프레드가 위기 임계치를 돌파했습니다. 신용 경색 현실화 단계입니다."; }
    else if (hyNum >= 450) { sitColor = "ORANGE"; sitText = "⚠️ 고위험 구간 진입: 하이일드 스프레드 급등으로 기업 자금조달 비용이 급증하고 있습니다."; }
    else if (hyNum >= 350) { sitColor = "YELLOW"; sitText = "📢 경계 수준: 크레딧 스트레스가 누적되고 있습니다. 부도율 상승 선행지표를 추가 모니터링하세요."; }
    else                   { sitText  = "✅ 신용 시장 안정: HY/IG 스프레드 모두 역사적 평균 이하 수준을 유지하고 있습니다."; }

    let advice = "";
    if      (score >= 70) advice = "📌 HY 회사채 즉각 축소. 투자등급 이하 채권 및 레버리지론 전면 회피. 현금 비중 확대.";
    else if (score >= 40) advice = "📌 HY 신규 매입 자제. IG 중심으로 방어적 크레딧 포지션 유지.";
    else                  advice = "📌 HY 선별적 편입 가능 구간. 단, 스프레드 변화율을 주간 단위로 점검.";

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
    const totalVal   = raw?.total_valuation_bn ?? 0;
    const ratioRaw   = raw?.pipeline_ratio_pct ?? (totalVal / 69000 * 100);
    const ratio      = ratioRaw.toFixed(2);
    const ipoListRaw = raw?.ipo_list ?? [];
    const totalRaw   = ipoListRaw
      .filter(ip => ip.status !== "상장완료")
      .reduce((s, ip) => s + (ip.valuation_bn ?? ip.valuation_b ?? 0), 0);
    const filed  = raw?.filed_count  ?? 0;
    const priced = raw?.priced_count ?? 0;

    let pipelineLabel = "정상", pipelineClass = "val-green";
    if      (ratioRaw >= 0.45) { pipelineLabel = "위험 🚨";   pipelineClass = "val-red"; }
    else if (ratioRaw >= 0.25) { pipelineLabel = "경고 ⚠️";   pipelineClass = "val-orange"; }
    else if (ratioRaw >= 0.15) { pipelineLabel = "주의 📢";   pipelineClass = "val-yellow"; }

    let sitColor = "GREEN", sitText = "";
    if      (ratioRaw >= 0.45) { sitColor = "RED";    sitText = `🚨 전례 없는 압력: 시총 대비 ${ratio}% — 닷컴버블(0.45%) 초과. 유동성 흡수 위험 최고조입니다.`; }
    else if (ratioRaw >= 0.25) { sitColor = "ORANGE"; sitText = `⚠️ 닷컴버블 수준: 시총 대비 ${ratio}% — 1999~2000년 수준의 IPO 압력이 시장에 가해지고 있습니다.`; }
    else if (ratioRaw >= 0.15) { sitColor = "YELLOW"; sitText = `📢 SPAC 붐 수준: 시총 대비 ${ratio}% — 2021년 수준의 파이프라인 압력이 누적되고 있습니다.`; }
    else                       { sitText  = `✅ IPO 파이프라인 정상: 시총 대비 ${ratio}% — 시장 유동성에 큰 영향 없음.`; }

    let advice = "";
    if      (score >= 70) advice = "📌 IPO 참여 최소화. 기존 포트폴리오 현금 비중 확대. 대형 IPO 락업 해제 일정 사전 점검.";
    else if (score >= 40) advice = "📌 신규 IPO 선별적 접근. 상장 첫날 매수보다 안정화 후 진입 전략 권장.";
    else                  advice = "📌 IPO 환경 우호적. 우량 기업 공모 참여 고려 가능.";

    return `
      <div class="front-metrics-block">
        <div class="front-metric-row"><span class="front-metric-label">실제 파이프라인 총액</span><span class="front-metric-val val-red">$${totalRaw.toFixed(0)}B</span></div>
        <div class="front-metric-row"><span class="front-metric-label">가중 위험 환산액</span><span class="front-metric-val ${pipelineClass}">$${totalVal.toFixed(0)}B</span></div>
        <div class="front-metric-row"><span class="front-metric-label">시총 대비 비율</span><span class="front-metric-val ${pipelineClass}">${ratio}%</span></div>
        <div class="front-metric-row"><span class="front-metric-label">위험 수준</span><span class="front-metric-val ${pipelineClass}">${pipelineLabel}</span></div>
        <div class="front-metric-row"><span class="front-metric-label">신청완료 기업 수</span><span class="front-metric-val ${filed>0?'val-yellow':'val-green'}">${filed}개</span></div>
        <div class="front-metric-row"><span class="front-metric-label">가격확정 기업 수</span><span class="front-metric-val ${priced>0?'val-red':'val-green'}">${priced}개</span></div>
      </div>
      <div class="front-situation ${sitColor}">${sitText}</div>
      <div class="front-advice">💡 ${advice}</div>`;
  }

  return "";
}

/* ── 뒷면 콘텐츠 빌더 ────────────────────────────────────── */
function buildBackContent(prefix, score, raw) {

  if (prefix === "w1") {
    return `
      <div class="back-content">
        <div class="back-section">
          <h4>📐 수치 해설</h4>
          <div class="back-metric"><span class="back-label">SPY YTD</span><span class="back-value">S&amp;P500 시가총액 가중 ETF 연초 대비 수익률</span></div>
          <div class="back-metric"><span class="back-label">RSP YTD</span><span class="back-value">S&amp;P500 동일가중 ETF 연초 대비 수익률</span></div>
          <div class="back-metric"><span class="back-label">SPY-RSP 스프레드</span><span class="back-value">두 ETF 수익률 차이 — 클수록 소수 종목 쏠림</span></div>
          <div class="back-metric"><span class="back-label">스프레드 백분위</span><span class="back-value">과거 대비 현재 스프레드 상대 위치</span></div>
          <div class="back-metric"><span class="back-label">RSP 역행 신호</span><span class="back-value">SPY 상승 중 RSP 하락 = 쏠림 극단 경고</span></div>
        </div>
        <div class="back-section">
          <h4>📌 위험 기준</h4>
          <div class="back-metric"><span class="back-label">스프레드 &lt; 2%p</span><span class="back-value" style="color:#34d399">정상 — 균형 장세</span></div>
          <div class="back-metric"><span class="back-label">2 ~ 4%p</span><span class="back-value" style="color:#fbbf24">주의 — 쏠림 시작</span></div>
          <div class="back-metric"><span class="back-label">4 ~ 6%p</span><span class="back-value" style="color:#f97316">경고 — 2022년 수준</span></div>
          <div class="back-metric"><span class="back-label">6%p 이상</span><span class="back-value" style="color:#f87171">위험 — 닷컴버블 수준</span></div>
        </div>
        <div class="back-section">
          <h4>🔢 점수 산출</h4>
          <div class="back-metric"><span class="back-label">산출 방식</span><span class="back-value">스프레드 크기 50% + 백분위 30% + RSP 역행 20%</span></div>
        </div>
      </div>`;
  }

  if (prefix === "w2") {
    return `
      <div class="back-content">
        <div class="back-section">
          <h4>📐 수치 해설</h4>
          <div class="back-metric"><span class="back-label">미국 10년물</span><span class="back-value">장기 성장·인플레이션 기대치 반영</span></div>
          <div class="back-metric"><span class="back-label">미국 2년물</span><span class="back-value">단기 연준 정책금리 기대치 반영</span></div>
          <div class="back-metric"><span class="back-label">장단기 스프레드</span><span class="back-value">10Y - 2Y, 음수 = 역전 (경기침체 선행신호)</span></div>
          <div class="back-metric"><span class="back-label">TIPS 실질금리</span><span class="back-value">인플레이션 제거 실질 금리 — 높을수록 주식 부담</span></div>
        </div>
        <div class="back-section">
          <h4>📌 위험 기준</h4>
          <div class="back-metric"><span class="back-label">10년물 &lt; 4.0%</span><span class="back-value" style="color:#34d399">정상 — 밸류에이션 부담 없음</span></div>
          <div class="back-metric"><span class="back-label">4.0 ~ 4.5%</span><span class="back-value" style="color:#fbbf24">주의 — 부담 시작</span></div>
          <div class="back-metric"><span class="back-label">4.5 ~ 5.0%</span><span class="back-value" style="color:#f97316">경고 — 조정 동반 구간</span></div>
          <div class="back-metric"><span class="back-label">장단기 역전</span><span class="back-value" style="color:#f87171">위험 — 1969년 이후 침체 100% 선행</span></div>
        </div>
        <div class="back-section">
          <h4>🔢 점수 산출</h4>
          <div class="back-metric"><span class="back-label">산출 방식</span><span class="back-value">10년물 수준 40% + 역전 여부·깊이 40% + 금리인상 우려 20%</span></div>
        </div>
      </div>`;
  }

  if (prefix === "w3") {
    return `
      <div class="back-content">
        <div class="back-section">
          <h4>📐 수치 해설</h4>
          <div class="back-metric"><span class="back-label">HY 스프레드</span><span class="back-value">하이일드 채권 vs 국채 금리 차이 (신용 공포 지수)</span></div>
          <div class="back-metric"><span class="back-label">IG 스프레드</span><span class="back-value">투자등급 회사채 vs 국채 금리 차이</span></div>
          <div class="back-metric"><span class="back-label">HY 1개월 변화</span><span class="back-value">최근 한 달 스프레드 변동 — 급등이 핵심 신호</span></div>
        </div>
        <div class="back-section">
          <h4>📌 위험 기준</h4>
          <div class="back-metric"><span class="back-label">HY &lt; 300 bps</span><span class="back-value" style="color:#34d399">정상 — 역사적 저점권</span></div>
          <div class="back-metric"><span class="back-label">300 ~ 350 bps</span><span class="back-value" style="color:#fbbf24">주의 — 평균 상회</span></div>
          <div class="back-metric"><span class="back-label">350 ~ 600 bps</span><span class="back-value" style="color:#f97316">경고 — 스트레스 구간</span></div>
          <div class="back-metric"><span class="back-label">600 bps 이상</span><span class="back-value" style="color:#f87171">위험 — 금융위기 수준</span></div>
        </div>
        <div class="back-section">
          <h4>🔢 점수 산출</h4>
          <div class="back-metric"><span class="back-label">산출 방식</span><span class="back-value">HY 절대치 50% + HY 1개월 변화 30% + IG 수준 20%</span></div>
        </div>
      </div>`;
  }

  if (prefix === "w4") {
    return `
      <div class="back-content">
        <div class="back-section">
          <h4>📐 수치 해설</h4>
          <div class="back-metric"><span class="back-label">가중 파이프라인</span><span class="back-value">기업가치 × 상태가중치 합산 (실제 흡수 위험)</span></div>
          <div class="back-metric"><span class="back-label">상태별 가중치</span><span class="back-value">루머 10% / 검토중 30% / 신청완료 100% / 상장완료 0%</span></div>
          <div class="back-metric"><span class="back-label">시총 대비 비율</span><span class="back-value">가중 파이프라인 ÷ 미국 시총($69조) × 100</span></div>
        </div>
        <div class="back-section">
          <h4>📌 위험 기준 (역사적 근거)</h4>
          <div class="back-metric"><span class="back-label">&lt; 0.15%</span><span class="back-value" style="color:#34d399">정상 — 2010~16년 회복기 수준</span></div>
          <div class="back-metric"><span class="back-label">0.15 ~ 0.25%</span><span class="back-value" style="color:#fbbf24">주의 — 2021년 SPAC 붐 수준</span></div>
          <div class="back-metric"><span class="back-label">0.25 ~ 0.45%</span><span class="back-value" style="color:#f97316">경고 — 1999~2000년 닷컴버블 수준</span></div>
          <div class="back-metric"><span class="back-label">0.45% 이상</span><span class="back-value" style="color:#f87171">위험 — 닷컴버블 초과, 전례 없음</span></div>
        </div>
        <div class="back-section">
          <h4>🔢 점수 산출</h4>
          <div class="back-metric"><span class="back-label">산출 방식</span><span class="back-value">시총 대비 비율 구간별 점수 + 신청완료 수 × 5점 (최대 20점)</span></div>
        </div>
      </div>`;
  }

  return "";
}

/* ── 앞면 메트릭 그리드 (레거시 호환) ───────────────────── */
function buildMetrics(prefix, score, raw) {
  return [];
}

/* ── 카드 렌더 ───────────────────────────────────────────── */
function renderCard(prefix, score, raw) {
  const badge = document.getElementById(`score-${prefix}`);
  if (badge) {
    badge.textContent = score.toFixed(1);
    badge.className   = `card-score-badge ${scoreGradeClass(score)}`;
  }
  const wBadge = document.getElementById(`weight-${prefix}`);
  if (wBadge) wBadge.textContent = `가중치 ${(WEIGHTS[prefix]*100).toFixed(0)}%`;

  drawMiniBar(`bar-${prefix}`, score);

  const sigList = document.getElementById(`signals-${prefix}`);
  if (sigList && raw?.signals) {
    sigList.innerHTML = raw.signals.map(sig => {
      let cls = "GREEN";
      if      (sig.includes("🚨"))                         cls = "RED";
      else if (sig.includes("⚠️"))                        cls = "ORANGE";
      else if (sig.includes("📢") || sig.includes("🔍"))  cls = "YELLOW";
      return `<div class="signal-item ${cls}">
        <div class="signal-dot ${cls}"></div>
        <span>${sig}</span>
      </div>`;
    }).join("");
  }

  const frontBody = document.getElementById(`front-body-${prefix}`);
  if (frontBody) frontBody.innerHTML = buildFrontContent(prefix, score, raw);

  const backBody = document.getElementById(`back-body-${prefix}`);
  if (backBody)  backBody.innerHTML  = buildBackContent(prefix, score, raw);
}

/* ── 복합 점수 렌더 ─────────────────────────────────────── */
function renderComposite(data) {
  const score = data.composite_score ?? 0;
  const grade = data.grade ?? "GREEN";

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

  const actionEl = document.getElementById("action-rec");
  if (actionEl) {
    let action = "현재 시장은 안정적입니다. 기존 전략을 유지하세요.";
    if      (score >= 80) action = "🚨 즉각적인 리스크 감축이 필요합니다. 주식 비중을 대폭 줄이고 현금 및 안전자산으로 이동하세요.";
    else if (score >= 70) action = "⚠️ 위험 수준 도달. 방어적 포지션 강화 및 헤지 전략 실행을 권장합니다.";
    else if (score >= 55) action = "📢 경고 단계 진입. 포트폴리오 리밸런싱 및 익스포저 점검이 필요합니다.";
    else if (score >= 40) action = "🔍 주의 단계. 위험 지표를 지속 모니터링하며 방어적 준비를 시작하세요.";
    actionEl.textContent = action;
  }

  const sigBadge = document.getElementById("algo-signal-badge");
  const sigDesc  = document.getElementById("algo-signal-desc");
  if (sigBadge && sigDesc) {
    if      (score >= 70) { sigBadge.textContent = "RISK-OFF"; sigBadge.style.background = "#ef4444"; sigDesc.textContent = "전체 위험 지표가 임계치를 초과했습니다."; }
    else if (score >= 40) { sigBadge.textContent = "CAUTION";  sigBadge.style.background = "#f59e0b"; sigDesc.textContent = "복수의 경고 신호가 감지되고 있습니다."; }
    else                  { sigBadge.textContent = "RISK-ON";  sigBadge.style.background = "#10b981"; sigDesc.textContent = "전반적인 시장 환경이 우호적입니다."; }
  }

  const hedgeEl = document.getElementById("hedge-rec");
  if (hedgeEl) {
    if      (score >= 70) hedgeEl.textContent = "헤지 권장: VIX 콜옵션, 인버스 ETF, 금·달러 비중 확대";
    else if (score >= 40) hedgeEl.textContent = "부분 헤지 권장: 방어주 비중 확대, 포트폴리오 분산 강화";
    else                  hedgeEl.textContent = "헤지 불필요: 위험 지표 정상 범위 내 유지 중";
  }

  const bars = [
    { label: "선도주압축", score: data.w1?.score ?? 0 },
    { label: "채권·금리",  score: data.w2?.score ?? 0 },
    { label: "사모크레딧", score: data.w3?.score ?? 0 },
    { label: "대형IPO",    score: data.w4?.score ?? 0 },
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

  const stormSection = document.getElementById("storm-section");
  if (stormSection) stormSection.style.display = score >= 80 ? "block" : "none";

  const tsEl = document.getElementById("last-updated");
  if (tsEl && data.timestamp) {
    const d = new Date(data.timestamp);
    tsEl.textContent = `Last updated: ${d.toLocaleString("ko-KR", { timeZone: "Asia/Seoul" })} KST`;
  }
}

/* ── 히스토리 차트 ───────────────────────────────────────── */
function loadHistory() {
  fetch(HISTORY_URL)
    .then(r => r.text())
    .then(text => {
      const entries = text.trim().split("\n")
        .filter(l => l.trim())
        .map(l => {
          try {
            const obj   = JSON.parse(l);
            const score = obj.score ?? obj.composite_score;
            const date  = obj.date ?? "";
            if (score != null && date) return { date, score: parseFloat(score) };
            return null;
          } catch { return null; }
        })
        .filter(s => s != null);
      if (entries.length) drawHistoryChart(entries);
      else {
        const fallback = [35,38,32,40,45,42,38,35,30,32,35,38,42,40,38,35,32,35,42,35]
          .map((s, i) => ({ date: `Day-${20-i}`, score: s }));
        drawHistoryChart(fallback);
      }
    })
    .catch(() => {
      const fallback = [35,38,32,40,45,42,38,35,30,32,35,38,42,40,38,35,32,35,42,35]
        .map((s, i) => ({ date: `Day-${20-i}`, score: s }));
      drawHistoryChart(fallback);
    });
}

/* ── 데이터 로드 ─────────────────────────────────────────── */
function loadData() {
  fetch(DATA_URL)
    .then(r => r.json())
    .then(data => {
      renderComposite(data);
      ["w1","w2","w3","w4"].forEach(p => {
        const score = data[p]?.score ?? 0;
        const raw   = data[p] ?? {};
        renderCard(p, score, raw);
      });
      loadHistory();
      setTimeout(equalizeCardHeights, 100);
      setTimeout(equalizeCardHeights, 500);
    })
    .catch(err => {
      console.error("데이터 로드 실패:", err);
      const fallback = {
        composite_score: 62, grade: "YELLOW", timestamp: new Date().toISOString(),
        w1: { score: 58, spy_ytd: 11.24, rsp_ytd: 9.48, current_spread: 1.76, spread_percentile: 55, rsp_1w_return: 1.5, rsp_is_negative_while_spy_positive: false, signals: ["📢 스프레드 주의 수준"] },
        w2: { score: 65, us10y_yield: 4.42, us2y_yield: 4.18, term_spread: 0.24, is_inverted: false, rate_hike_concern: false, tips_10y_real_yield: 1.9, signals: ["⚠️ 10년물 4.4% 상회"] },
        w3: { score: 55, hy_bps: 320, ig_bps: 95, hy_change_bps: 15, ig_change_bps: 8, stress_level: "보통", signals: ["📢 HY 스프레드 확대 중"] },
        w4: { score: 72, total_valuation_bn: 2523, pipeline_ratio_pct: 3.66, filed_count: 3, priced_count: 0,
          signals: ["🚨 파이프라인 비율 3.66% — 닷컴버블(0.45%) 초과, 전례 없는 수준"],
          ipo_list: [
            { company: "SpaceX",     valuation_bn: 1800, status: "신청완료" },
            { company: "OpenAI",     valuation_bn: 852,  status: "검토중" },
            { company: "Anthropic",  valuation_bn: 965,  status: "검토중" },
            { company: "Databricks", valuation_bn: 134,  status: "검토중" },
            { company: "Stripe",     valuation_bn: 159,  status: "검토중" },
            { company: "Cerebras",   valuation_bn: 95,   status: "상장완료", ticker: "CBRS" },
            { company: "Revolut",    valuation_bn: 75,   status: "신청완료" },
            { company: "Discord",    valuation_bn: 15,   status: "신청완료" },
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
