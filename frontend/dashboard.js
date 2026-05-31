// ============================================================
// dashboard.js  –  대시보드 렌더링 (index.html 구조 기준)
// ============================================================
"use strict";

const DATA_URL    = "./data/latest_scores.json";
const HISTORY_URL = "./data/history.jsonl";

const WEIGHTS = { w1: 0.25, w2: 0.30, w3: 0.20, w4: 0.25 };

const STATUS_WEIGHT = {
  "루머": 0.1, "검토중": 0.3, "신청완료": 1.0, "가격확정": 1.0, "상장완료": 0.0,
};

const statusClassMap = {
  "신청완료": "Filed", "검토중": "Considering", "가격확정": "Priced",
  "상장완료": "Trading", "루머": "Rumor",
};

// ── 유틸 ──────────────────────────────────────────────────
function scoreColor(s) {
  if (s >= 70) return "#ef4444";
  if (s >= 40) return "#f59e0b";
  return "#10b981";
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

// ── 카드 높이 균일화 ──────────────────────────────────────
function equalizeCardHeights() {
  const wrappers = document.querySelectorAll(".card-flip-wrapper");
  // 높이 초기화
  wrappers.forEach(w => {
    w.style.height = "auto";
    const front = w.querySelector(".card-front");
    const inner = w.querySelector(".card-flip-inner");
    if (front) front.style.minHeight = "auto";
    if (inner) inner.style.height    = "auto";
  });

  requestAnimationFrame(() => {
    let maxH = 0;
    wrappers.forEach(w => {
      const front = w.querySelector(".card-front");
      if (front) maxH = Math.max(maxH, front.scrollHeight);
    });
    if (maxH < 10) return;
    wrappers.forEach(w => {
      w.style.height = maxH + "px";
      const inner = w.querySelector(".card-flip-inner");
      const front = w.querySelector(".card-front");
      if (inner) inner.style.height = maxH + "px";
      if (front) front.style.minHeight = maxH + "px";
    });
  });
}

window.addEventListener("resize", () => {
  clearTimeout(window._eqTimer);
  window._eqTimer = setTimeout(equalizeCardHeights, 150);
});

// ── 카드 뒤집기 ───────────────────────────────────────────
function toggleFlip(prefix) {
  const wrapper = document.getElementById(`flip-${prefix}`);
  if (wrapper) wrapper.classList.toggle("flipped");
}

// ── 종합 점수 링 차트 ─────────────────────────────────────
function drawScoreRing(score) {
  const canvas = document.getElementById("score-ring");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const cx = canvas.width / 2, cy = canvas.height / 2, r = 65;
  const start = -Math.PI / 2;
  const end   = start + (score / 100) * 2 * Math.PI;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, 2 * Math.PI);
  ctx.strokeStyle = "rgba(255,255,255,0.1)";
  ctx.lineWidth = 12; ctx.stroke();
  ctx.beginPath();
  ctx.arc(cx, cy, r, start, end);
  ctx.strokeStyle = scoreColor(score);
  ctx.lineWidth = 12; ctx.lineCap = "round"; ctx.stroke();
}

// ── 미니바 (requestAnimationFrame으로 타이밍 보정) ────────
function drawMiniBar(prefix, score) {
  requestAnimationFrame(() => {
    const canvas = document.getElementById(`chart-${prefix}`);
    if (!canvas) return;
    const parent = canvas.parentElement;
    const w = (parent ? parent.offsetWidth : 0) || 240;
    canvas.width = w; canvas.height = 8;
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, w, 8);
    ctx.fillStyle = "rgba(255,255,255,0.08)";
    ctx.roundRect(0, 0, w, 8, 4); ctx.fill();
    ctx.fillStyle = scoreColor(score);
    ctx.roundRect(0, 0, w * (score / 100), 8, 4); ctx.fill();
  });
}

