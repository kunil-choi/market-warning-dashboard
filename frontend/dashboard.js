// ============================================================
// dashboard.js  –  대시보드 렌더링 및 인터랙션
// 수정사항:
//   Bug Fix 3 – loadHistory() 완료 후 equalizeCardHeights() 재호출
//   + Anthropic $900B 반영된 카드 뒷면 해설 업데이트
//   + statusClassMap 한글→CSS 클래스 매핑 유지
// ============================================================

"use strict";

// ── 데이터 URL ────────────────────────────────────────────
const DATA_URL    = "./data/latest_scores.json";
const HISTORY_URL = "./data/history.jsonl";

// ── 가중치 설정 ───────────────────────────────────────────
const WEIGHTS = {
  w1: 0.25,   // 주도주 압축
  w2: 0.30,   // 채권 자경단 (금리)
  w3: 0.20,   // 사모 크레딧
  w4: 0.25,   // 대어급 IPO
};

const WEIGHT_LABELS = {
  w1: "25%",
  w2: "30%",
  w3: "20%",
  w4: "25%",
};

// ── IPO 상태 → CSS 클래스 매핑 ───────────────────────────
const statusClassMap = {
  "신청완료":   "Filed",
  "검토중":     "Considering",
  "공모가확정": "Priced",
  "거래중":     "Trading",
  "루머":       "Rumor",
};

// ── 등급별 색상 ───────────────────────────────────────────
const GRADE_COLOR = {
  GREEN:  "#27ae60",
  YELLOW: "#f39c12",
  RED:    "#e74c3c",
};

// ── 점수별 CSS 클래스 ─────────────────────────────────────
function gradeClass(score) {
  if (score >= 70) return "grade-red";
  if (score >= 40) return "grade-yellow";
  return "grade-green";
}

function scoreBarColor(score) {
  if (score >= 70) return "#e74c3c";
  if (score >= 40) return "#f39c12";
  return "#27ae60";
}


// ════════════════════════════════════════════════════════════
// 카드 뒤집기
// ════════════════════════════════════════════════════════════

function toggleFlip(prefix) {
  const inner = document.getElementById(`inner-${prefix}`);
  if (!inner) return;
  inner.classList.toggle("flipped");
}


// ════════════════════════════════════════════════════════════
// 카드 높이 균일화  ← Bug Fix 3: loadHistory 후에도 재호출
// ════════════════════════════════════════════════════════════

