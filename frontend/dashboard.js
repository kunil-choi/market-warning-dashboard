/* ── 뒷면 콘텐츠 빌더 (수치해설 + 지표의미) ──────────────── */
function buildBackContent(prefix, score, raw) {

  if (prefix === "w1") {
    return `
      <div class="back-content">
        <div class="back-section">
          <h4>📐 수치 해설</h4>
          <div class="back-metric"><span class="back-label">SPY YTD</span><span class="back-value">S&P500 시가총액 가중 ETF 연초 대비 수익률</span></div>
          <div class="back-metric"><span class="back-label">RSP YTD</span><span class="back-value">S&P500 동일가중 ETF 연초 대비 수익률</span></div>
          <div class="back-metric"><span class="back-label">SPY-RSP 스프레드</span><span class="back-value">두 ETF 수익률 차이 — 클수록 소수 종목 쏠림</span></div>
          <div class="back-metric"><span class="back-label">스프레드 백분위</span><span class="back-value">과거 대비 현재 스프레드 상대 위치</span></div>
          <div class="back-metric"><span class="back-label">RSP 역행 신호</span><span class="back-value">SPY 상승 중 RSP 하락 = 쏠림 극단 경고</span></div>
        </div>
        <div class="back-section">
          <h4>📌 위험 기준</h4>
          <div class="back-metric"><span class="back-label">스프레드 &lt; 2%p</span><span class="back-value" style="color:#34d399">정상 — 균형 장세</span></div>
          <div class="back-metric"><span class="back-label">2~4%p</span><span class="back-value" style="color:#fbbf24">주의 — 쏠림 시작</span></div>
          <div class="back-metric"><span class="back-label">4~6%p</span><span class="back-value" style="color:#f97316">경고 — 2022년 수준</span></div>
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
          <div class="back-metric"><span class="back-label">4.0~4.5%</span><span class="back-value" style="color:#fbbf24">주의 — 부담 시작</span></div>
          <div class="back-metric"><span class="back-label">4.5~5.0%</span><span class="back-value" style="color:#f97316">경고 — 조정 동반 구간</span></div>
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
          <div class="back-metric"><span class="back-label">300~350 bps</span><span class="back-value" style="color:#fbbf24">주의 — 평균 상회</span></div>
          <div class="back-metric"><span class="back-label">350~600 bps</span><span class="back-value" style="color:#f97316">경고 — 스트레스 구간</span></div>
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
          <div class="back-metric"><span class="back-label">시총 대비 비율</span><span class="back-value">가중 파이프라인 ÷ 미국 시총 ($69조) × 100</span></div>
        </div>
        <div class="back-section">
          <h4>📌 위험 기준 (역사적 근거)</h4>
          <div class="back-metric"><span class="back-label">비율 &lt; 0.15%</span><span class="back-value" style="color:#34d399">정상 — 2010~16년 회복기 수준</span></div>
          <div class="back-metric"><span class="back-label">0.15~0.25%</span><span class="back-value" style="color:#fbbf24">주의 — 2021년 SPAC 붐 수준</span></div>
          <div class="back-metric"><span class="back-label">0.25~0.45%</span><span class="back-value" style="color:#f97316">경고 — 1999~2000년 닷컴버블 수준</span></div>
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
