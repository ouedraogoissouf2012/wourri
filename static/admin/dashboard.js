"use strict";

const STORAGE_KEY = "wourri_admin_api_key";
const state = {
  apiKey: sessionStorage.getItem(STORAGE_KEY) || "",
  chart: null,
};

const elements = {
  authPanel: document.getElementById("auth-panel"),
  authForm: document.getElementById("auth-form"),
  apiKey: document.getElementById("api-key"),
  authError: document.getElementById("auth-error"),
  dashboard: document.getElementById("dashboard"),
  period: document.getElementById("period"),
  refresh: document.getElementById("refresh"),
  logout: document.getElementById("logout"),
  generatedAt: document.getElementById("generated-at"),
};

function text(id, value) {
  document.getElementById(id).textContent = value;
}

function percent(value) {
  return value === null || value === undefined
    ? "—"
    : `${(value * 100).toFixed(1)} %`;
}

function duration(value) {
  return value === null || value === undefined
    ? "—"
    : `${Math.round(value)} ms`;
}

function localTime(value) {
  return new Intl.DateTimeFormat("fr-FR", {
    dateStyle: "short",
    timeStyle: "medium",
  }).format(new Date(value));
}

function statusClass(code) {
  if (code >= 500) return "status-error";
  if (code >= 400) return "status-warning";
  return "status-ok";
}

function renderRanking(id, rows) {
  const list = document.getElementById(id);
  list.replaceChildren();
  if (!rows.length) {
    const empty = document.createElement("li");
    empty.textContent = "Aucune donnée";
    list.appendChild(empty);
    return;
  }
  rows.forEach((row) => {
    const item = document.createElement("li");
    const label = document.createElement("span");
    const count = document.createElement("strong");
    label.textContent = row.label;
    count.textContent = row.count.toLocaleString("fr-FR");
    item.append(label, count);
    list.appendChild(item);
  });
}

function appendCell(row, value, className) {
  const cell = document.createElement("td");
  cell.textContent = value ?? "—";
  if (className) cell.className = className;
  row.appendChild(cell);
}

function renderRecent(rows) {
  const body = document.getElementById("recent-requests");
  body.replaceChildren();
  rows.forEach((item) => {
    const row = document.createElement("tr");
    appendCell(row, localTime(item.observed_at));
    appendCell(row, item.endpoint);
    appendCell(row, item.status_code, statusClass(item.status_code));
    appendCell(row, `${item.duration_ms} ms`);
    appendCell(row, item.intent);
    appendCell(row, item.culture);
    appendCell(row, item.source);
    body.appendChild(row);
  });
}

const errorLabels = {
  server_error: "Erreur serveur",
  client_error: "Erreur client",
  asr_failure: "Échec ASR",
  nlu_out_of_scope: "Hors sujet NLU",
};

function renderErrors(rows) {
  const body = document.getElementById("recent-errors");
  body.replaceChildren();
  rows.forEach((item) => {
    const row = document.createElement("tr");
    appendCell(row, localTime(item.observed_at));
    appendCell(row, errorLabels[item.error_kind] || item.error_kind);
    appendCell(row, item.endpoint);
    appendCell(row, item.status_code, statusClass(item.status_code));
    appendCell(row, `${item.duration_ms} ms`);
    appendCell(row, item.intent);
    body.appendChild(row);
  });
}

function renderChart(rows) {
  const fallback = document.getElementById("chart-fallback");
  if (typeof Chart === "undefined") {
    fallback.hidden = false;
    return;
  }
  fallback.hidden = true;
  const canvas = document.getElementById("requests-chart");
  if (state.chart) state.chart.destroy();
  state.chart = new Chart(canvas, {
    type: "line",
    data: {
      labels: rows.map((row) => row.day),
      datasets: [
        {
          label: "Requêtes",
          data: rows.map((row) => row.requests),
          borderColor: "#65d28d",
          backgroundColor: "rgba(101, 210, 141, .15)",
          fill: true,
          tension: .3,
        },
        {
          label: "Erreurs / hors-sujet",
          data: rows.map((row) => row.errors),
          borderColor: "#f5bd63",
          backgroundColor: "transparent",
          tension: .3,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          labels: { color: "#9fb3a5" },
        },
      },
      scales: {
        x: {
          ticks: { color: "#9fb3a5" },
          grid: { color: "rgba(36, 66, 49, .35)" },
        },
        y: {
          beginAtZero: true,
          ticks: { color: "#9fb3a5", precision: 0 },
          grid: { color: "rgba(36, 66, 49, .35)" },
        },
      },
    },
  });
}

function render(data) {
  const summary = data.summary;
  text("total-requests", summary.total_requests.toLocaleString("fr-FR"));
  text("success-rate", percent(summary.success_rate));
  text("asr-success-rate", percent(summary.asr_success_rate));
  text("nlu-scope-rate", percent(summary.nlu_in_scope_rate));
  text("average-duration", duration(summary.average_duration_ms));
  text("p95-duration", duration(summary.p95_duration_ms));
  elements.generatedAt.textContent = `Mis à jour ${localTime(data.generated_at)}`;
  renderRanking("top-intents", data.top_intents);
  renderRanking("top-cultures", data.top_cultures);
  renderRanking("endpoint-counts", data.endpoint_counts);
  renderRanking("top-sources", data.top_sources);
  renderRecent(data.recent_requests);
  renderErrors(data.recent_errors);
  renderChart(data.daily);
}

function showLogin(message = "") {
  elements.dashboard.hidden = true;
  elements.authPanel.hidden = false;
  elements.authError.textContent = message;
  elements.apiKey.focus();
}

function showDashboard() {
  elements.authPanel.hidden = true;
  elements.dashboard.hidden = false;
}

async function loadDashboard() {
  const headers = {};
  if (state.apiKey) headers["X-API-Key"] = state.apiKey;
  elements.refresh.disabled = true;
  try {
    const response = await fetch(
      `/admin/dashboard/data?days=${encodeURIComponent(elements.period.value)}`,
      { headers, cache: "no-store" },
    );
    if (response.status === 403) {
      showLogin("Clé invalide ou manquante.");
      return;
    }
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    render(await response.json());
    showDashboard();
  } catch (error) {
    elements.authError.textContent = "";
    text("connection-status", "Métriques temporairement indisponibles");
  } finally {
    elements.refresh.disabled = false;
  }
}

elements.authForm.addEventListener("submit", (event) => {
  event.preventDefault();
  state.apiKey = elements.apiKey.value.trim();
  sessionStorage.setItem(STORAGE_KEY, state.apiKey);
  loadDashboard();
});

elements.refresh.addEventListener("click", loadDashboard);
elements.period.addEventListener("change", loadDashboard);
elements.logout.addEventListener("click", () => {
  sessionStorage.removeItem(STORAGE_KEY);
  state.apiKey = "";
  elements.apiKey.value = "";
  showLogin();
});

loadDashboard();
setInterval(() => {
  if (!elements.dashboard.hidden && document.visibilityState === "visible") {
    loadDashboard();
  }
}, 30_000);
