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

// ── 히스토리 차트 ──
let historyChartInstance = null;

function drawHistoryChart(historyData) {
  const canvas = document.getElementById("history-chart");
  if (!canvas || !historyData || historyData.length === 0) return;
  if (historyChartInstance) historyChartInstance.destroy();

  const labels = historyData.map(d => d.date);

  historyChartInstance = new Chart(canvas, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "종합 위험 스코어",
          data: historyData.map(d => d.score),
          borderColor: "#ef4444",
          borderWidth: 2.5,
          pointRadius: 3,
          pointBackgroundColor: historyData.map(d => scoreToColor(d.score)),
          tension: 0.3,
          fill: { target: "origin", above: "rgba(239,68,68,0.05)" },
        },
        {
          label: "W1 주도주",
          data: historyData.map(d => d.w1),
          borderColor: "#38bdf8",
          borderWidth: 1,
          pointRadius: 0,
          tension: 0.3,
          fill: false,
          borderDash: [3, 3],
        },
        {
          label: "W2 금리",
          data: historyData.map(d => d.w2),
          borderColor: "#f59e0b",
          borderWidth: 1,
          pointRadius: 0,
          tension: 0.3,
          fill: false,
          borderDash: [3, 3],
        },
        {
          label: "W3 크레딧",
          data: historyData.map(d => d.w3),
          borderColor: "#a78bfa",
          borderWidth: 1,
          pointRadius: 0,
          tension: 0.3,
          fill: false,
          borderDash: [3, 3],
        },
        {
          label: "W4 IPO",
          data: historyData.map(d => d.w4),
          borderColor: "#34d399",
          borderWidth: 1,
          pointRadius: 0,
          tension: 0.3,
          fill: false,
          borderDash: [3, 3],
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
        x: { ticks: { color: "#475569", font: { size: 10 }, maxTicksLimit: 12 }, grid: { color: "rgba(255,255,255,0.04)" } },
        y: { min: 0, max: 100, ticks: { color: "#475569", font: { size: 10 }, stepSize: 20 }, grid: { color: "rgba(255,255,255,0.04)" } }
      },
      animation: { duration: 800 }
    }
  });
}