// ── IPO 테이블 ────────────────────────────────────────────
function renderIPOTable(ipoList) {
  if (!ipoList || ipoList.length === 0)
    return `<p style="color:#64748b;font-size:12px;padding:0.5rem 0">IPO 데이터 없음</p>`;
  const rows = ipoList.map(item => {
    const css       = statusClassMap[item.status] ?? "Rumor";
    const val       = item.valuation_bn ? `$${Number(item.valuation_bn).toLocaleString()}B` : "–";
    const wt        = (STATUS_WEIGHT[item.status] ?? 0.1) * 100;
    const wtVal     = item.valuation_bn
      ? `$${Math.round(item.valuation_bn * (STATUS_WEIGHT[item.status] ?? 0.1)).toLocaleString()}B`
      : "–";
    return `<tr>
      <td>${item.company}</td><td>${val}</td>
      <td><span class="status-badge status-${css}">${item.status}</span></td>
      <td>${wt}%</td><td>${wtVal}</td>
    </tr>`;
  }).join("");
  return `<table class="ipo-table">
    <thead><tr><th>기업</th><th>기업가치</th><th>상태</th><th>가중치</th><th>반영액</th></tr></thead>
    <tbody>${rows}</tbody>
  </table>`;
}

// ── 카드 뒷면 해설 (풍부한 버전) ─────────────────────────
function buildBackContent(prefix, raw) {
  if (prefix === "w1") {
    const spy   = (raw.spy_ytd ?? 0).toFixed(2);
    const rsp   = (raw.rsp_ytd ?? 0).toFixed(2);
    const diff  = ((raw.spy_ytd ?? 0) - (raw.rsp_ytd ?? 0)).toFixed(2);
    const pct   = raw.spread_percentile ?? "N/A";
    const rsp1w = raw.rsp_1w_return != null ? Number(raw.rsp_1w_return).toFixed(2) : null;
    const isNeg = raw.rsp_is_negative_while_spy_positive ?? false;
    const diffF = parseFloat(diff);
    let situationClass = "GREEN", situationMsg = "";
    if (isNeg) {
      situationClass = "RED";
      situationMsg = `🔴 <strong>위험 트리거 발동</strong> — SPY 상승 중 RSP가 마이너스로, 소형·가치주가 매도되고 있습니다. 시장 참여자들이 대형 성장주로만 몰리는 극단적 쏠림입니다.`;
    } else if (diffF >= 6) {
      situationClass = "ORANGE";
      situationMsg = `⚠️ <strong>주의 구간</strong> — 괴리율 ${diff}%p는 역사적 상위 ${100 - pct}% 수준입니다. 소수 대형주가 지수를 끌어올리고 있어 조정 시 낙폭이 클 수 있습니다.`;
    } else if (diffF >= 2) {
      situationClass = "YELLOW";
      situationMsg = `🟡 <strong>관찰 구간</strong> — 괴리율 ${diff}%p, 대형주 집중 현상이 나타나고 있으나 아직 위험 수위는 아닙니다.`;
    } else {
      situationClass = "GREEN";
      situationMsg = `✅ <strong>정상 구간</strong> — SPY와 RSP가 균형 있게 상승 중. 시장 내 폭넓은 참여가 이루어지고 있습니다.`;
    }
    return `
      <div class="back-section">
        <div class="back-section-title">📊 수치 해설</div>
        <div class="back-metric"><span class="back-label">SPY YTD 수익률</span><span class="back-value val-green">+${spy}%</span></div>
        <div class="back-metric"><span class="back-label">RSP YTD 수익률</span><span class="back-value val-green">+${rsp}%</span></div>
        <div class="back-metric"><span class="back-label">SPY–RSP 괴리율</span><span class="back-value ${diffF >= 4 ? "val-red" : diffF >= 2 ? "val-yellow" : "val-green"}">+${diff}%p</span></div>
        <div class="back-metric"><span class="back-label">괴리 역사적 퍼센타일</span><span class="back-value">${pct}%ile</span></div>
        ${rsp1w !== null ? `<div class="back-metric"><span class="back-label">RSP 최근 1주 수익률</span><span class="back-value ${parseFloat(rsp1w) < 0 ? "val-red" : "val-green"}">${parseFloat(rsp1w) >= 0 ? "+" : ""}${rsp1w}%</span></div>` : ""}
      </div>
      <div class="back-section">
        <div class="back-section-title">🔍 현재 상황 진단</div>
        <div class="back-situation ${situationClass}">${situationMsg}</div>
      </div>
      <div class="back-section">
        <div class="back-section-title">📖 지표 의미</div>
        <p class="back-desc">SPY는 시가총액 가중 ETF로 상위 10개 종목이 35% 이상을 차지합니다. RSP는 동일 500종목을 0.2%씩 균등 배분합니다. 두 지수 괴리가 커질수록 소수 대형 기술주만 시장을 견인하는 <strong>'좁은 시장(Narrow Market)'</strong> 상태입니다. 과거 2000년 닷컴 버블, 2021년 말 고점에서 유사 패턴이 나타났습니다.</p>
      </div>
      <div class="back-advice">💡 <strong>투자 시사점:</strong> RSP가 마이너스 전환 시 포지션 10~20% 축소. 괴리 6%p 이상 지속 시 대형 기술주 비중 점검 권고.</div>`;
  }

  if (prefix === "w2") {
    const y10   = (raw.us10y_yield ?? 0).toFixed(2);
    const y2    = (raw.us2y_yield  ?? 0).toFixed(2);
    const spd   = (raw.term_spread ?? 0).toFixed(2);
    const tips  = (raw.tips_10y_real_yield ?? 0).toFixed(2);
    const isInv = (raw.term_spread ?? 0) < 0;
    const y10F  = parseFloat(y10);
    let situationClass = "GREEN", situationMsg = "";
    if (isInv && y10F >= 4.5) {
      situationClass = "RED";
      situationMsg = `🔴 <strong>복합 위험</strong> — 10년물 ${y10}%로 임계선 돌파 + 장단기 금리 역전 동시 발생. 경기침체 선행 신호가 켜진 상태입니다.`;
    } else if (y10F >= 4.5) {
      situationClass = "ORANGE";
      situationMsg = `⚠️ <strong>금리 경계 구간</strong> — 10년물 ${y10}%로 4.5% 임계선을 돌파했습니다. 주식 밸류에이션 압박과 레버리지 비용 증가가 시작됩니다.`;
    } else if (isInv) {
      situationClass = "YELLOW";
      situationMsg = `🟡 <strong>장단기 역전 주의</strong> — 금리 역전은 은행 마진 축소와 신용 수축을 유발합니다. 과거 역전 후 평균 12~18개월 뒤 침체 발생.`;
    } else {
      situationClass = "GREEN";
      situationMsg = `✅ <strong>금리 정상 구간</strong> — 10년물 ${y10}%, 장단기 스프레드 +${spd}%p 유지. 금리발 리스크는 현재 낮은 수준입니다.`;
    }
    return `
      <div class="back-section">
        <div class="back-section-title">📊 수치 해설</div>
        <div class="back-metric"><span class="back-label">미국 10년물 국채</span><span class="back-value ${y10F >= 4.5 ? "val-red" : y10F >= 4.0 ? "val-yellow" : "val-green"}">${y10}%</span></div>
        <div class="back-metric"><span class="back-label">미국 2년물 국채</span><span class="back-value">${y2}%</span></div>
        <div class="back-metric"><span class="back-label">장단기 스프레드(10Y-2Y)</span><span class="back-value ${isInv ? "val-red" : "val-green"}">${parseFloat(spd) >= 0 ? "+" : ""}${spd}%p</span></div>
        <div class="back-metric"><span class="back-label">TIPS 10년 실질금리</span><span class="back-value ${parseFloat(tips) >= 2.5 ? "val-red" : parseFloat(tips) >= 2.0 ? "val-yellow" : ""}">${tips}%</span></div>
        <div class="back-metric"><span class="back-label">장단기 역전 여부</span><span class="back-value ${isInv ? "val-red" : "val-green"}">${isInv ? "⚠️ 역전 중" : "✅ 정상"}</span></div>
      </div>
      <div class="back-section">
        <div class="back-section-title">🔍 현재 상황 진단</div>
        <div class="back-situation ${situationClass}">${situationMsg}</div>
      </div>
      <div class="back-section">
        <div class="back-section-title">📖 지표 의미</div>
        <p class="back-desc"><strong>채권 자경단(Bond Vigilantes)</strong>은 재정 정책이 과도하다고 판단하면 국채를 매도해 금리를 강제로 올리는 시장 참여자들입니다. 10년물 4.5% 돌파는 모기지·기업 대출 비용을 직접 올려 실물 경제를 억압합니다. TIPS 실질금리 2% 이상은 주식 리스크 프리미엄을 잠식합니다.</p>
      </div>
      <div class="back-advice">💡 <strong>투자 시사점:</strong> 10년물 4.5% 이상 시 성장주·기술주 비중 축소. 역전 지속 시 경기방어주(유틸리티·헬스케어) 비중 확대 고려.</div>`;
  }

  if (prefix === "w3") {
    const hy    = (raw.hy_bps ?? 0).toFixed(0);
    const ig    = (raw.ig_bps ?? 0).toFixed(0);
    const hyChg = (raw.hy_change_bps ?? 0).toFixed(0);
    const hyF   = parseInt(hy);
    const chgF  = parseFloat(hyChg);
    let situationClass = "GREEN", situationMsg = "";
    if (hyF >= 400) {
      situationClass = "RED";
      situationMsg = `🔴 <strong>신용 위기 경계</strong> — HY 스프레드 ${hy}bps로 위험 구간 진입. 고수익 채권 발행사들의 디폴트 우려가 확대되고 있습니다.`;
    } else if (hyF >= 300) {
      situationClass = "ORANGE";
      situationMsg = `⚠️ <strong>신용 경고 구간</strong> — HY 스프레드 ${hy}bps. 투자자들이 위험 회피에 나서고 있으며 레버리지 기업 자금 조달 비용이 상승 중입니다.`;
    } else if (chgF >= 20) {
      situationClass = "YELLOW";
      situationMsg = `🟡 <strong>스프레드 확대 주의</strong> — 절대 수준은 낮으나 최근 1개월간 ${hyChg}bps 확대. 방향성 변화에 주목이 필요합니다.`;
    } else {
      situationClass = "GREEN";
      situationMsg = `✅ <strong>신용 시장 안정</strong> — HY 스프레드 ${hy}bps는 역사적 저점 수준. 신용 시장이 위험을 거의 반영하지 않는 상태입니다. 역설적으로 향후 확대 가능성에 유의하세요.`;
    }
    return `
      <div class="back-section">
        <div class="back-section-title">📊 수치 해설</div>
        <div class="back-metric"><span class="back-label">HY 스프레드 (OAS)</span><span class="back-value ${hyF >= 400 ? "val-red" : hyF >= 300 ? "val-yellow" : "val-green"}">${hy} bps</span></div>
        <div class="back-metric"><span class="back-label">IG 스프레드 (OAS)</span><span class="back-value">${ig} bps</span></div>
        <div class="back-metric"><span class="back-label">HY 1개월 변화량</span><span class="back-value ${chgF >= 20 ? "val-red" : chgF >= 0 ? "val-yellow" : "val-green"}">${chgF >= 0 ? "+" : ""}${hyChg} bps</span></div>
        <div class="back-metric"><span class="back-label">HY 위험 임계선</span><span class="back-value val-yellow">400 bps</span></div>
      </div>
      <div class="back-section">
        <div class="back-section-title">🔍 현재 상황 진단</div>
        <div class="back-situation ${situationClass}">${situationMsg}</div>
      </div>
      <div class="back-section">
        <div class="back-section-title">📖 지표 의미</div>
        <p class="back-desc"><strong>OAS(Option-Adjusted Spread)</strong>는 국채 대비 회사채 초과 수익률로, 투자자가 신용 위험에 대해 요구하는 보상입니다. HY(고수익/정크본드)는 BB등급 이하 기업 채권으로 경기 민감도가 높습니다. 스프레드 급등은 신용 시장 경색, 기업 유동성 위기의 선행 신호입니다.</p>
      </div>
      <div class="back-advice">💡 <strong>투자 시사점:</strong> HY 400bps 돌파 시 하이일드 ETF(HYG·JNK) 매도 및 국채 비중 확대. 스프레드 확대 추세 시 소형주·사이클 주식 축소 고려.</div>`;
  }

  if (prefix === "w4") {
    const totalBn = (raw.total_valuation_bn ?? 0).toLocaleString();
    const filed   = raw.filed_count  ?? 0;
    const priced  = raw.priced_count ?? 0;
    const totalF  = raw.total_valuation_bn ?? 0;
    let situationClass = "GREEN", situationMsg = "";
    if (totalF >= 3000) {
      situationClass = "RED";
      situationMsg = `🔴 <strong>역대 최대 파이프라인</strong> — 가중 반영액 $${totalBn}B는 역사상 전례 없는 수준입니다. IPO 청약에 수조 달러의 유동성이 묶일 수 있습니다.`;
    } else if (totalF >= 2000) {
      situationClass = "ORANGE";
      situationMsg = `⚠️ <strong>매우 높은 파이프라인</strong> — 가중 반영액 $${totalBn}B. 대규모 유동성 흡수가 예상되며 시장 변동성이 높아질 수 있습니다.`;
    } else if (totalF >= 1000) {
      situationClass = "YELLOW";
      situationMsg = `🟡 <strong>주의 구간</strong> — 가중 반영액 $${totalBn}B. IPO 시즌 진입으로 유동성 분산 가능성이 있습니다.`;
    } else {
      situationClass = "GREEN";
      situationMsg = `✅ <strong>정상 파이프라인</strong> — 현재 IPO 규모가 시장에 미치는 유동성 영향은 제한적입니다.`;
    }
    return `
      <div class="back-section">
        <div class="back-section-title">📊 수치 해설</div>
        <div class="back-metric"><span class="back-label">가중 활성 파이프라인</span><span class="back-value val-red">$${totalBn}B</span></div>
        <div class="back-metric"><span class="back-label">S-1 신청 완료</span><span class="back-value">${filed}건</span></div>
        <div class="back-metric"><span class="back-label">공모가 확정</span><span class="back-value">${priced}건</span></div>
        <div class="back-metric"><span class="back-label">가중치 기준</span><span class="back-value" style="font-size:0.65rem">신청완료 100% / 검토중 30%</span></div>
      </div>
      <div class="back-section">
        <div class="back-section-title">🔍 현재 상황 진단</div>
        <div class="back-situation ${situationClass}">${situationMsg}</div>
      </div>
      <div class="back-section">
        <div class="back-section-title">📖 주요 파이프라인</div>
        <p class="back-desc">SpaceX($1,800B·신청완료), OpenAI($852B·검토중), Anthropic($965B·검토중) 등 AI·우주 섹터 초대형 IPO가 집중 대기 중입니다. 과거 2000년 닷컴 버블과 2021년 SPAC 붐 당시에도 대규모 IPO 집중 직후 시장 조정이 발생했습니다.</p>
      </div>
      <div class="back-advice">💡 <strong>투자 시사점:</strong> SpaceX IPO 전후 1~2주 변동성 확대 예상. IPO 청약 참여 시 기존 포지션 비중 점검 필요. 파이프라인 $3,000B 이상 시 현금 비중 10~15% 확보 권고.</div>`;
  }

  return `<p>데이터 없음</p>`;
}

