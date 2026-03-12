(function () {
  const payloadEl = document.getElementById("chart-data");
  const chartEl = document.getElementById("reportChart");
  const trendEl = document.getElementById("trendChart");
  const generalCumulativeEl = document.getElementById("generalCumulativeChart");
  const shopComparisonEl = document.getElementById("shopComparisonChart");
  const generalPieEl = document.getElementById("generalPieChart");

  if (!payloadEl || typeof Chart === "undefined") {
    return;
  }

  const data = JSON.parse(payloadEl.textContent);

  if (chartEl) {
    new Chart(chartEl, {
      type: "bar",
      data: {
        labels: data.shopBarLabels || [],
        datasets: [
          {
            label: `${data.shopName || "Shop"} (${data.shopBarDate || "Today"})`,
            data: data.shopBarValues || [],
            borderRadius: 8,
            backgroundColor: [
              "rgba(15, 118, 110, 0.75)",
              "rgba(180, 83, 9, 0.75)",
              "rgba(190, 24, 93, 0.75)",
              "rgba(30, 64, 175, 0.75)",
              "rgba(22, 101, 52, 0.75)",
            ],
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: {
          mode: "index",
          intersect: false,
        },
        plugins: {
          legend: {
            display: false,
          },
          tooltip: {
            callbacks: {
              label: function (ctx) {
                const val = ctx.parsed.y;
                return ` ${ctx.dataset.label}: ${val.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
              },
            },
          },
        },
        scales: {
          x: {
            grid: { display: false },
          },
          y: {
            beginAtZero: true,
            ticks: {
              callback: function (val) {
                return val.toLocaleString();
              },
            },
          },
        },
      },
    });
  }

  if (trendEl) {
    new Chart(trendEl, {
      type: "line",
      data: {
        labels: data.trendLabels || [],
        datasets: [
          {
            label: "Sales",
            data: data.trendSales || [],
            borderColor: "#0f766e",
            backgroundColor: "rgba(15, 118, 110, 0.08)",
            tension: 0.45,
            fill: true,
            pointRadius: 4,
            pointHoverRadius: 7,
            pointBackgroundColor: "#0f766e",
            pointHoverBackgroundColor: "#fff",
            pointHoverBorderColor: "#0f766e",
            pointHoverBorderWidth: 2,
          },
          {
            label: "Expenses",
            data: data.trendExpenses || [],
            borderColor: "#b45309",
            backgroundColor: "rgba(180, 83, 9, 0.08)",
            tension: 0.45,
            fill: true,
            pointRadius: 4,
            pointHoverRadius: 7,
            pointBackgroundColor: "#b45309",
            pointHoverBackgroundColor: "#fff",
            pointHoverBorderColor: "#b45309",
            pointHoverBorderWidth: 2,
          },
          {
            label: "Profit/Loss",
            data: data.trendProfit || [],
            borderColor: "#1d4ed8",
            backgroundColor: "rgba(29, 78, 216, 0.08)",
            tension: 0.45,
            fill: true,
            pointRadius: 4,
            pointHoverRadius: 7,
            pointBackgroundColor: "#1d4ed8",
            pointHoverBackgroundColor: "#fff",
            pointHoverBorderColor: "#1d4ed8",
            pointHoverBorderWidth: 2,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: {
          mode: "index",
          intersect: false,
        },
        plugins: {
          legend: {
            display: true,
          },
          tooltip: {
            enabled: true,
            mode: "index",
            intersect: false,
            callbacks: {
              label: function (ctx) {
                const val = ctx.parsed.y;
                return ` ${ctx.dataset.label}: ${val.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
              },
            },
          },
        },
        scales: {
          x: {
            grid: { display: false },
          },
          y: {
            beginAtZero: true,
            ticks: {
              callback: function (val) {
                return val.toLocaleString();
              },
            },
          },
        },
      },
    });
  }

  if (generalCumulativeEl) {
    new Chart(generalCumulativeEl, {
      type: "line",
      data: {
        labels: data.allCumulativeLabels || [],
        datasets: [
          {
            label: "Cumulative Sales",
            data: data.allCumulativeSales || [],
            borderColor: "#0f766e",
            backgroundColor: "rgba(15, 118, 110, 0.08)",
            tension: 0.4,
            fill: true,
          },
          {
            label: "Cumulative Debts",
            data: data.allCumulativeDebts || [],
            borderColor: "#be123c",
            backgroundColor: "rgba(190, 18, 60, 0.08)",
            tension: 0.4,
            fill: true,
          },
          {
            label: "Cumulative Profit/Loss",
            data: data.allCumulativeProfit || [],
            borderColor: "#1d4ed8",
            backgroundColor: "rgba(29, 78, 216, 0.08)",
            tension: 0.4,
            fill: true,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: {
          mode: "index",
          intersect: false,
        },
        plugins: {
          legend: { display: true },
        },
      },
    });
  }

  if (shopComparisonEl) {
    new Chart(shopComparisonEl, {
      type: "bar",
      data: {
        labels: data.shopCompareLabels || [],
        datasets: [
          {
            label: "Sales",
            data: data.shopCompareSales || [],
            backgroundColor: "rgba(15, 118, 110, 0.75)",
          },
          {
            label: "Debts",
            data: data.shopCompareDebts || [],
            backgroundColor: "rgba(190, 24, 93, 0.75)",
          },
          {
            label: "Profit/Loss",
            data: data.shopCompareProfit || [],
            backgroundColor: "rgba(29, 78, 216, 0.75)",
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: {
          mode: "index",
          intersect: false,
        },
      },
    });
  }

  if (generalPieEl) {
    new Chart(generalPieEl, {
      type: "pie",
      data: {
        labels: data.generalPieLabels || [],
        datasets: [
          {
            data: data.generalPieValues || [],
            backgroundColor: [
              "rgba(15, 118, 110, 0.8)",
              "rgba(180, 83, 9, 0.8)",
              "rgba(190, 24, 93, 0.8)",
              "rgba(29, 78, 216, 0.8)",
              "rgba(127, 29, 29, 0.8)",
            ],
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: "bottom",
          },
        },
      },
    });
  }
})();
