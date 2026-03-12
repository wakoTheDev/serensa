(function () {
  const payloadEl = document.getElementById("chart-data");
  const chartEl = document.getElementById("reportChart");
  const trendEl = document.getElementById("trendChart");

  if (!payloadEl || typeof Chart === "undefined") {
    return;
  }

  const data = JSON.parse(payloadEl.textContent);

  if (chartEl) {
    new Chart(chartEl, {
      type: "bar",
      data: {
        labels: data.barLabels || data.trendLabels || [],
        datasets: [
          {
            label: "Progressive Sales",
            data: data.barSales || [],
            borderRadius: 8,
            backgroundColor: "rgba(15, 118, 110, 0.75)",
          },
          {
            label: "Progressive Expenses",
            data: data.barExpenses || [],
            borderRadius: 8,
            backgroundColor: "rgba(180, 83, 9, 0.75)",
          },
          {
            label: "Progressive Profit/Loss",
            data: data.barProfit || [],
            borderRadius: 8,
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
        plugins: {
          legend: {
            display: true,
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
})();