// ── 지표 그리드 빌더 ──────────────────────────────────────
function buildMetrics(prefix, raw) {
  if (prefix === "w1") return `
    <div class="metric-item"><span class="metric-label">SPY YTD</span><span class="metric-value">+${(raw.spy_ytd ?? 0).toFixed(2)}%</span></div>
    <div class="metric-item"><span class="metric-label">RSP YTD</span><span class="metric-value">+${(raw.rsp_ytd ?? 0).toFixed(2)}%</span></div>
    <div class="metric-item"><span class="metric-label">괴리율</span><span class="metric-value">+${((raw.spy_ytd ?? 0) - (raw.rsp_ytd ?? 0)).toFixed(2)}%p</span></div>
    <div class="metric-item"><span class="metric-label">퍼센타일</span><span class="metric-value">${raw.spread_percentile ?? "N/A"}%ile</span></div>`;
  if (prefix === "w2") return `
    <div class="metric-item"><span class="metric-label">10년물</span><span class="metric-value">${(raw.us10y_yield ?? 0).toFixed(2)}%</span></div>
    <div class="metric-item"><span class="metric-label">2년물</span><span class="metric-value">${(raw.us2y_yield ?? 0).toFixed(2)}%</span></div>
    <div class="metric-item"><span class="metric-label">장단기차</span><span class="metric-value">${(raw.term_spread ?? 0) >= 0 ? "+" : ""}${(raw.term_spread ?? 0).toFixed(2)}%p</span></div>
    <div class="metric-item"><span class="metric-label">TIPS</span><span class="metric-value">${(raw.tips_10y_real_yield ?? 0).toFixed(2)}%</span></div>`;
  if (prefix === "w3") return `
    <div class="metric-item"><span class="metric-label">HY 스프레드</span><span class="metric-value">${(raw.hy_bps ?? 0).toFixed(0)} bps</span></div>
    <div class="metric-item"><span class="metric-label">IG 스프레드</span><span class="metric-value">${(raw.ig_bps ?? 0).toFixed(0)} bps</span></div>
    <div class="metric-item"><span class="metric-label">HY 변화</span><span class="metric-value">${(raw.hy_change_bps ?? 0) >= 0 ? "+" : ""}${(raw.hy_change_bps ?? 0).toFixed(0)} bps</span></div>`;
  if (prefix === "w4") return `
    <div class="metric-item"><span class="metric-label">파이프라인</span><span class="metric-value">$${(raw.total_valuation_bn ?? 0).toLocaleString()}B</span></div>
    <div class="metric-item"><span class="metric-label">S-1 신청</span><span class="metric-value">${raw.filed_count ?? 0}건</span></div>`;
  return "";
}

