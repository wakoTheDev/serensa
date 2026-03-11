(function () {
  const payloadEl = document.getElementById("chart-data");
  const chartEl = document.getElementById("reportChart");

  if (!payloadEl || !chartEl || typeof Chart === "undefined") {
    return;
  }

  const data = JSON.parse(payloadEl.textContent);

  new Chart(chartEl, {
    type: "bar",
    data: {
      labels: data.labels,
      datasets: [
        {
          label: "Amount",
          data: data.values,
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
})();
