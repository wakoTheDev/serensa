(function () {
  const payloadEl = document.getElementById("chart-data");
  const boardEl = document.getElementById("report-chart-board");
  const emptyEl = document.getElementById("empty-charts");

  if (!payloadEl || !boardEl || typeof Chart === "undefined") {
    return;
  }

  const data = JSON.parse(payloadEl.textContent || "{}");
  const chartCards = Array.isArray(data.chartCards) ? data.chartCards : [];

  if (!chartCards.length) {
    if (emptyEl) {
      emptyEl.hidden = false;
    }
    return;
  }

  if (emptyEl) {
    emptyEl.hidden = true;
  }

  const numberFormatter = function (val) {
    return Number(val || 0).toLocaleString(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  };

  const createBaseOptions = function (type) {
    const options = {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        mode: "index",
        intersect: false,
      },
      plugins: {
        legend: {
          display: type !== "bar",
          position: type === "pie" ? "bottom" : "top",
        },
        tooltip: {
          callbacks: {
            label: function (ctx) {
              const value = type === "pie" ? ctx.raw : ctx.parsed.y;
              return " " + ctx.dataset.label + ": " + numberFormatter(value);
            },
          },
        },
      },
    };

    if (type !== "pie") {
      options.scales = {
        x: {
          grid: { display: false },
        },
        y: {
          beginAtZero: true,
          ticks: {
            callback: function (val) {
              return Number(val).toLocaleString();
            },
          },
        },
      };
    }

    return options;
  };

  chartCards.forEach(function (card, idx) {
    const article = document.createElement("article");
    article.className = "panel chart-panel compact-chart-panel";

    const category = document.createElement("p");
    category.className = "chart-category-tag";
    category.textContent = card.category || "General";

    const title = document.createElement("h3");
    title.textContent = card.title || "Report Chart";

    const wrap = document.createElement("div");
    wrap.className = "chart-wrap" + (card.chartType === "line" || card.chartType === "pie" ? " trend-wrap" : "");

    const canvas = document.createElement("canvas");
    canvas.id = "report-chart-" + idx;

    wrap.appendChild(canvas);
    article.appendChild(category);
    article.appendChild(title);
    article.appendChild(wrap);
    boardEl.appendChild(article);

    const datasets = (card.datasets || []).map(function (set) {
      const next = Object.assign({}, set);
      if (card.chartType === "line") {
        if (next.pointRadius === undefined) next.pointRadius = 4;
        if (next.pointHoverRadius === undefined) next.pointHoverRadius = 7;
        if (next.pointHoverBorderWidth === undefined) next.pointHoverBorderWidth = 2;
      }
      return next;
    });

    new Chart(canvas, {
      type: card.chartType || "bar",
      data: {
        labels: card.labels || [],
        datasets: datasets,
      },
      options: createBaseOptions(card.chartType || "bar"),
    });
  });
})();