// ── 개별 카드 렌더링 ──────────────────────────────────────
function renderCard(prefix, score, raw, weightLabel) {
  const scoreBadge = document.getElementById(`score-${prefix}`);
  if (scoreBadge) {
    scoreBadge.textContent = score;
    scoreBadge.className   = `card-score-badge ${scoreGradeClass(score)}`;
  }
  const weightBadge = document.getElementById(`weight-${prefix}`);
  if (weightBadge) weightBadge.textContent = `가중치 ${weightLabel}`;

  drawMiniBar(prefix, score);

  const signalEl = document.getElementById(`signals-${prefix}`);
  if (signalEl) {
    const signals = raw.signals ?? [];
    const alerts  = raw.alerts  ?? [];
    const allMsgs = [...alerts, ...signals];
    signalEl.innerHTML = allMsgs.length
      ? allMsgs.map(s => {
          let cls = "DEFAULT";
          if (s.startsWith("🚨")) cls = "RED";
          else if (s.startsWith("⚠️")) cls = "ORANGE";
          else if (s.startsWith("📢") || s.startsWith("🔍") || s.startsWith("📋") || s.startsWith("💰")) cls = "YELLOW";
          else if (s.startsWith("✅")) cls = "GREEN";
          return `<div class="signal-item ${cls}">${s}</div>`;
        }).join("")
      : "";
  }

  const metricsEl = document.getElementById(`metrics-${prefix}`);
  if (metricsEl) metricsEl.innerHTML = buildMetrics(prefix, raw);

  if (prefix === "w4") {
    const tableEl = document.getElementById("ipo-table");
    if (tableEl) tableEl.innerHTML = renderIPOTable(raw.ipo_list ?? []);
  }

  const backEl = document.getElementById(`back-${prefix}`);
  if (backEl) {
    backEl.innerHTML = `
      <div class="back-content">
        <div class="back-top-bar">
          <span class="back-top-title">📋 상세 해설 — ${
            prefix === "w1" ? "주도주 압축" :
            prefix === "w2" ? "채권 자경단 & 금리" :
            prefix === "w3" ? "사모 크레딧 환매" : "대어급 IPO 유동성"
          }</span>
          <button class="flip-btn" onclick="event.stopPropagation(); toggleFlip('${prefix}')">◀ 돌아가기</button>
        </div>
        ${buildBackContent(prefix, raw)}
      </div>`;
  }
}

