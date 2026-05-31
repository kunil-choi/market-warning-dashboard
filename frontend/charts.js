"use strict";

function scoreToColor(score) {
  if (score >= 70) return "#ef4444";
  if (score >= 50) return "#f97316";
  if (score >= 35) return "#eab308";
  if (score >= 20) return "#84cc16";
  return "#10b981";
}

// ── 종합 스코어 링 ──
let scoreRingInstance = null;

function drawScoreRing(score) {
  const canvas = document.getElementById("score-ring");
  if (!canvas) return;
  if (scoreRingInstance) scoreRingInstance.destroy();

  const color = scoreToColor(score);

  scoreRingInstance = new Chart(canvas, {
    type: "doughnut",
    data: {
      datasets: [{
        data: [score, 100 - score],
        backgroundColor: [color, "#1e3a5f"],
        borderWidth: 0,
        hoverOffset: 0,
      }]
    },
    options: {
      responsive: false,
      plugins: { legend: { display: false }, tooltip: { enabled: false } },
      cutout: "78%",
      animation: { animateRotate: true, duration: 1000 }
    }
  });

  const el = document.getElementById("composite-score");
  if (el) {
    el.style.color = color;
    el.textContent = score.toFixed(1);
  }
}

// ── 라인 차트 인스턴스 관리 ──
const lineInstances = {};

// ── 경고등1: SPY vs RSP ──
function drawLiquidityChart(canvasId, history) {
  const canvas = document.getElementById(canvasId);
  if (!canvas || !history) return;
  if (lineInstances[canvasId]) lineInstances[canvasId].destroy();

  lineInstances[canvasId] = new Chart(canvas, {
    type: "line",
    data: {
      labels: history.dates,
      datasets: [
        {
          label: "SPY",
          data: history.spy,
          borderColor: "#38bdf8",
          borderWidth: 1.5,
          pointRadius: 0,
          tension: 0.3,
          fill: false,
        },
        {
          label: "RSP",
          data: history.rsp,
          borderColor: "#f59e0b",
          borderWidth: 1.5,
          pointRadius: 0,
          tension: 0.3,
          fill: false,
        },
        {
          label: "QQQ",
          data: history.qqq,
          borderColor: "#a78bfa",
          borderWidth: 1,
          pointRadius: 0,
          tension: 0.3,
          fill: false,
          borderDash: [4, 3],
        },
        {
          label: "DIA",
          data: history.dia,
          borderColor: "#6b7280",
          borderWidth: 1,
          pointRadius: 0,
          tension: 0.3,
          fill: false,
          borderDash: [4, 3],
        },
      ]
    },
    options: {
      responsive: true,
      plugins: {
        legend: { display: true, labels: { color: "#94a3b8", font: { size: 10 }, boxWidth: 12 } },
        tooltip: { mode: "index", intersect: false, backgroundColor: "#0d1b2e", borderColor: "#1e3a5f", borderWidth: 1 }
      },
      scales: {
        x: { ticks: { color: "#475569", font: { size: 9 }, maxTicksLimit: 8 }, grid: { color: "rgba(255,255,255,0.04)" } },
        y: { ticks: { color: "#475569", font: { size: 9 } }, grid: { color: "rgba(255,255,255,0.04)" } }
      },
      animation: { duration: 600 }
    }
  });
}

// ── 경고등2: 금리 차트 ──
function drawRatesChart(canvasId, history) {
  const canvas = document.getElementById(canvasId);
  if (!canvas || !history) return;
  if (lineInstances[canvasId]) lineInstances[canvasId].destroy();

  const colors = { t10y: "#ef4444", t2y: "#f97316", fed_funds: "#38bdf8", real10y: "#a78bfa" };
  const labels = { t10y: "10년 국채", t2y: "2년 국채", fed_funds: "연준 기준금리", real10y: "실질 10년" };

  const datasets = Object.entries(history)
    .filter(([, h]) => h && h.dates && h.dates.length > 0)
    .map(([key, h]) => ({
      label: labels[key] || key,
      data: h.values,
      borderColor: colors[key] || "#6b7280",
      borderWidth: 1.5,
      pointRadius: 0,
      tension: 0.2,
      fill: false,
    }));

  const allDates = Object.values(history).find(h => h && h.dates)?.dates || [];

  lineInstances[canvasId] = new Chart(canvas, {
    type: "line",
    data: { labels: allDates, datasets },
    options: {
      responsive: true,
      plugins: {
        legend: { display: true, labels: { color: "#94a3b8", font: { size: 10 }, boxWidth: 12 } },
        tooltip: { mode: "index", intersect: false, backgroundColor: "#0d1b2e", borderColor: "#1e3a5f", borderWidth: 1,
          callbacks: { label: ctx => ` ${ctx.dataset.label}: ${ctx.parsed.y?.toFixed(2)}%` }
        }
      },
      scales: {
        x: { ticks: { color: "#475569", font: { size: 9 }, maxTicksLimit: 8 }, grid: { color: "rgba(255,255,255,0.04)" } },
        y: { ticks: { color: "#475569", font: { size: 9 }, callback: v => v.toFixed(1) + "%" }, grid: { color: "rgba(255,255,255,0.04)" } }
      },
      animation: { duration: 600 }
    }
  });
}

