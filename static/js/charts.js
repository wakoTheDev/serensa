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
        labels: data.summaryLabels || data.labels || [],
        datasets: [
          {
            label: "Amount",
            data: data.summaryValues || data.values || [],
            borderRadius: 10,
            backgroundColor: ["#0f766e", "#b45309", "#be123c", "#1d4ed8"],
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            display: false,
          },
        },
        scales: {
          y: {
            beginAtZero: true,
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
            backgroundColor: "rgba(15, 118, 110, 0.2)",
            tension: 0.35,
            fill: false,
          },
          {
            label: "Expenses",
            data: data.trendExpenses || [],
            borderColor: "#b45309",
            backgroundColor: "rgba(180, 83, 9, 0.2)",
            tension: 0.35,
            fill: false,
          },
          {
            label: "Profit/Loss",
            data: data.trendProfit || [],
            borderColor: "#1d4ed8",
            backgroundColor: "rgba(29, 78, 216, 0.2)",
            tension: 0.35,
            fill: false,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            display: true,
          },
        },
        scales: {
          y: {
            beginAtZero: true,
          },
        },
      },
    });
  }
})();
