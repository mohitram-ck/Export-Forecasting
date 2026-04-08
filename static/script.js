let mainChart = null;
let compareChart = null;

function showToast(message, isError = false) {
    const toast = document.getElementById("toast");
    toast.textContent = message;
    toast.style.background = isError ? "#b91c1c" : "#111827";
    toast.classList.add("show");
    setTimeout(() => {
        toast.classList.remove("show");
    }, 3000);
}

async function apiFetch(url, options = {}) {
    const resp = await fetch(url, {
        credentials: "include",
        ...options,
    });
    const contentType = resp.headers.get("content-type") || "";
    if (!resp.ok) {
        let msg = "Request failed";
        try {
            if (contentType.includes("application/json")) {
                const data = await resp.json();
                msg = data.error || JSON.stringify(data);
            } else {
                msg = await resp.text();
            }
        } catch (e) {
            // ignore
        }
        throw new Error(msg);
    }
    if (contentType.includes("application/json")) {
        return resp.json();
    }
    return resp.text();
}

function initSidebar() {
    const items = document.querySelectorAll(".sidebar-item");
    const sections = document.querySelectorAll(".section");

    items.forEach((item) => {
        item.addEventListener("click", () => {
            items.forEach((i) => i.classList.remove("active"));
            item.classList.add("active");
            const target = item.getAttribute("data-section");
            sections.forEach((sec) => {
                sec.classList.toggle("active", sec.id === `section-${target}`);
            });
        });
    });
}

function initUpload() {
    const uploadZone = document.getElementById("upload-zone");
    const fileInput = document.getElementById("file-input");
    const progressWrapper = document.getElementById("upload-progress-wrapper");
    const progressBar = document.getElementById("upload-progress-bar");

    function resetProgress() {
        progressWrapper.style.display = "none";
        progressBar.style.width = "0%";
    }

    uploadZone.addEventListener("click", () => fileInput.click());

    uploadZone.addEventListener("dragover", (e) => {
        e.preventDefault();
        uploadZone.classList.add("dragover");
    });

    uploadZone.addEventListener("dragleave", (e) => {
        e.preventDefault();
        uploadZone.classList.remove("dragover");
    });

    uploadZone.addEventListener("drop", (e) => {
        e.preventDefault();
        uploadZone.classList.remove("dragover");
        const file = e.dataTransfer.files[0];
        if (file) {
            uploadFile(file);
        }
    });

    fileInput.addEventListener("change", (e) => {
        const file = e.target.files[0];
        if (file) {
            uploadFile(file);
        }
    });

    async function uploadFile(file) {
        if (!file.name.toLowerCase().endsWith(".csv")) {
            showToast("Please upload a .csv file.", true);
            return;
        }
        if (file.size > 5 * 1024 * 1024) {
            showToast("File must be smaller than 5MB.", true);
            return;
        }
        const formData = new FormData();
        formData.append("file", file);

        progressWrapper.style.display = "block";
        progressBar.style.width = "20%";

        try {
            const data = await apiFetch("/api/upload", {
                method: "POST",
                body: formData,
            });
            progressBar.style.width = "100%";
            showToast(data.message || "Upload successful");
            await loadDatasets();
        } catch (err) {
            console.error(err);
            showToast(err.message || "Upload failed", true);
        } finally {
            setTimeout(resetProgress, 800);
        }
    }
}