// ── 종합 카드 렌더링 ──────────────────────────────────────
function renderComposite(data) {
  const c = data.composite_score ?? 0;

  const scoreEl = document.getElementById("composite-score");
  if (scoreEl) scoreEl.textContent = c;
  drawScoreRing(c);

  const labelEl = document.getElementById("overall-label");
  if (labelEl) { labelEl.textContent = scoreLabel(c); labelEl.style.color = scoreColor(c); }

  const actionEl = document.getElementById("action-rec");
  if (actionEl) {
    if (c >= 70)      actionEl.textContent = "⚠️ 즉시 포지션 점검 필요";
    else if (c >= 40) actionEl.textContent = "🔍 주의 깊게 모니터링 하세요";
    else              actionEl.textContent = "✅ 현재 시장 위험도 낮음";
  }

  const badgeEl = document.getElementById("signal-badge");
  const descEl  = document.getElementById("signal-desc");
  if (badgeEl && descEl) {
    if (c >= 70) {
      badgeEl.textContent = "SELL"; badgeEl.style.background = "#ef4444";
      descEl.textContent  = "위험 구간 — 현금 비중 확대 고려";
    } else if (c >= 40) {
      badgeEl.textContent = "HOLD"; badgeEl.style.background = "#f59e0b";
      descEl.textContent  = "주의 구간 — 신규 매수 자제";
    } else {
      badgeEl.textContent = "BUY";  badgeEl.style.background = "#10b981";
      descEl.textContent  = "안전 구간 — 정상적 투자 가능";
    }
  }

  const hedgeEl = document.getElementById("hedge-rec");
  if (hedgeEl) {
    if (c >= 70)
      hedgeEl.innerHTML = `<span style="color:#ef4444">🛡️ 헤지 권고: 인버스 ETF 또는 현금 비중 30% 이상 유지</span>`;
    else if (c >= 40)
      hedgeEl.innerHTML = `<span style="color:#f59e0b">🛡️ 헤지 고려: 포트폴리오 리밸런싱 검토</span>`;
    else
      hedgeEl.innerHTML = `<span style="color:#10b981">🛡️ 헤지 불필요: 정상 시장 환경</span>`;
  }

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
      return `<div class="warning-bar-item">
        <span class="warning-bar-label">${label}</span>
        <div class="warning-bar-track">
          <div class="warning-bar-fill" style="width:${s}%;background:${scoreColor(s)}"></div>
        </div>
        <span class="warning-bar-val" style="color:${scoreColor(s)}">${s}점</span>
      </div>`;
    }).join("");
  }

  const stormEl = document.getElementById("storm-section");
  if (stormEl) stormEl.style.display = c >= 70 ? "block" : "none";

  const updatedEl = document.getElementById("last-updated");
  if (updatedEl && data.timestamp) {
    updatedEl.textContent = `데이터 기준: ${new Date(data.timestamp).toLocaleString("ko-KR", { timeZone: "Asia/Seoul" })}`;
  }
}

