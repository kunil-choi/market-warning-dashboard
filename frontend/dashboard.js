// ============================================================
// dashboard.js – 글로벌 주식시장 위기경보 대시보드 렌더러
// 수정:
//   Bug2  – toggleFlip: flip- 래퍼에 .flipped 토글
//   Bug3  – warning-bar 클래스명 styles.css 와 일치
//   Bug4  – 앞면: 현재수치 + 현재상황진단 + 투자시사점
//            뒷면: 수치해설 + 위험기준 + 점수산출
//   Bug5  – W4 IPO 카드 중복 제거 및 테이블 통합
//   Fix6  – W4 뒷면 시총 대비 비율 기준 임계치로 교체
//   Fix7  – 폴백 데이터 valuation_b → valuation_bn 키 통일
//   Fix8  – W4 앞면 pipeline_ratio_pct 표시 추가
//   Fix9  – 2026-05-01 이후 / $50B 이상 기업만 포함
//   Fix10 – 가중치 재설계 (검토중 0.1 / 제출완료 0.7 / 가격확정 1.0)
//   Fix11 – '신청완료' → '제출완료' 용어 통일
//   Fix12 – 상장완료 기업 화면 표시 제외
//   Fix13 – 카드 헤더: 배지를 제목 아래 배치 (index.html 과 연동)
//   Fix14 – 시간 표시 24시간제 (hour12: false)
//   Fix15 – ID 불일치 수정: signal-badge→algo-signal-badge, signal-desc→algo-signal-desc
//            score-badge-w* → score-w*, front-w* → front-body-w*, back-w* → back-body-w*
//   Fix16 – W3 키 불일치 수정: hy_spread→hy_bps, ig_spread→ig_bps, hy_spread_change_1m→hy_change_bps
// ============================================================

const DATA_URL    = "./data/latest_scores.json";
const HISTORY_URL = "./data/history.jsonl";

const WEIGHTS = { w1: 0.25, w2: 0.30, w3: 0.20, w4: 0.25 };

// Fix10: 가중치 재설계
const STATUS_WEIGHT = {
  "루머":     0.0,
  "검토중":   0.1,
  "제출완료": 0.7,
  "신청완료": 0.7,   // 구버전 데이터 호환
  "가격확정": 1.0,
  "상장완료": 0.0,
};