// ── 경고등3: HY 스프레드 차트 ──
function drawCreditChart(canvasId, history) {
  const canvas = document.getElementById(canvasId);
  if (!canvas || !history || !history.hy_spread) return;
  if (lineInstances[canvasId]) lineInstances[canvasId].destroy();

  const hy = history.hy_spread;
  const ig = history.ig_spread;

  lineInstances[canvasId] = new Chart(canvas, {
    type: "line",
    data: {
      labels: hy.dates,
      datasets: [
        {
          label: "HY 스프레드",
          data: hy.values,
          borderColor: "#ef4444",
          borderWidth: 1.5,
          pointRadius: 0,
          tension: 0.2,
          fill: { target: "origin", above: "rgba(239,68,68,0.07)" },
          yAxisID: "y",
        },
        ...(ig && ig.dates.length > 0 ? [{
          label: "IG 스프레드",
          data: ig.values,
          borderColor: "#38bdf8",
          borderWidth: 1,
          pointRadius: 0,
          tension: 0.2,
          fill: false,
          yAxisID: "y1",
          borderDash: [4, 3],
        }] : []),
      ]
    },
    options: {
      responsive: true,
      plugins: {
        legend: { display: true, labels: { color: "#94a3b8", font: { size: 10 }, boxWidth: 12 } },
        tooltip: { mode: "index", intersect: false, backgroundColor: "#0d1b2e", borderColor: "#1e3a5f", borderWidth: 1 }
      },
      scales: {
        x: { ticks: { color: "#475569", font: { size: 9 }, maxTicksLimit: 8 }, grid: { color: "rgba(255,255,255,0.04)" } },
        y:  { position: "left",  ticks: { color: "#ef4444", font: { size: 9 }, callback: v => v + "bps" }, grid: { color: "rgba(255,255,255,0.04)" } },
        y1: { position: "right", ticks: { color: "#38bdf8", font: { size: 9 }, callback: v => v + "bps" }, grid: { display: false } },
      },
      animation: { duration: 600 }
    }
  });
}

/* ── 히스토리 — 종합 점수 단일 라인 (선명하게) ── */
let historyChartInstance = null;

function drawHistoryChart(historyData) {
  const canvas = document.getElementById("history-chart");
  if (!canvas || !historyData || historyData.length === 0) return;
  if (historyChartInstance) historyChartInstance.destroy();

  const labels = historyData.map(d => d.date);
  const scores = historyData.map(d => d.score ?? 0);

  /* 점수별 색상 배열 */
  const pointColors = scores.map(s =>
    s >= 70 ? "#ef4444" : s >= 50 ? "#f97316" : s >= 35 ? "#eab308" : "#10b981"
  );

  /* 그라디언트 배경 */
  const ctx = canvas.getContext("2d");
  const gradient = ctx.createLinearGradient(0, 0, 0, canvas.clientHeight || 150);
  gradient.addColorStop(0,   "rgba(239,68,68,0.25)");
  gradient.addColorStop(0.5, "rgba(249,115,22,0.1)");
  gradient.addColorStop(1,   "rgba(16,185,129,0.0)");

  historyChartInstance = new Chart(canvas, {
    type: "line",
    data: {
      labels,
      datasets: [{
        label: "종합 위험 스코어",
        data: scores,
        borderColor: "#38bdf8",
        borderWidth: 2.5,
        pointRadius: scores.length <= 30 ? 4 : 2,
        pointBackgroundColor: pointColors,
        pointBorderColor: pointColors,
        pointHoverRadius: 6,
        tension: 0.35,
        fill: true,
        backgroundColor: gradient,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          mode: "index",
          intersect: false,
          backgroundColor: "#0d1b2e",
          borderColor: "#1e3a5f",
          borderWidth: 1,
          callbacks: {
            label: ctx => {
              const s = ctx.parsed.y;
              const level = s >= 70 ? "🔴 위험" : s >= 50 ? "🟠 경계" : s >= 35 ? "🟡 주의" : "🟢 안정";
              return ` 종합 점수: ${s.toFixed(1)} — ${level}`;
            }
          }
        },
        /* 위험 구간 배경 주석 */
        annotation: undefined,
      },
      scales: {
        x: {
          ticks: {
            color: "#475569",
            font: { size: 10 },
            maxTicksLimit: 10,
            maxRotation: 0,
          },
          grid: { color: "rgba(255,255,255,0.04)" }
        },
        y: {
          min: 0,
          max: 100,
          ticks: {
            color: "#475569",
            font: { size: 10 },
            stepSize: 25,
            callback: v => {
              if (v === 75) return "🔴 위험";
              if (v === 50) return "🟠 경계";
              if (v === 25) return "🟢 안정";
              return v;
            }
          },
          grid: {
            color: ctx => {
              if (ctx.tick.value === 70) return "rgba(239,68,68,0.3)";
              if (ctx.tick.value === 50) return "rgba(249,115,22,0.25)";
              if (ctx.tick.value === 35) return "rgba(234,179,8,0.2)";
              return "rgba(255,255,255,0.04)";
            },
            lineWidth: ctx => [70, 50, 35].includes(ctx.tick.value) ? 1.5 : 1,
          }
        }
      },
      animation: { duration: 1000, easing: "easeInOutQuart" }
    }
  });
}