async function loadDatasets() {
    const tableBody = document.querySelector("#datasets-table tbody");
    const datasetSelect = document.getElementById("dataset-select");

    tableBody.innerHTML = "<tr><td colspan='5'>Loading...</td></tr>";

    try {
        const datasets = await apiFetch("/api/datasets");
        tableBody.innerHTML = "";
        datasetSelect.innerHTML =
            '<option value="">Default Sample Data</option>';

        datasets.forEach((ds) => {
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td>${ds.filename}</td>
                <td>${ds.row_count ?? "-"}</td>
                <td>${ds.date_range ?? "-"}</td>
                <td>${ds.uploaded_at ?? "-"}</td>
                <td>
                    <button class="btn btn-secondary btn-sm use-dataset" data-id="${
                        ds.id
                    }">Use this dataset</button>
                    <button class="btn btn-primary btn-sm delete-dataset" data-id="${
                        ds.id
                    }">Delete</button>
                </td>
            `;
            tableBody.appendChild(tr);

            const opt = document.createElement("option");
            opt.value = ds.id;
            opt.textContent = ds.filename;
            datasetSelect.appendChild(opt);
        });

        tableBody.querySelectorAll(".use-dataset").forEach((btn) => {
            btn.addEventListener("click", () => {
                const id = btn.getAttribute("data-id");
                datasetSelect.value = id;
                showToast("Dataset selected for forecasting.");
            });
        });
        tableBody.querySelectorAll(".delete-dataset").forEach((btn) => {
            btn.addEventListener("click", async () => {
                const id = btn.getAttribute("data-id");
                if (!confirm("Delete this dataset?")) {
                    return;
                }
                try {
                    await apiFetch(`/api/datasets/${id}`, { method: "DELETE" });
                    showToast("Dataset deleted.");
                    await loadDatasets();
                } catch (err) {
                    showToast(err.message || "Failed to delete dataset", true);
                }
            });
        });
    } catch (err) {
        console.error(err);
        tableBody.innerHTML =
            "<tr><td colspan='5'>Failed to load datasets.</td></tr>";
    }
}

function initForecastControls() {
    const stepsRange = document.getElementById("steps-range");
    const stepsLabel = document.getElementById("steps-label");
    stepsLabel.textContent = stepsRange.value;
    stepsRange.addEventListener("input", () => {
        stepsLabel.textContent = stepsRange.value;
    });

    document
        .getElementById("run-forecast-btn")
        .addEventListener("click", (event) => {
            event.preventDefault();
            runForecast();
        });
}

function updateMetrics(metric) {
    document.getElementById("metric-mae").textContent = metric.mae.toFixed(2);
    document.getElementById("metric-rmse").textContent = metric.rmse.toFixed(2);
    document.getElementById("metric-mape").textContent = metric.mape.toFixed(2) + "%";
    document.getElementById("metric-accuracy").textContent =
        metric.accuracy.toFixed(2) + "%";
}

function renderMainChart(series, forecast) {
    const ctx = document.getElementById("main-chart").getContext("2d");
    if (mainChart) {
        mainChart.destroy();
    }

    const historyData = series.values;
    const forecastValues = forecast.values;

    const hasForecast = Array.isArray(forecast?.dates) && forecast.dates.length > 0;
    const allDates = hasForecast ? [...series.dates, ...forecast.dates] : [...series.dates];

    const datasets = [
        {
            label: "Historical",
            data: historyData,
            borderColor: "#1d4ed8",
            backgroundColor: "rgba(37,99,235,0.1)",
            tension: 0.25,
        },
    ];

    if (hasForecast && historyData.length > 0) {
        datasets.push({
            label: "Forecast",
            data: [
                ...new Array(historyData.length - 1).fill(null),
                historyData[historyData.length - 1],
                ...forecastValues,
            ],
            borderColor: "#22c55e",
            backgroundColor: "rgba(34,197,94,0.1)",
            borderDash: [5, 5],
            tension: 0.25,
        });
    }

    mainChart = new Chart(ctx, {
        type: "line",
        data: {
            labels: allDates,
            datasets,
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: {
                    ticks: {
                        maxTicksLimit: 10,
                    },
                },
            },
        },
    });
}

async function runForecast(fromHistoryId) {
    const datasetSelect = document.getElementById("dataset-select");
    const modelSelect = document.getElementById("model-select");
    const stepsRange = document.getElementById("steps-range");
    const spinner = document.getElementById("forecast-spinner");
    const btnText = document.querySelector("#run-forecast-btn .btn-text");

    const payload = {};

    if (!fromHistoryId) {
        if (datasetSelect.value) {
            payload.dataset_id = parseInt(datasetSelect.value, 10);
        }
        payload.model = modelSelect.value;
        payload.steps = parseInt(stepsRange.value, 10);
    }

    spinner.style.display = "inline-block";
    btnText.textContent = "Running...";

    try {
        let data;
        if (fromHistoryId) {
            data = await apiFetch(`/api/history/${fromHistoryId}`);
            if (!data.forecast) {
                throw new Error("No stored forecast available.");
            }
            renderMainChart(
                {
                    dates: data.forecast.dates,
                    values: data.series_values || [],
                },
                {
                    dates: data.forecast.dates,
                    values: data.forecast.predicted,
                }
            );
            updateMetrics({
                mae: data.mae,
                rmse: data.rmse,
                mape: data.mape,
                accuracy: data.accuracy,
            });
            showToast("Loaded forecast from history.");
            return;
        } else {
            data = await apiFetch("/api/forecast", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify(payload),
            });
        }

        updateMetrics(data.metric);
        renderMainChart(data.series, data.forecast);
        showToast("Forecast generated.");
    } catch (err) {
        console.error(err);
        showToast(err.message || "Could not run forecast", true);
    } finally {
        spinner.style.display = "none";
        btnText.textContent = "Generate Forecast";
    }
}

async function loadHistory() {
    const tableBody = document.querySelector("#history-table tbody");
    tableBody.innerHTML = "<tr><td colspan='8'>Loading...</td></tr>";
    try {
        const records = await apiFetch("/api/history");
        tableBody.innerHTML = "";
        if (!records.length) {
            tableBody.innerHTML =
                "<tr><td colspan='8'>No history yet. Run a forecast to get started.</td></tr>";
            return;
        }
        records.forEach((rec) => {
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td>${rec.created_at}</td>
                <td>${rec.model_used.toUpperCase()}</td>
                <td>${rec.dataset_name || "Sample Data"}</td>
                <td>${rec.steps}</td>
                <td>${rec.mae?.toFixed ? rec.mae.toFixed(2) : "-"}</td>
                <td>${rec.rmse?.toFixed ? rec.rmse.toFixed(2) : "-"}</td>
                <td>${rec.accuracy?.toFixed ? rec.accuracy.toFixed(1) + "%" : "-"}</td>
                <td>
                    <button class="btn btn-secondary btn-sm view-history" data-id="${
                        rec.id
                    }">View Chart</button>
                    <button class="btn btn-primary btn-sm delete-history" data-id="${
                        rec.id
                    }">Delete</button>
                </td>
            `;
            tableBody.appendChild(tr);
        });

        tableBody.querySelectorAll(".view-history").forEach((btn) => {
            btn.addEventListener("click", () => {
                const id = btn.getAttribute("data-id");
                loadHistoryDetail(id);
            });
        });
        tableBody.querySelectorAll(".delete-history").forEach((btn) => {
            btn.addEventListener("click", () => {
                const id = btn.getAttribute("data-id");
                deleteHistory(id);
            });
        });
    } catch (err) {
        console.error(err);
        tableBody.innerHTML =
            "<tr><td colspan='8'>Failed to load history.</td></tr>";
    }
}