// Fix11: 배지 CSS 클래스 매핑 (상장완료 제거)
const statusClassMap = {
  "루머":     "루머",
  "검토중":   "검토중",
  "제출완료": "제출완료",
  "신청완료": "제출완료",  // 구버전 데이터 호환 → 동일 배지
  "가격확정": "가격확정",
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
  // Reset heights so we can measure natural content size
  wrappers.forEach(w => { w.style.height = ""; });
  let maxH = 0;
  wrappers.forEach(w => {
    // card-front is position:absolute so offsetHeight of wrapper = min-height only.
    // Measure the actual scrollHeight of the card-front instead.
    const front = w.querySelector(".card-front");
    const h = front ? front.scrollHeight : w.offsetHeight;
    maxH = Math.max(maxH, h);
  });
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
// Fix12: 상장완료 기업 화면 표시 제외
// Fix11: 신청완료 → 제출완료 표시
function renderIPOTable(ipoList) {
  if (!ipoList || !ipoList.length) {
    return "<p style='font-size:0.74rem;color:#64748b'>데이터 없음</p>";
  }

  // 상장완료 제외 필터
  const filtered = ipoList.filter(ipo => {
    const st = ipo.status || "";
    return st !== "상장완료" && st !== "Trading";
  });

  if (!filtered.length) {
    return "<p style='font-size:0.74rem;color:#64748b'>표시할 IPO 없음</p>";
  }

  let html = `
    <div class="ipo-table-wrapper">
      <table class="ipo-table">
        <thead><tr>
          <th>기업</th>
          <th>기업가치</th>
          <th>상태</th>
          <th>가중치</th>
          <th>위험환산</th>
        </tr></thead>
        <tbody>`;

  filtered.forEach(ipo => {
    const val    = ipo.valuation_bn ?? ipo.valuation_b ?? 0;
    // Fix11: 신청완료 → 제출완료 표시
    let st       = ipo.status || "루머";
    if (st === "신청완료") st = "제출완료";
    const wt     = STATUS_WEIGHT[st] ?? 0.0;
    const wVal   = (val * wt).toFixed(0);
    const cls    = statusClassMap[st] || "루머";
    const name   = ipo.company || ipo.short_name || ipo.name || "—";
    const ticker = ipo.ticker ? ` <span style="color:#64748b;font-size:0.7rem">(${ipo.ticker})</span>` : "";

    html += `
        <tr>
          <td style="font-weight:600">${name}${ticker}</td>
          <td style="font-family:monospace">$${val}B</td>
          <td><span class="status-badge status-${cls}">${st}</span></td>
          <td style="font-family:monospace;text-align:center">${(wt * 100).toFixed(0)}%</td>
          <td style="font-family:monospace;color:#f59e0b">$${wVal}B</td>
        </tr>`;
  });

  html += `</tbody></table></div>`;
  return html;
}

/* ── 앞면 콘텐츠 빌더 ────────────────────────────────────── */
function buildFrontContent(prefix, score, raw) {
  const color      = scoreColor(score);
  const label      = scoreLabel(score);
  const gradeClass = scoreGradeClass(score);

  /* ────────── W1: 선도주 압축 ────────── */
  if (prefix === "w1") {
    const spy   = raw?.spy_ytd        != null ? parseFloat(raw.spy_ytd).toFixed(2)        : "—";
    const rsp   = raw?.rsp_ytd        != null ? parseFloat(raw.rsp_ytd).toFixed(2)        : "—";
    const sp    = raw?.current_spread != null ? raw.current_spread.toFixed(2)             : "—";
    const pct   = raw?.spread_percentile ?? "—";
    const rsp1w = raw?.rsp_1w_return  != null ? parseFloat(raw.rsp_1w_return).toFixed(2) : "—";
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
        <div class="front-metric-row">
          <span class="front-metric-label">SPY YTD</span>
          <span class="front-metric-val ${(parseFloat(spy)||0)>=0?'val-green':'val-red'}">${spy}%</span>
        </div>
        <div class="front-metric-row">
          <span class="front-metric-label">RSP YTD</span>
          <span class="front-metric-val ${(parseFloat(rsp)||0)>=0?'val-green':'val-red'}">${rsp}%</span>
        </div>
        <div class="front-metric-row">
          <span class="front-metric-label">SPY-RSP 스프레드</span>
          <span class="front-metric-val ${spread>=4?'val-red':spread>=2?'val-yellow':'val-green'}">${sp}%p</span>
        </div>
        <div class="front-metric-row">
          <span class="front-metric-label">스프레드 백분위</span>
          <span class="front-metric-val ${pct>=80?'val-red':pct>=60?'val-yellow':'val-green'}">${pct}%ile</span>
        </div>
        <div class="front-metric-row">
          <span class="front-metric-label">RSP 1주 수익률</span>
          <span class="front-metric-val ${(parseFloat(rsp1w)||0)>=0?'val-green':'val-red'}">${rsp1w}%</span>
        </div>
        <div class="front-metric-row">
          <span class="front-metric-label">RSP 역행 신호</span>
          <span class="front-metric-val ${rspNeg?'val-red':'val-green'}">${rspNeg?'🚨 발생':'✅ 없음'}</span>
        </div>
      </div>
      <div class="front-situation ${sitColor}">${sitText}</div>
      <div class="front-advice">💡 ${advice}</div>`;
  }

  /* ────────── W2: 채권·금리 ────────── */
  if (prefix === "w2") {
    const t10     = raw?.us10y_yield ?? raw?.us_10yr ?? "—";
    const t2      = raw?.us2y_yield  ?? raw?.us_2yr  ?? "—";
    const term    = raw?.term_spread != null ? raw.term_spread.toFixed(2) : "—";
    const inv     = raw?.is_inverted ?? raw?.inverted ?? false;
    const tipsReal = raw?.tips_10y_real_yield ?? 0;
    const hi      = raw?.rate_hike_concern ?? (tipsReal >= 2.0);
    const termNum = raw?.term_spread ?? 0;
    const t10Num  = parseFloat(t10) || 0;

    let sitColor = "GREEN", sitText = "";
    if      (inv || termNum < -0.5) { sitColor = "RED";    sitText = "🚨 심각한 장단기 금리 역전: 과거 사례상 12~18개월 내 경기침체 가능성이 높습니다."; }
    else if (termNum < 0)           { sitColor = "ORANGE"; sitText = "⚠️ 금리 역전 진행 중: 시장이 미래 성장 둔화를 반영하고 있습니다."; }
    else if (score >= 40 || t10Num >= 4.5) { sitColor = "YELLOW"; sitText = "📢 금리 급등 경계: 10년물 고점에서의 변동성 확대 가능성을 주시해야 합니다."; }
    else                            { sitText  = "✅ 금리 구조 안정: 장단기 스프레드가 정상 범위를 유지하고 있습니다."; }

    let advice = "";
    if      (score >= 70) advice = "📌 장기채 비중 축소. 듀레이션 단축(단기채·MMF 확대). TIPS 또는 변동금리 채권 편입 검토.";
    else if (score >= 40) advice = "📌 채권 포트폴리오 듀레이션 중립 유지. 금리 추가 상승 시 단기채 비율 증가 준비.";
    else                  advice = "📌 현재 금리 환경 우호적. 투자등급 회사채 일부 편입 고려 가능.";

    return `
      <div class="front-metrics-block">
        <div class="front-metric-row">
          <span class="front-metric-label">미국 10년물</span>
          <span class="front-metric-val ${t10Num>=4.5?'val-red':t10Num>=4?'val-yellow':'val-green'}">${t10}%</span>
        </div>
        <div class="front-metric-row">
          <span class="front-metric-label">미국 2년물</span>
          <span class="front-metric-val ${(parseFloat(t2)||0)>=5?'val-red':(parseFloat(t2)||0)>=4.5?'val-yellow':'val-green'}">${t2}%</span>
        </div>
        <div class="front-metric-row">
          <span class="front-metric-label">장단기 스프레드</span>
          <span class="front-metric-val ${termNum<0?'val-red':termNum<0.5?'val-yellow':'val-green'}">${term}%p</span>
        </div>
        <div class="front-metric-row">
          <span class="front-metric-label">10년 실질금리(TIPS)</span>
          <span class="front-metric-val ${tipsReal>=2.5?'val-red':tipsReal>=2.0?'val-yellow':'val-green'}">${tipsReal.toFixed(2)}%</span>
        </div>
        <div class="front-metric-row">
          <span class="front-metric-label">장단기 역전</span>
          <span class="front-metric-val ${inv?'val-red':'val-green'}">${inv?'🚨 역전':'✅ 정상'}</span>
        </div>
        <div class="front-metric-row">
          <span class="front-metric-label">금리 인상 우려</span>
          <span class="front-metric-val ${hi?'val-orange':'val-green'}">${hi?'⚠️ 있음':'✅ 없음'}</span>
        </div>
      </div>
      <div class="front-situation ${sitColor}">${sitText}</div>
      <div class="front-advice">💡 ${advice}</div>`;
  }

  /* ────────── W3: 사모크레딧 환매 위험 ────────── */
  if (prefix === "w3") {
    const bdcDisc  = raw?.bdc_nav_discount ?? null;
    const bdcDate  = raw?.bdc_nav_date     ?? "";
    const sloos    = raw?.sloos_ci_pct     ?? null;
    const ciDelq   = raw?.ci_delq_pct      ?? null;
    const hy       = raw?.hy_bps ?? raw?.hy_spread ?? 0;
    const ig       = raw?.ig_bps ?? raw?.ig_spread ?? 0;
    const hyChg    = raw?.hy_change_bps ?? raw?.hy_spread_change_1m ?? 0;

    // 상황 판단: 주 지표(BDC 할인, SLOOS) 우선
    let sitColor = "GREEN", sitText = "";
    if      (bdcDisc >= 25 || sloos >= 50) {
      sitColor = "RED";
      sitText  = "🚨 사모크레딧 위기: BDC 할인율 급등 또는 은행 C&I 긴축이 위기 수준입니다. 환매 게이팅 발생 가능성이 높습니다.";
    } else if (bdcDisc >= 15 || sloos >= 30) {
      sitColor = "ORANGE";
      sitText  = "⚠️ 사모크레딧 스트레스: 유동성 미스매치 위험이 쌓이고 있습니다. 인터벌 펀드·비상장 BDC 익스포저를 점검하세요.";
    } else if (bdcDisc >= 5 || sloos >= 15 || hy >= 350) {
      sitColor = "YELLOW";
      sitText  = "📢 사모크레딧 경계: HY 스프레드는 안정적이지만 구조적 유동성 위험 신호가 소폭 감지됩니다.";
    } else {
      sitText  = "✅ 사모크레딧 안정: BDC 할인율·대출 긴축 모두 정상 범위. 공개시장 스프레드도 타이트.";
    }

    let advice = "";
    if      (score >= 70) advice = "📌 비상장 BDC·인터벌 펀드 환매 지연 위험. 사모크레딧 익스포저 즉시 점검. 유동성 확보 최우선.";
    else if (score >= 40) advice = "📌 사모크레딧 신규 편입 자제. 분기 환매 한도(게이팅) 발동 여부 모니터링.";
    else                  advice = "📌 사모크레딧 환경 양호. BDC 할인율과 SLOOS 추이를 분기별로 확인하세요.";

    const bdcColor  = bdcDisc >= 15 ? "val-red" : bdcDisc >= 5 ? "val-yellow" : "val-green";
    const sloosColor = sloos >= 30 ? "val-red" : sloos >= 15 ? "val-yellow" : sloos <= -10 ? "val-green" : "val-green";
    const ciColor   = ciDelq >= 3.0 ? "val-red" : ciDelq >= 2.0 ? "val-yellow" : "val-green";
    const hyColor   = hy >= 400 ? "val-red" : hy >= 300 ? "val-yellow" : "val-green";

    return `
      <div class="front-metrics-block">
        <div class="front-metric-row">
          <span class="front-metric-label">BDC NAV 할인율 <span style="font-size:0.65rem;color:#64748b">주</span></span>
          <span class="front-metric-val ${bdcColor}">${bdcDisc != null ? bdcDisc.toFixed(1)+'%' : '—'}${bdcDate ? ` <span style="font-size:0.65rem;color:#64748b">(${bdcDate})</span>` : ''}</span>
        </div>
        <div class="front-metric-row">
          <span class="front-metric-label">C&I 대출 긴축(SLOOS) <span style="font-size:0.65rem;color:#64748b">주</span></span>
          <span class="front-metric-val ${sloosColor}">${sloos != null ? sloos.toFixed(1)+'%' : '—'}</span>
        </div>
        <div class="front-metric-row">
          <span class="front-metric-label">C&I 연체율 <span style="font-size:0.65rem;color:#64748b">주</span></span>
          <span class="front-metric-val ${ciColor}">${ciDelq != null ? ciDelq.toFixed(2)+'%' : '—'}</span>
        </div>
        <div class="front-metric-row">
          <span class="front-metric-label">HY 스프레드 <span style="font-size:0.65rem;color:#64748b">보조</span></span>
          <span class="front-metric-val ${hyColor}">${hy} bps</span>
        </div>
        <div class="front-metric-row">
          <span class="front-metric-label">HY 1개월 변화 <span style="font-size:0.65rem;color:#64748b">보조</span></span>
          <span class="front-metric-val ${hyChg>=50?'val-red':hyChg>=20?'val-yellow':hyChg<0?'val-green':'val-orange'}">${hyChg>0?'+':''}${hyChg} bps</span>
        </div>
      </div>
      <div class="front-situation ${sitColor}">${sitText}</div>
      <div class="front-advice">💡 ${advice}</div>`;
  }

  /* ────────── W4: 대형 IPO 유동성 ────────── */
  if (prefix === "w4") {
    const totalVal  = raw?.total_valuation_bn   ?? 0;
    const ratio     = raw?.pipeline_ratio_pct   ?? 0;
    const mktCap    = raw?.us_market_cap_bn      ?? 69000;
    const filed     = raw?.filed_count           ?? 0;
    const priced    = raw?.priced_count          ?? 0;
    const ipoList   = raw?.ipo_list              ?? [];
    const alerts    = raw?.alerts                ?? [];

    let sitColor = "GREEN", sitText = "";
    if      (ratio >= 0.45) { sitColor = "RED";    sitText = `🚨 닷컴버블 초과 (${ratio.toFixed(2)}%): 전례 없는 수준의 IPO 유동성 흡수 압력입니다.`; }
    else if (ratio >= 0.25) { sitColor = "ORANGE"; sitText = `⚠️ 닷컴버블 수준 (${ratio.toFixed(2)}%): 1999~2000년과 유사한 IPO 과열 구간입니다.`; }
    else if (ratio >= 0.15) { sitColor = "YELLOW"; sitText = `📢 SPAC 붐 수준 (${ratio.toFixed(2)}%): 2021년 수준의 IPO 압력이 감지됩니다.`; }
    else                    { sitText  = `✅ IPO 압력 정상 (${ratio.toFixed(2)}%): 시장 유동성 흡수 위험이 낮습니다.`; }

    let advice = "";
    if      (score >= 70) advice = "📌 대형 IPO 공모 참여 자제. 기존 성장주 포트폴리오 유동성 확보 필요. 상장 이후 6개월 가격 안정화 후 접근 권장.";
    else if (score >= 40) advice = "📌 IPO 공모 선별 참여. 상장 초기 변동성 확대 가능성 감안하여 분할 매수 전략 적용.";
    else                  advice = "📌 IPO 시장 정상 수준. 우량 IPO 공모 참여 가능.";

    return `
      <div class="front-metrics-block">
        <div class="front-metric-row">
          <span class="front-metric-label">가중 파이프라인</span>
          <span class="front-metric-val ${ratio>=0.45?'val-red':ratio>=0.25?'val-orange':ratio>=0.15?'val-yellow':'val-green'}">$${totalVal.toFixed(0)}B</span>
        </div>
        <div class="front-metric-row">
          <span class="front-metric-label">시총 대비 비율</span>
          <span class="front-metric-val ${ratio>=0.45?'val-red':ratio>=0.25?'val-orange':ratio>=0.15?'val-yellow':'val-green'}">${ratio.toFixed(4)}%</span>
        </div>
        <div class="front-metric-row">
          <span class="front-metric-label">기준 시총</span>
          <span class="front-metric-val val-green">$${(mktCap/1000).toFixed(0)}조</span>
        </div>
        <div class="front-metric-row">
          <span class="front-metric-label">가격확정 건수</span>
          <span class="front-metric-val ${priced>0?'val-red':'val-green'}">${priced}건</span>
        </div>
        <div class="front-metric-row">
          <span class="front-metric-label">제출완료 건수</span>
          <span class="front-metric-val ${filed>0?'val-orange':'val-green'}">${filed}건</span>
        </div>
      </div>
      ${alerts.length ? `<div class="front-situation ${sitColor}">${alerts[0]}</div>` : `<div class="front-situation ${sitColor}">${sitText}</div>`}
      <div class="front-advice">💡 ${advice}</div>`;
  }

  return "";
}

/* ── 뒷면 콘텐츠 빌더 ────────────────────────────────────── */
function buildBackContent(prefix, score, raw) {

  /* ────────── W1 뒷면 ────────── */
  if (prefix === "w1") {
    return `
      <div class="back-content">
        <div class="back-section">
          <h4>📐 수치 해설</h4>
          <div class="back-metric"><span class="back-label">SPY YTD</span><span class="back-value">S&amp;P500 시가총액 가중 ETF 연초 대비 수익률</span></div>
          <div class="back-metric"><span class="back-label">RSP YTD</span><span class="back-value">S&amp;P500 동일가중 ETF 연초 대비 수익률</span></div>
          <div class="back-metric"><span class="back-label">SPY-RSP 스프레드</span><span class="back-value">두 ETF 수익률 차이 — 클수록 소수 종목 쏠림 심화</span></div>
          <div class="back-metric"><span class="back-label">스프레드 백분위</span><span class="back-value">과거 대비 현재 스프레드 상대적 위치</span></div>
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
          <div class="back-formula">
            <p>스프레드 크기 <strong>50%</strong> + 백분위 <strong>30%</strong> + RSP 역행 <strong>20%</strong></p>
          </div>
        </div>
      </div>`;
  }

  /* ────────── W2 뒷면 ────────── */
  if (prefix === "w2") {
    return `
      <div class="back-content">
        <div class="back-section">
          <h4>📐 수치 해설</h4>
          <div class="back-metric"><span class="back-label">미국 10년물</span><span class="back-value">장기 성장·인플레이션 기대치 반영</span></div>
          <div class="back-metric"><span class="back-label">미국 2년물</span><span class="back-value">단기 연준 정책금리 기대치 반영</span></div>
          <div class="back-metric"><span class="back-label">장단기 스프레드</span><span class="back-value">10Y - 2Y, 음수 = 역전 (경기침체 선행신호)</span></div>
          <div class="back-metric"><span class="back-label">TIPS 실질금리</span><span class="back-value">인플레이션 제거 실질 금리 — 높을수록 주식 밸류에이션 부담</span></div>
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
          <div class="back-formula">
            <p>10년물 수준 <strong>40%</strong> + 역전 여부·깊이 <strong>40%</strong> + 금리인상 우려 <strong>20%</strong></p>
          </div>
        </div>
      </div>`;
  }

  /* ────────── W3 뒷면 ────────── */
  if (prefix === "w3") {
    return `
      <div class="back-content">
        <div class="back-section">
          <h4>⚠️ HY/IG 스프레드의 한계</h4>
          <p style="font-size:0.76rem;color:#94a3b8;line-height:1.5">
            HY/IG 스프레드는 매일 시가평가(mark-to-market)되는 공개시장 채권을 봅니다.
            사모크레딧은 모델 평가(mark-to-model)라 마크가 매끄럽게(smoothed) 움직이고,
            환매 중단(게이팅)은 신용 사건이 아니라 <strong>유동성 사건</strong>이므로
            스프레드가 멀쩡해도 런(run)이 발생할 수 있습니다.
            이 카드는 HY/IG를 보조 지표로만 씁니다.
          </p>
        </div>
        <div class="back-section">
          <h4>📐 주 지표 해설</h4>
          <div class="back-metric"><span class="back-label">BDC NAV 할인율</span><span class="back-value">상장 BDC 주가 vs 운용사 NAV 차이. 시장이 사모 마크를 못 믿으면 할인 확대. 실시간에 가장 가까운 신호.</span></div>
          <div class="back-metric"><span class="back-label">C&I 대출 긴축(SLOOS)</span><span class="back-value">연준 은행 대출 담당자 설문. 은행 신용 수축 → NBFI(사모) 전이 경로. 분기 업데이트.</span></div>
          <div class="back-metric"><span class="back-label">C&I 연체율</span><span class="back-value">기업 대출 연체율. 사모크레딧 기초 포트폴리오 신용 품질 프록시. 분기 업데이트.</span></div>
        </div>
        <div class="back-section">
          <h4>📌 위험 기준</h4>
          <div class="back-metric"><span class="back-label">BDC 할인 &lt; 5%</span><span class="back-value" style="color:#34d399">정상 — 시장이 사모 마크 신뢰</span></div>
          <div class="back-metric"><span class="back-label">BDC 할인 5 ~ 15%</span><span class="back-value" style="color:#fbbf24">주의 — 마크 불신 시작</span></div>
          <div class="back-metric"><span class="back-label">BDC 할인 15 ~ 25%</span><span class="back-value" style="color:#f97316">경고 — 환매 압력 심화</span></div>
          <div class="back-metric"><span class="back-label">BDC 할인 25% 이상</span><span class="back-value" style="color:#f87171">위험 — 2008·2020 위기 수준</span></div>
          <div class="back-metric"><span class="back-label">SLOOS 긴축 30% 이상</span><span class="back-value" style="color:#f97316">경고 — 은행→NBFI 전이 위험</span></div>
        </div>
        <div class="back-section">
          <h4>🔢 점수 산출</h4>
          <div class="back-formula">
            <p>BDC 할인율 <strong>25%</strong> + SLOOS 긴축 <strong>25%</strong> + C&I 연체율 <strong>15%</strong> + HY 수준 <strong>20%</strong> + HY 변화 <strong>15%</strong></p>
          </div>
        </div>
        <div class="back-section">
          <h4>📋 추가 모니터링 권장</h4>
          <div class="back-metric"><span class="back-label">인터벌 펀드 환매 충족률</span><span class="back-value">분기 환매 요청이 한도 초과 시 비례배분(게이팅 직접 증거)</span></div>
          <div class="back-metric"><span class="back-label">PIK 이자 비중</span><span class="back-value">현금 대신 추가 부채로 이자 지급 — 부실 은폐 신호</span></div>
          <div class="back-metric"><span class="back-label">CLO BB 트랜치 스프레드</span><span class="back-value">레버리지론 시장 — 사모크레딧과 가장 인접한 공개시장</span></div>
        </div>
      </div>`;
  }

  /* ────────── W4 뒷면 ────────── */
  if (prefix === "w4") {
    return `
      <div class="back-content">
        <div class="back-section">
          <h4>📐 수치 해설</h4>
          <div class="back-metric"><span class="back-label">포함 기준</span><span class="back-value">2026-05-01 이후 액션 + 기업가치 $50B 이상</span></div>
          <div class="back-metric"><span class="back-label">가중 파이프라인</span><span class="back-value">기업가치 × 상태가중치 합산 (실제 흡수 위험 반영)</span></div>
          <div class="back-metric"><span class="back-label">시총 대비 비율</span><span class="back-value">가중 파이프라인 ÷ 미국 시총($69조) × 100</span></div>
        </div>
        <div class="back-section">
          <h4>⚖️ 상태별 가중치</h4>
          <div class="back-metric"><span class="back-label">가격확정</span><span class="back-value" style="color:#f87171">100% — 상장 임박, 즉각적 유동성 흡수</span></div>
          <div class="back-metric"><span class="back-label">제출완료</span><span class="back-value" style="color:#f97316">70% — S-1 제출, 수개월 내 상장 예정</span></div>
          <div class="back-metric"><span class="back-label">검토중</span><span class="back-value" style="color:#fbbf24">10% — 불확실성 높음, 1년 이상 소요 가능</span></div>
          <div class="back-metric"><span class="back-label">루머·상장완료</span><span class="back-value" style="color:#64748b">0% — 점수 제외</span></div>
        </div>
        <div class="back-section">
          <h4>📌 위험 기준 (역사적 근거)</h4>
          <div class="back-metric"><span class="back-label">&lt; 0.15%</span><span class="back-value" style="color:#34d399">정상 — 2010~16년 회복기 수준</span></div>
          <div class="back-metric"><span class="back-label">0.15 ~ 0.25%</span><span class="back-value" style="color:#fbbf24">주의 — 2021년 SPAC 붐 수준</span></div>
          <div class="back-metric"><span class="back-label">0.25 ~ 0.45%</span><span class="back-value" style="color:#f97316">경고 — 1999~2000년 닷컴버블 수준</span></div>
          <div class="back-metric"><span class="back-label">0.45% 이상</span><span class="back-value" style="color:#f87171">위험 — 닷컴버블 초과, 전례 없는 수준</span></div>
        </div>
        <div class="back-section">
          <h4>🔢 점수 산출</h4>
          <div class="back-formula">
            <p>기본 점수: 비율 구간별 (10 / 30 / 50 / 75점)</p>
            <code>가격확정 × 10점 + 제출완료 × 5점 (최대 보너스 20점)</code>
            <p>최종 = 기본 점수 + 보너스 (최대 100점)</p>
          </div>
        </div>
      </div>`;
  }

  return "";
}

/* ── 점수 배지 업데이트 ──────────────────────────────────── */
function updateScoreBadge(prefix, score) {
  // Fix15: HTML ID는 score-w1 형식 (score-badge-w1 아님)
  const badge = document.getElementById(`score-${prefix}`);
  if (!badge) return;
  const label = scoreLabel(score);
  const cls   = scoreGradeClass(score);
  badge.textContent = `${score}점 ${label}`;
  badge.className   = `card-score-badge ${cls}`;
}

/* ── 경고 바 렌더 ────────────────────────────────────────── */
function renderWarningBars(scores) {
  const container = document.getElementById("warning-bars");
  if (!container) return;
  const items = [
    { key: "w1", label: "선도주" },
    { key: "w2", label: "채권" },
    { key: "w3", label: "신용" },
    { key: "w4", label: "IPO" },
  ];
  container.innerHTML = items.map(({ key, label }) => {
    const s   = scores[key]?.score ?? 0;
    const col = scoreColor(s);
    return `
      <div class="warning-bar-item">
        <span class="warning-bar-label">${label}</span>
        <div class="warning-bar-track">
          <div class="warning-bar-fill" style="width:${s}%;background:${col}"></div>
        </div>
        <span class="warning-bar-val" style="color:${col}">${s}</span>
      </div>`;
  }).join("");
}

/* ── 복합 점수 카드 렌더 ─────────────────────────────────── */
function renderComposite(data) {
  const comp  = data.composite_score ?? 0;
  const grade = data.grade ?? "GREEN";

  // 점수 링
  drawScoreRing("composite-ring", comp);

  // 숫자
  const numEl = document.getElementById("composite-number");
  if (numEl) {
    numEl.textContent = comp.toFixed(1);
    numEl.style.color = scoreColor(comp);
  }

  // 카드 등급 테두리
  const cardEl = document.getElementById("composite-card");
  if (cardEl) {
    cardEl.className = `composite-card grade-${grade}`;
  }

  // 전체 레이블
  const labelEl = document.getElementById("overall-label");
  if (labelEl) {
    const labels = {
      RED:    "🚨 위험 — 복합 위기 신호 감지",
      YELLOW: "⚠️ 경계 — 주요 지표 이상 감지",
      GREEN:  "✅ 안정 — 전반적 시장 위험 낮음",
    };
    labelEl.textContent = labels[grade] ?? "—";
    labelEl.style.color = scoreColor(comp);
  }

  // 행동 권고
  const recEl = document.getElementById("action-rec");
  if (recEl) {
    if      (comp >= 70) recEl.textContent = "즉각적 포트폴리오 점검 필요. 위험자산 비중 축소 및 헤지 포지션 구축을 권장합니다.";
    else if (comp >= 40) recEl.textContent = "주요 지표 모니터링 강화 필요. 신규 위험자산 진입 시 신중한 접근이 요구됩니다.";
    else                 recEl.textContent = "전반적으로 안정적인 시장 환경입니다. 기존 전략을 유지하되 지표 변화를 주시하세요.";
  }

  // 알고 신호 배지
  const sigBadge = document.getElementById("algo-signal-badge");
  const sigDesc  = document.getElementById("algo-signal-desc");
  if (sigBadge && sigDesc) {
    if      (comp >= 70) { sigBadge.textContent = "RISK ON";  sigBadge.style.background = "#ef4444"; sigDesc.textContent = "위험 경보 발령 — 방어적 포지션 전환"; }
    else if (comp >= 40) { sigBadge.textContent = "CAUTION";  sigBadge.style.background = "#f59e0b"; sigDesc.textContent = "경계 모드 — 선별적 포지션 관리"; }
    else                 { sigBadge.textContent = "SAFE";     sigBadge.style.background = "#10b981"; sigDesc.textContent = "안전 모드 — 정상적 시장 환경"; }
  }

  // 헤지 권고
  const hedgeEl = document.getElementById("hedge-rec");
  if (hedgeEl) {
    if      (comp >= 70) hedgeEl.textContent = "💼 헤지 권고: 금·달러·단기국채 비중 확대 / VIX 콜옵션 매수 고려";
    else if (comp >= 40) hedgeEl.textContent = "💼 부분 헤지: 포트폴리오의 10~20%를 방어 자산으로 전환 고려";
    else                 hedgeEl.textContent = "💼 헤지 불필요: 현재 시장 환경에서는 공격적 헤지 불필요";
  }

  // 퍼펙트스톰 배너
  const stormEl = document.getElementById("storm-section");
  if (stormEl) stormEl.style.display = comp >= 80 ? "block" : "none";

  // 경고 바
  const scores = {
    w1: data.w1, w2: data.w2, w3: data.w3, w4: data.w4,
  };
  renderWarningBars(scores);
}

/* ── 개별 카드 렌더 ──────────────────────────────────────── */
function renderCard(prefix, scoreObj, rawObj) {
  const score = scoreObj?.score ?? 0;

  // 미니바
  drawMiniBar(`bar-${prefix}`, score);

  // 점수 배지
  updateScoreBadge(prefix, score);

  // 앞면
  // Fix15: HTML ID는 front-body-w1 형식
  const frontEl = document.getElementById(`front-body-${prefix}`);
  if (frontEl) frontEl.innerHTML = buildFrontContent(prefix, score, rawObj);

  // 뒷면
  // Fix15: HTML ID는 back-body-w1 형식
  const backEl = document.getElementById(`back-body-${prefix}`);
  if (backEl) backEl.innerHTML = buildBackContent(prefix, score, rawObj);
}

/* ── 히스토리 차트 ───────────────────────────────────────── */
async function renderHistoryChart() {
  try {
    const res  = await fetch(HISTORY_URL);
    const text = await res.text();
    const rows = text.trim().split("\n").map(l => {
      try { return JSON.parse(l); } catch { return null; }
    }).filter(Boolean);

    const recent = rows.slice(-30);
    const labels = recent.map(r => r.date?.slice(5) ?? "");
    const data   = recent.map(r => r.composite_score ?? r.score ?? 0);

    const canvas = document.getElementById("history-chart");
    if (!canvas) return;

    if (window._histChart) window._histChart.destroy();
    window._histChart = new Chart(canvas.getContext("2d"), {
      type: "line",
      data: {
        labels,
        datasets: [{
          label: "종합위험점수",
          data,
          borderColor: "#38bdf8",
          backgroundColor: "rgba(56,189,248,0.08)",
          borderWidth: 2,
          pointRadius: 3,
          pointBackgroundColor: data.map(v => scoreColor(v)),
          tension: 0.3,
          fill: true,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: {
            ticks: { color: "#64748b", font: { size: 10 } },
            grid:  { color: "#1e3a5f55" },
          },
          y: {
            min: 0, max: 100,
            ticks: { color: "#64748b", font: { size: 10 } },
            grid:  { color: "#1e3a5f55" },
          },
        },
      },
    });
  } catch (e) {
    console.warn("히스토리 차트 로드 실패:", e);
  }
}

/* ── 타임스탬프 표시 (Fix14: 24시간제) ──────────────────── */
function renderTimestamp(ts) {
  const tsEl = document.getElementById("last-updated");
  if (!tsEl) return;
  try {
    const d = new Date(ts);
    tsEl.textContent = `Last updated: ${d.toLocaleString("ko-KR", {
      timeZone: "Asia/Seoul",
      hour12: false,
    })} KST`;
  } catch {
    tsEl.textContent = `Last updated: ${ts}`;
  }
}

/* ── 폴백 데이터 ─────────────────────────────────────────── */
const FALLBACK_DATA = {
  composite_score: 45,
  grade: "YELLOW",
  timestamp: new Date().toISOString(),
  w1: { score: 20, spy_ytd: 5.0, rsp_ytd: 3.5, current_spread: 1.5, spread_percentile: 40, rsp_1w_return: 0.8, rsp_is_negative_while_spy_positive: false },
  w2: { score: 35, us10y_yield: 4.3, us2y_yield: 4.1, term_spread: 0.2, tips_10y_real_yield: 1.8, is_inverted: false, rate_hike_concern: false },
  w3: { score: 15, bdc_nav_discount: 3.5, bdc_nav_date: "2026-05-30", sloos_ci_pct: 14.5, ci_delq_pct: 1.55, hy_bps: 272, ig_bps: 74, hy_change_bps: -10 },
  w4: {
    score: 90, grade: "위험", color: "red",
    total_valuation_bn: 2506.3,
    pipeline_ratio_pct: 3.6323,
    us_market_cap_bn: 69000,
    filed_count: 1,
    priced_count: 1,
    alerts: ["🚨 파이프라인 비율 3.63% — 닷컴버블(0.45%) 초과, 전례 없는 수준"],
    ipo_list: [
      { company: "SpaceX",    valuation_bn: 1800, status: "가격확정", filed_date: "2026-05-20" },
      { company: "OpenAI",    valuation_bn: 852,  status: "제출완료", filed_date: "2026-05-20" },
      { company: "Anthropic", valuation_bn: 965,  status: "검토중",   active_date: "2026-05-28" },
      { company: "Databricks",valuation_bn: 134,  status: "검토중",   active_date: "2026-05-01" },
    ],
  },
};

/* ── 메인 초기화 ─────────────────────────────────────────── */
async function init() {
  let data = null;

  try {
    const res = await fetch(DATA_URL);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    data = await res.json();
  } catch (e) {
    console.warn("데이터 로드 실패, 폴백 사용:", e);
    data = FALLBACK_DATA;
  }

  // 타임스탬프
  renderTimestamp(data.timestamp ?? new Date().toISOString());

  // 복합 점수
  renderComposite(data);

  // 개별 카드 4장
  ["w1", "w2", "w3", "w4"].forEach(prefix => {
    renderCard(prefix, data[prefix], data[prefix]);
  });

  // 히스토리 차트
  await renderHistoryChart();

  // 카드 높이 균등화
  setTimeout(equalizeCardHeights, 100);
}

document.addEventListener("DOMContentLoaded", init);
