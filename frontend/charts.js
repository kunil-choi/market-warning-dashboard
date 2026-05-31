// ============================================================
// charts.js  –  히스토리 차트 렌더링
// 퍼펙트스톰 단일 라인만 표출 (요구사항 3)
// ============================================================

"use strict";

/**
 * drawHistoryChart
 * @param {Array<{date: string, score: number}>} scores
 */
function drawHistoryChart(scores) {
  const canvas = document.getElementById("history-chart");
  if (!canvas) return;

  const ctx = canvas.getContext("2d");

  // 기존 차트 인스턴스 파괴 (중복 렌더 방지)
  if (window._historyChartInstance) {
    window._historyChartInstance.destroy();
  }

  if (!scores || scores.length === 0) {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = "#888";
    ctx.font = "14px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("히스토리 데이터 없음", canvas.width / 2, canvas.height / 2);
    return;
  }

  const labels = scores.map(s => s.date);
  const values = scores.map(s => s.score);

  // ── 그라디언트 배경 ────────────────────────────────────
  const gradient = ctx.createLinearGradient(0, 0, 0, canvas.height);
  gradient.addColorStop(0,   "rgba(231, 76,  60,  0.35)");   // 빨강 (상단)
  gradient.addColorStop(0.4, "rgba(243, 156, 18,  0.25)");   // 노랑 (중간)
  gradient.addColorStop(1,   "rgba(39,  174, 96,  0.10)");   // 초록 (하단)

  // ── 포인트별 색상 ─────────────────────────────────────
  const pointColors = values.map(v => {
    if (v >= 70) return "#e74c3c";
    if (v >= 40) return "#f39c12";
    return "#27ae60";
  });

  window._historyChartInstance = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [{
        label: "퍼펙트스톰 점수",
        data: values,
        borderColor: "#5b8ff9",
        borderWidth: 2.5,
        backgroundColor: gradient,
        fill: true,
        tension: 0.35,
        pointBackgroundColor: pointColors,
        pointBorderColor:     "#fff",
        pointBorderWidth:     2,
        pointRadius:          5,
        pointHoverRadius:     7,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 600 },
      interaction: {
        mode: "index",
        intersect: false,
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label(ctx) {
              const v = ctx.parsed.y;
              const grade = v >= 70 ? "🔴 위험" : v >= 40 ? "🟡 주의" : "🟢 안전";
              return ` ${v.toFixed(1)}점  ${grade}`;
            },
          },
          backgroundColor: "rgba(20,20,30,0.85)",
          titleColor:  "#fff",
          bodyColor:   "#ddd",
          padding:     10,
          cornerRadius: 8,
        },
      },
      scales: {
        x: {
          grid: { color: "rgba(255,255,255,0.06)" },
          ticks: {
            color: "#aaa",
            maxTicksLimit: 8,
            maxRotation: 0,
          },
        },
        y: {
          min: 0,
          max: 100,
          grid: {
            color(ctx) {
              const v = ctx.tick.value;
              if (v === 70) return "rgba(231,76,60,0.5)";
              if (v === 40) return "rgba(243,156,18,0.5)";
              return "rgba(255,255,255,0.06)";
            },
            lineWidth(ctx) {
              const v = ctx.tick.value;
              return (v === 70 || v === 40) ? 1.5 : 1;
            },
          },
          ticks: {
            color: "#aaa",
            stepSize: 10,
            callback(val) {
              if (val === 70) return "70 🔴";
              if (val === 40) return "40 🟡";
              if (val === 0)  return "0 🟢";
              return val;
            },
          },
        },
      },
    },
  });
}