async function loadHistoryDetail(id) {
    try {
        const data = await apiFetch(`/api/history/${id}`);
        if (!data.forecast) {
            showToast("No forecast JSON stored for this record.", true);
            return;
        }
        const dates = data.forecast.dates || [];
        const predicted = data.forecast.predicted || [];
        renderMainChart({ dates, values: predicted }, { dates: [], values: [] });
        updateMetrics({
            mae: data.mae,
            rmse: data.rmse,
            mape: data.mape,
            accuracy: data.accuracy,
        });
        showToast("History forecast loaded.");
    } catch (err) {
        console.error(err);
        showToast(err.message || "Failed to load history detail", true);
    }
}

async function deleteHistory(id) {
    if (!confirm("Delete this forecast history record?")) {
        return;
    }
    try {
        await apiFetch(`/api/history/${id}`, {
            method: "DELETE",
        });
        showToast("History record deleted.");
        await loadHistory();
    } catch (err) {
        console.error(err);
        showToast(err.message || "Failed to delete record", true);
    }
}

async function runCompare() {
    const datasetSelect = document.getElementById("dataset-select");
    const stepsRange = document.getElementById("steps-range");

    const params = new URLSearchParams();
    if (datasetSelect.value) {
        params.append("dataset_id", datasetSelect.value);
    }
    params.append("steps", stepsRange.value);

    try {
        const data = await apiFetch(`/api/compare?${params.toString()}`);
        const tbody = document.querySelector("#compare-table tbody");
        tbody.innerHTML = "";
        const rmses = [];
        const labels = ["arima", "lstm", "hybrid"];

        labels.forEach((name) => {
            const res = data.summary[name];
            const tr = document.createElement("tr");
            const highlightClass =
                name === data.best_model ? ' style="background:#dcfce7;"' : "";

            if (res.error) {
                tr.innerHTML = `<td${highlightClass}>${name.toUpperCase()}</td><td colspan="4">${res.error}</td>`;
                tbody.appendChild(tr);
            } else {
                rmses.push(res.rmse ?? 0);
                tr.innerHTML = `
                    <td${highlightClass}>${name.toUpperCase()}</td>
                    <td>${res.mae?.toFixed ? res.mae.toFixed(2) : "-"}</td>
                    <td>${res.rmse?.toFixed ? res.rmse.toFixed(2) : "-"}</td>
                    <td>${res.mape?.toFixed ? res.mape.toFixed(2) + "%" : "-"}</td>
                    <td>${res.accuracy?.toFixed ? res.accuracy.toFixed(1) + "%" : "-"}</td>
                `;
                tbody.appendChild(tr);
            }
        });

        const ctx = document.getElementById("compare-chart").getContext("2d");
        if (compareChart) {
            compareChart.destroy();
        }
        compareChart = new Chart(ctx, {
            type: "bar",
            data: {
                labels: labels.map((s) => s.toUpperCase()),
                datasets: [
                    {
                        label: "RMSE",
                        data: rmses,
                        backgroundColor: ["#1d4ed8", "#22c55e", "#f59e0b"],
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
            },
        });

        showToast(
            data.best_model
                ? `Best model: ${data.best_model.toUpperCase()}`
                : "Comparison completed."
        );
    } catch (err) {
        console.error(err);
        showToast(err.message || "Failed to compare models", true);
    }
}

async function initHealthCheck() {
    try {
        const start = performance.now();
        await apiFetch("/api/health");
        const elapsed = performance.now() - start;
        if (elapsed > 2000) {
            showToast("Server is waking up... please wait.");
        }
    } catch (err) {
        console.error(err);
    }
}

window.addEventListener("DOMContentLoaded", async () => {
    initSidebar();
    initUpload();
    initForecastControls();

    document
        .getElementById("run-compare-btn")
        .addEventListener("click", runCompare);

    await initHealthCheck();
    await loadDatasets();
    await loadHistory();
});