function equalizeCardHeights() {
  const prefixes = ["w1", "w2", "w3", "w4"];

  // 1단계: 높이 리셋
  prefixes.forEach(p => {
    const inner = document.getElementById(`inner-${p}`);
    if (inner) inner.style.height = "auto";
  });

  // 2단계: 레이아웃 완료 후 실측
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

// 리사이즈 이벤트 연결 (중복 방지)
window.removeEventListener("resize", equalizeCardHeights);
window.addEventListener("resize", equalizeCardHeights);


// ════════════════════════════════════════════════════════════
// 카드 뒷면 콘텐츠 생성
// ════════════════════════════════════════════════════════════

function buildBackContent(prefix, raw) {
  // ── W1: 주도주 압축 ────────────────────────────────────
  if (prefix === "w1") {
    const spy    = (raw.spy_ytd              ?? 0).toFixed(2);
    const rsp    = (raw.rsp_ytd              ?? 0).toFixed(2);
    const diff   = ((raw.spy_ytd ?? 0) - (raw.rsp_ytd ?? 0)).toFixed(2);
    const pct    = raw.spread_percentile     ?? "N/A";
    const rsp1w  = raw.rsp_1w_return         != null
                   ? (raw.rsp_1w_return).toFixed(2)
                   : null;
    const isNeg  = raw.rsp_is_negative_while_spy_positive ?? false;

    const rsp1wHtml = rsp1w !== null
      ? `<div class="back-metric">
           <span class="back-label">RSP 1주 수익률</span>
           <span class="back-value ${parseFloat(rsp1w) < 0 ? 'val-red' : 'val-green'}">
             ${rsp1w > 0 ? "+" : ""}${rsp1w}%
           </span>
         </div>`
      : "";

    const warningHtml = isNeg
      ? `<p class="back-warning">🔴 SPY 상승 중 RSP 마이너스 — 진짜 위험 트리거 발동</p>`
      : `<p class="back-ok">✅ RSP 양수 유지 — 소외주 동반 상승 중</p>`;

    return `
      <div class="back-section">
        <h4>📊 수치 해설</h4>
        <div class="back-metric">
          <span class="back-label">SPY YTD (시가총액 가중)</span>
          <span class="back-value">+${spy}%</span>
        </div>
        <div class="back-metric">
          <span class="back-label">RSP YTD (동일 가중)</span>
          <span class="back-value">+${rsp}%</span>
        </div>
        <div class="back-metric">
          <span class="back-label">SPY–RSP 괴리율</span>
          <span class="back-value val-red">+${diff}%p</span>
        </div>
        <div class="back-metric">
          <span class="back-label">괴리 퍼센타일</span>
          <span class="back-value">${pct}%ile</span>
        </div>
        ${rsp1wHtml}
      </div>

      <div class="back-section">
        <h4>🔍 지금 어떤 상황인가?</h4>
        <p>
          <strong>SPY</strong>는 엔비디아·애플·마이크로소프트 등 대형주에
          자동으로 비중이 쏠리는 시가총액 가중 ETF입니다.
          <strong>RSP</strong>는 같은 500개 종목을 동일 비중으로 담은 ETF입니다.
        </p>
        <p>
          현재 두 ETF의 연초 대비 수익률 차이가 <strong>${diff}%p</strong>로,
          이는 역대 데이터 중 상위 <strong>${pct}%ile</strong> 수준입니다.
          쉽게 말해, 지금처럼 대형주와 나머지 종목 사이의 격차가 이렇게
          벌어진 적이 역사적으로 거의 없었다는 의미입니다.
        </p>
        ${warningHtml}
        <p class="back-advice">
          💡 <strong>투자 시사점:</strong>
          RSP가 플러스를 유지하는 동안은 시장 전반의 붕괴보다
          대형주 쏠림 현상에 가깝습니다. RSP가 마이너스로 전환되면
          포지션 축소를 고려하세요.
        </p>
      </div>
    `;
  }

  // ── W2: 채권 자경단 (금리) ─────────────────────────────
  if (prefix === "w2") {
    const y10      = (raw.us10y_yield         ?? 0).toFixed(2);
    const y2       = (raw.us2y_yield          ?? 0).toFixed(2);
    const termSprd = ((raw.us10y_yield ?? 0) - (raw.us2y_yield ?? 0)).toFixed(2);
    const realYld  = (raw.tips_10y_real_yield ?? 0).toFixed(2);
    const isInv    = parseFloat(termSprd) < 0;

    return `
      <div class="back-section">
        <h4>📊 수치 해설</h4>
        <div class="back-metric">
          <span class="back-label">미국 10년물 국채금리</span>
          <span class="back-value ${parseFloat(y10) >= 4.5 ? 'val-red' : ''}">${y10}%</span>
        </div>
        <div class="back-metric">
          <span class="back-label">미국 2년물 국채금리</span>
          <span class="back-value">${y2}%</span>
        </div>
        <div class="back-metric">
          <span class="back-label">장단기 금리차 (10Y–2Y)</span>
          <span class="back-value ${isInv ? 'val-red' : 'val-green'}">
            ${parseFloat(termSprd) >= 0 ? "+" : ""}${termSprd}%p
          </span>
        </div>
        <div class="back-metric">
          <span class="back-label">10년 실질금리 (TIPS)</span>
          <span class="back-value">${realYld}%</span>
        </div>
      </div>

      <div class="back-section">
        <h4>🔍 지금 어떤 상황인가?</h4>
        <p>
          채권 시장의 큰손(자경단)들이 금리를 높게 유지하면
          주식 시장에서 돈이 빠져나가는 효과가 생깁니다.
          <strong>10년물 금리 4.5%</strong>가 핵심 임계선으로,
          이를 돌파하면 주식 밸류에이션 압박이 본격화됩니다.
        </p>
        <p>
          현재 10년물은 <strong>${y10}%</strong>입니다.
          ${parseFloat(y10) >= 4.5
            ? "⚠️ 임계선 4.5%를 <strong>돌파</strong>한 상태입니다. 주식 시장 압박 구간입니다."
            : `임계선 4.5%까지 <strong>${(4.5 - parseFloat(y10)).toFixed(2)}%p</strong> 여유가 있습니다.`
          }
        </p>
        ${isInv
          ? `<p class="back-warning">🔴 장단기 금리 역전 — 경기침체 선행 신호</p>`
          : `<p class="back-ok">✅ 장단기 금리차 정상 (역전 없음)</p>`
        }
        <p class="back-advice">
          💡 <strong>투자 시사점:</strong>
          10년물 금리가 4.5% 이상에서 유지되거나 상승하면
          성장주·기술주 비중 축소를 고려하세요.
        </p>
      </div>
    `;
  }

  // ── W3: 사모 크레딧 ────────────────────────────────────
  if (prefix === "w3") {
    const hy     = (raw.hy_spread_bps ?? 0).toFixed(0);
    const ig     = (raw.ig_spread_bps ?? 0).toFixed(0);
    const hyPct  = raw.hy_spread_percentile ?? "N/A";

    return `
      <div class="back-section">
        <h4>📊 수치 해설</h4>
        <div class="back-metric">
          <span class="back-label">HY 스프레드 (고수익채권)</span>
          <span class="back-value ${parseInt(hy) >= 400 ? 'val-red' : parseInt(hy) >= 300 ? 'val-yellow' : 'val-green'}">
            ${hy} bps
          </span>
        </div>
        <div class="back-metric">
          <span class="back-label">IG 스프레드 (투자등급채권)</span>
          <span class="back-value">${ig} bps</span>
        </div>
        <div class="back-metric">
          <span class="back-label">HY 스프레드 퍼센타일</span>
          <span class="back-value">${hyPct}%ile</span>
        </div>
      </div>

      <div class="back-section">
        <h4>🔍 지금 어떤 상황인가?</h4>
        <p>
          스프레드는 국채 대비 회사채의 추가 이자율입니다.
          기업들이 돈을 빌릴 때 얼마나 더 많은 이자를 내야 하는지를
          보여주는 지표로, 높을수록 시장의 불안감이 크다는 신호입니다.
        </p>
        <p>
          현재 고수익채권(HY) 스프레드는 <strong>${hy}bps</strong>,
          투자등급(IG) 스프레드는 <strong>${ig}bps</strong>입니다.
          HY 300bps 미만은 역사적 저점권으로 시장이 매우 낙관적임을 의미합니다.
          ${parseInt(hy) < 300
            ? "지금은 그 낮은 수준입니다 — 역설적으로 향후 스프레드 확대 리스크가 존재합니다."
            : parseInt(hy) >= 400
              ? "⚠️ 400bps 돌파 — 신용 위기 경계 구간입니다."
              : "현재는 정상~주의 구간입니다."
          }
        </p>
        <p class="back-advice">
          💡 <strong>투자 시사점:</strong>
          HY 스프레드가 급격히 400bps 이상으로 확대되면
          신용 경색 초입 신호로 해석하고 위험자산 비중을 줄이세요.
        </p>
      </div>
    `;
  }

  // ── W4: 대어급 IPO ─────────────────────────────────────
  if (prefix === "w4") {
    const totalBn   = (raw.total_weighted_bn  ?? 0).toLocaleString();
    const filed     = raw.filed_count         ?? 0;
    const priced    = raw.priced_count        ?? 0;
    const ipoList   = raw.ipo_list            ?? [];

    return `
      <div class="back-section">
        <h4>📊 수치 해설</h4>
        <div class="back-metric">
          <span class="back-label">가중 IPO 파이프라인</span>
          <span class="back-value ${parseFloat(totalBn.replace(/,/g,'')) >= 1500 ? 'val-red' : 'val-yellow'}">

            $${totalBn}B
          </span>
        </div>
        <div class="back-metric">
          <span class="back-label">S-1 신청완료 건수</span>
          <span class="back-value">${filed}건</span>
        </div>
        <div class="back-metric">
          <span class="back-label">공모가 확정 건수</span>
          <span class="back-value">${priced}건</span>
        </div>
      </div>

      <div class="back-section">
        <h4>🔍 지금 어떤 상황인가?</h4>
        <p>
          대형 IPO가 줄줄이 예정되면 기관·개인 투자자들의 현금이
          주식 시장에서 빠져나와 IPO 청약에 쏠립니다.
          이를 <strong>유동성 흡수</strong> 효과라고 합니다.
        </p>
        <p>
          현재 가중 파이프라인은 <strong>$${totalBn}B</strong>입니다.
          스페이스X($1,750B)의 역대 최대 IPO를 포함해
          OpenAI($852B), Anthropic($900B) 등이 줄줄이 대기 중으로,
          역사상 전례 없는 규모입니다.
        </p>
        <p>
          <strong>가중치 계산 방식:</strong> S-1 신청완료 기업은 100%,
          검토중은 30%, 루머는 10%의 기업가치만 파이프라인에 반영합니다.
          $1,500B 초과 시 HIGH 위험 등급입니다.
        </p>
        <p class="back-advice">
          💡 <strong>투자 시사점:</strong>
          스페이스X IPO(6월 12일 예정) 전후로 시장 유동성이
          일시적으로 타이트해질 수 있습니다.
          청약 참여 계획이 없다면 IPO 당일 전후 변동성에 주의하세요.
        </p>
      </div>
    `;
  }

  return `<p>데이터 없음</p>`;
}


// ════════════════════════════════════════════════════════════
// 가중치 적용 종합점수 계산
// ════════════════════════════════════════════════════════════

function calcWeightedScore(raw) {
  const s1 = (raw.w1_score ?? 0) * WEIGHTS.w1;
  const s2 = (raw.w2_score ?? 0) * WEIGHTS.w2;
  const s3 = (raw.w3_score ?? 0) * WEIGHTS.w3;
  const s4 = (raw.w4_score ?? 0) * WEIGHTS.w4;
  return Math.min(100, Math.round((s1 + s2 + s3 + s4) * 10) / 10);
}


// ════════════════════════════════════════════════════════════
// IPO 테이블 렌더링
// ════════════════════════════════════════════════════════════

function renderIPOTable(ipoList) {
  if (!ipoList || ipoList.length === 0) {
    return `<p class="no-data">IPO 데이터 없음</p>`;
  }

  const rows = ipoList.map(item => {
    const cssKey    = statusClassMap[item.status] ?? "Rumor";
    const valuation = item.valuation_bn
      ? `$${item.valuation_bn.toLocaleString()}B`
      : "–";
    const weight    = (STATUS_WEIGHT?.[item.status] ?? 0.1) * 100;
    const weightedBn = item.valuation_bn
      ? `$${Math.round(item.valuation_bn * (STATUS_WEIGHT?.[item.status] ?? 0.1)).toLocaleString()}B`
      : "–";

    return `
      <tr>
        <td>${item.company}</td>
        <td>${valuation}</td>
        <td><span class="status-badge status-${cssKey}">${item.status}</span></td>
        <td>${weight}%</td>
        <td>${weightedBn}</td>
      </tr>
    `;
  }).join("");

  return `
    <table class="ipo-table">
      <thead>
        <tr>
          <th>기업</th>
          <th>기업가치</th>
          <th>상태</th>
          <th>가중치</th>
          <th>반영액</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}


// ════════════════════════════════════════════════════════════
// 경고 카드 렌더링
// ════════════════════════════════════════════════════════════

function renderWarningCard(prefix, title, score, raw) {
  const color   = scoreBarColor(score);
  const gClass  = gradeClass(score);
  const weight  = WEIGHT_LABELS[prefix];
  const backHtml = buildBackContent(prefix, raw);

  // W4는 IPO 테이블 추가
  const extraHtml = prefix === "w4"
    ? renderIPOTable(raw.ipo_list ?? [])
    : "";

  return `
    <div class="card-flip-wrapper">
      <div class="card-flip-inner" id="inner-${prefix}">

        <!-- 앞면 -->
        <div class="card-front" id="card-${prefix}">
          <div class="card-header">
            <span class="card-title">${title}</span>
            <span class="weight-badge">가중치 ${weight}</span>
            <button class="flip-btn" onclick="toggleFlip('${prefix}')">
              상세 보기 ▶
            </button>
          </div>
          <div class="score-bar-wrap">
            <div class="score-bar"
                 style="width:${score}%; background:${color};">
            </div>
          </div>
          <div class="card-score ${gClass}">${score}<span class="score-unit">점</span></div>
          ${extraHtml}
        </div>

        <!-- 뒷면 -->
        <div class="card-back" id="back-${prefix}">
          <div class="card-header">
            <span class="card-title">${title} — 상세 해설</span>
            <button class="flip-btn" onclick="toggleFlip('${prefix}')">
              ◀ 돌아가기
            </button>
          </div>
          <div class="back-content">
            ${backHtml}
          </div>
        </div>

      </div>
    </div>
  `;
}


// ════════════════════════════════════════════════════════════
// 메인 대시보드 렌더링
// ════════════════════════════════════════════════════════════

function renderDashboard(data) {
  const composite = calcWeightedScore(data);
  const compColor = scoreBarColor(composite);
  const compClass = gradeClass(composite);

  let grade, gradeLabel;
  if (composite >= 70) { grade = "RED";    gradeLabel = "🔴 위험"; }
  else if (composite >= 40) { grade = "YELLOW"; gradeLabel = "🟡 주의"; }
  else { grade = "GREEN";  gradeLabel = "🟢 안전"; }

  // ── 종합 카드 ────────────────────────────────────────────
  const compositeEl = document.getElementById("composite-card");
  if (compositeEl) {
    compositeEl.innerHTML = `
      <div class="composite-inner">
        <div class="composite-score-ring ${compClass}">
          <span class="ring-score">${composite}</span>
          <span class="ring-label">퍼펙트스톰</span>
        </div>
        <div class="composite-info">
          <div class="composite-grade">${gradeLabel}</div>
          <div class="composite-sub">
            가중 평균 점수 (W1×25% + W2×30% + W3×20% + W4×25%)
          </div>
          <div class="composite-bars">
            ${["w1","w2","w3","w4"].map(p => {
              const s = data[`${p}_score`] ?? 0;
              const lbl = {w1:"주도주",w2:"금리",w3:"크레딧",w4:"IPO"}[p];
              return `
                <div class="mini-bar-row">
                  <span class="mini-bar-label">${lbl}</span>
                  <div class="mini-bar-bg">
                    <div class="mini-bar-fill"
                         style="width:${s}%;background:${scoreBarColor(s)}">
                    </div>
                  </div>
                  <span class="mini-bar-val">${s}점</span>
                </div>
              `;
            }).join("")}
          </div>
        </div>
      </div>
      <div class="composite-timestamp">
        데이터 기준: ${data.timestamp
          ? new Date(data.timestamp).toLocaleString("ko-KR", {timeZone:"Asia/Seoul"})
          : "N/A"}
        <span class="ts-hint">
          (매일 07:00 KST 자동 갱신 · latest_scores.json 파일 기준)
        </span>
      </div>
    `;
  }

  // ── 4개 경고 카드 ─────────────────────────────────────────
  const cards = [
    { prefix: "w1", title: "⚡ W1 주도주 압축", raw: data.w1 ?? {} },
    { prefix: "w2", title: "📈 W2 채권 자경단", raw: data.w2 ?? {} },
    { prefix: "w3", title: "💳 W3 사모 크레딧", raw: data.w3 ?? {} },
    { prefix: "w4", title: "🚀 W4 대어급 IPO",  raw: data.w4 ?? {} },
  ];

  const gridEl = document.getElementById("warnings-grid");
  if (gridEl) {
    gridEl.innerHTML = cards.map(c =>
      renderWarningCard(
        c.prefix,
        c.title,
        data[`${c.prefix}_score`] ?? 0,
        c.raw
      )
    ).join("");
  }

  // ── 높이 균일화 (차트 렌더 완료 후) ────────────────────
  setTimeout(equalizeCardHeights, 0);
}


// ════════════════════════════════════════════════════════════
// 히스토리 로드  ← Bug Fix 3: 완료 후 equalizeCardHeights 재호출
// ════════════════════════════════════════════════════════════

async function loadHistory() {
  try {
    const res  = await fetch(HISTORY_URL);
    const text = await res.text();
    const lines = text.trim().split("\n").filter(Boolean);

    const scores = lines.map(line => {
      try {
        const obj = JSON.parse(line);
        return {
          // composite 키 이름 양쪽 모두 대응 (Bug Fix: 키 불일치 방어)
          score: obj.composite_score ?? obj.score ?? obj.perfect_storm_score ?? 0,
          date:  obj.date ?? obj.timestamp?.slice(0, 10) ?? "",
        };
      } catch { return null; }
    }).filter(Boolean);

    if (typeof drawHistoryChart === "function") {
      drawHistoryChart(scores);
    }

  } catch (e) {
    console.warn("[History] 로드 실패:", e);
    // 샘플 데이터로 폴백
    if (typeof drawHistoryChart === "function") {
      drawHistoryChart([
        { date: "2026-05-01", score: 38 },
        { date: "2026-05-05", score: 42 },
        { date: "2026-05-09", score: 45 },
        { date: "2026-05-13", score: 48 },
        { date: "2026-05-17", score: 51 },
        { date: "2026-05-21", score: 50 },
        { date: "2026-05-25", score: 52 },
        { date: "2026-05-29", score: 51.5 },
      ]);
    }
  }

  // ── Bug Fix 3: IPO 테이블 렌더 후 높이 재계산 ──────────
  setTimeout(equalizeCardHeights, 150);
}


// ════════════════════════════════════════════════════════════
// 데이터 로드 및 초기화
// ════════════════════════════════════════════════════════════

async function loadData() {
  try {
    const res  = await fetch(DATA_URL);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    renderDashboard(data);
    await loadHistory();   // 히스토리는 대시보드 렌더 후 로드

  } catch (e) {
    console.error("[loadData] 실패:", e);
    document.getElementById("composite-card").innerHTML =
      `<p class="error-msg">⚠️ 데이터 로드 실패: ${e.message}</p>`;
  }
}

// ── 초기 실행 ─────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", loadData);
