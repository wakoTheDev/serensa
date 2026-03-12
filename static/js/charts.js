(function () {
  const payloadEl = document.getElementById("chart-data");
  const shopBoardEl = document.getElementById("shop-chart-board");
  const generalBoardEl = document.getElementById("general-chart-board");
  const emptyShopEl = document.getElementById("empty-shop-charts");
  const emptyGeneralEl = document.getElementById("empty-general-charts");

  if (!payloadEl || !shopBoardEl || !generalBoardEl || typeof Chart === "undefined") {
    return;
  }

  const data = JSON.parse(payloadEl.textContent || "{}");
  const chartCards = Array.isArray(data.chartCards) ? data.chartCards : [];

  if (!chartCards.length) {
    if (emptyShopEl) emptyShopEl.hidden = false;
    if (emptyGeneralEl) emptyGeneralEl.hidden = false;
    return;
  }

  const shopCards = chartCards.filter(function (card) {
    return card.category === "Shop";
  });
  const generalCards = chartCards.filter(function (card) {
    return card.category === "General";
  });

  if (emptyShopEl) {
    emptyShopEl.hidden = shopCards.length > 0;
  }
  if (emptyGeneralEl) {
    emptyGeneralEl.hidden = generalCards.length > 0;
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

  const renderCharts = function (cards, boardEl, baseIdx) {
    cards.forEach(function (card, idx) {
      const article = document.createElement("article");
      article.className = "panel chart-panel compact-chart-panel";

      const category = document.createElement("p");
      category.className = "chart-category-tag";
      category.textContent = card.category || "General";

      const title = document.createElement("h3");
      title.textContent = card.title || "Report Chart";

      const wrap = document.createElement("div");
      wrap.className =
        "chart-wrap" +
        (card.chartType === "line" || card.chartType === "pie" ? " trend-wrap" : "");

      const canvas = document.createElement("canvas");
      canvas.id = "report-chart-" + baseIdx + "-" + idx;

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
  };

  renderCharts(shopCards, shopBoardEl, 0);
  renderCharts(generalCards, generalBoardEl, 1000);
})();