// ── 히스토리 로드 ─────────────────────────────────────────
async function loadHistory() {
  try {
    const res  = await fetch(HISTORY_URL);
    const text = await res.text();
    const scores = text.trim().split("\n").filter(Boolean).map(line => {
      try {
        const o = JSON.parse(line);
        return { score: o.composite_score ?? o.score ?? o.perfect_storm_score ?? 0,
                 date:  o.date ?? o.timestamp?.slice(0, 10) ?? "" };
      } catch { return null; }
    }).filter(Boolean);
    if (typeof drawHistoryChart === "function") drawHistoryChart(scores);
  } catch (e) {
    console.warn("[History] 로드 실패:", e);
    if (typeof drawHistoryChart === "function") {
      drawHistoryChart([
        { date: "2026-05-01", score: 38 }, { date: "2026-05-05", score: 42 },
        { date: "2026-05-13", score: 45 }, { date: "2026-05-21", score: 40 },
        { date: "2026-05-29", score: 35 },
      ]);
    }
  }
}

// ── 메인 진입점 ───────────────────────────────────────────
async function loadData() {
  try {
    const res = await fetch(DATA_URL);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    renderComposite(data);

    [
      { prefix: "w1", weight: "25%", raw: data.w1 ?? {} },
      { prefix: "w2", weight: "30%", raw: data.w2 ?? {} },
      { prefix: "w3", weight: "20%", raw: data.w3 ?? {} },
      { prefix: "w4", weight: "25%", raw: data.w4 ?? {} },
    ].forEach(({ prefix, weight, raw }) => {
      renderCard(prefix, data[`${prefix}_score`] ?? 0, raw, weight);
    });

    await loadHistory();

    // 카드 높이 균일화 — 렌더 완료 후 실행
    setTimeout(equalizeCardHeights, 100);
    setTimeout(equalizeCardHeights, 500); // 폰트 로딩 완료 후 재실행
  } catch (e) {
    console.error("[loadData] 실패:", e);
    const updatedEl = document.getElementById("last-updated");
    if (updatedEl) updatedEl.textContent = `⚠️ 데이터 로드 실패: ${e.message}`;
    const labelEl = document.getElementById("overall-label");
    if (labelEl) labelEl.textContent = "데이터를 불러올 수 없습니다.";
  }
}

document.addEventListener("DOMContentLoaded", loadData);
