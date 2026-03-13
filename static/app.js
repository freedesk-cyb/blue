/* ────────────────────────────────────────────────────────────
   Cisco SG300-28 Monitor — Frontend JavaScript
   ──────────────────────────────────────────────────────────── */

const POLL_MS = 10_000;   // match backend poll interval

// ── DOM refs ────────────────────────────────────────────────
const connectPanel  = document.getElementById("connectPanel");
const dashboard     = document.getElementById("dashboard");
const connectForm   = document.getElementById("connectForm");
const connectError  = document.getElementById("connectError");
const connectBtn    = document.getElementById("connectBtn");
const disconnectBtn = document.getElementById("disconnectBtn");
const statusBadge   = document.getElementById("statusBadge");
const statusDot     = document.getElementById("statusDot");
const statusText    = document.getElementById("statusText");
const lastUpdate    = document.getElementById("lastUpdate");
const tableSearch   = document.getElementById("tableSearch");

// stat cards
const statUptime = document.getElementById("statUptime");
const statCpu    = document.getElementById("statCpu");
const statMem    = document.getElementById("statMem");
const statPorts  = document.getElementById("statPorts");
const cpuBar     = document.getElementById("cpuBar");
const memBar     = document.getElementById("memBar");
const cpuBadge   = document.getElementById("cpuBadge");

// ── Chart.js setup ──────────────────────────────────────────
const cpuCtx = document.getElementById("cpuChart").getContext("2d");
const cpuChart = new Chart(cpuCtx, {
  type: "line",
  data: {
    labels: [],
    datasets: [{
      label: "CPU %",
      data: [],
      borderColor: "#388bfd",
      backgroundColor: "rgba(56,139,253,.12)",
      borderWidth: 2,
      pointRadius: 2,
      pointHoverRadius: 5,
      fill: true,
      tension: 0.35,
    }]
  },
  options: {
    responsive: true,
    animation: { duration: 400 },
    plugins: { legend: { display: false } },
    scales: {
      x: {
        ticks: { color: "#6e7681", maxTicksLimit: 10, font: { family: "JetBrains Mono", size: 10 } },
        grid:  { color: "#21262d" },
      },
      y: {
        min: 0, max: 100,
        ticks: { color: "#6e7681", callback: v => v + "%", font: { family: "JetBrains Mono", size: 10 } },
        grid:  { color: "#21262d" },
      }
    }
  }
});

// ── State ───────────────────────────────────────────────────
let pollTimer = null;

// ── Connect flow ────────────────────────────────────────────
connectForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  connectError.textContent = "";
  const host      = document.getElementById("hostInput").value.trim();
  const community = document.getElementById("communityInput").value.trim() || "public";

  if (!host) { showError("Ingresa la IP del switch"); return; }

  setConnecting(true);
  try {
    const res  = await fetch("/api/connect", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ host, community }),
    });
    const data = await res.json();
    if (!data.ok) { showError(data.error); setConnecting(false); return; }

    // Show dashboard after a short wait so first poll can run
    await delay(1500);
    showDashboard();
    startPolling();
  } catch (err) {
    showError("No se pudo conectar: " + err.message);
    setConnecting(false);
  }
});

// ── Disconnect ──────────────────────────────────────────────
disconnectBtn.addEventListener("click", async () => {
  stopPolling();
  await fetch("/api/disconnect", { method: "POST" });
  showConnect();
});

// ── Polling ─────────────────────────────────────────────────
function startPolling() {
  fetchStatus();
  pollTimer = setInterval(fetchStatus, POLL_MS);
}
function stopPolling() {
  clearInterval(pollTimer);
  pollTimer = null;
}

async function fetchStatus() {
  try {
    const res  = await fetch("/api/status");
    const data = await res.json();
    renderDashboard(data);
  } catch (_) { /* network hiccup, ignore */ }
}

// ── Render dashboard ─────────────────────────────────────────
function renderDashboard(d) {
  // Header status
  if (d.connected) {
    statusDot.className  = "status-dot connected";
    statusText.textContent = "Conectado";
    lastUpdate.textContent = d.last_update ? "Actualizado: " + d.last_update : "";
  } else {
    statusDot.className  = "status-dot error";
    statusText.textContent = d.error ? "Error" : "Sin datos";
  }

  // Sysinfo
  const sysNameEl = document.getElementById("sysName");
  const sysDescrEl = document.getElementById("sysDescr");
  if (sysNameEl) sysNameEl.textContent = d.sysName || "—";
  if (sysDescrEl) sysDescrEl.textContent = d.sysDescr || "—";

  // Uptime
  statUptime.textContent = d.sysUptime || "—";

  // CPU
  const cpu = d.cpu ?? 0;
  statCpu.textContent    = cpu + "%";
  cpuBadge.textContent   = cpu + "%";
  cpuBar.style.width     = Math.min(cpu, 100) + "%";
  cpuBar.style.background = cpu > 80 ? "linear-gradient(90deg,#f85149,#ff7b72)"
                          : cpu > 60 ? "linear-gradient(90deg,#d29922,#e3b341)"
                          :            "linear-gradient(90deg,#1f6feb,#58a6ff)";

  // Memory
  if (d.memory_total > 0) {
    const used  = d.memory_used;
    const total = d.memory_total;
    const pct   = Math.round(used / total * 100);
    statMem.textContent = fmtBytes(used) + " / " + fmtBytes(total);
    memBar.style.width  = pct + "%";
  } else {
    statMem.textContent = "N/D";
    memBar.style.width  = "0%";
  }

  // CPU chart
  if (d.history && d.history.timestamps.length) {
    cpuChart.data.labels  = d.history.timestamps;
    cpuChart.data.datasets[0].data = d.history.cpu;
    cpuChart.update("none");
  }

  // Ports
  const ifaces = d.interfaces || [];
  const operUp = ifaces.filter(i => i.status === "up").length;
  statPorts.textContent = operUp + " / " + ifaces.length;

  renderPorts(ifaces);
  renderTable(ifaces);
}

// ── Port visual ─────────────────────────────────────────────
function renderPorts(ifaces) {
  const container = document.getElementById("portVisual");

  // only recreate on first load or count change
  if (container.children.length !== ifaces.length) {
    container.innerHTML = "";
    ifaces.forEach(iface => {
      const box = document.createElement("div");
      box.className = "port-box";
      box.id = "port-box-" + iface.index;
      box.innerHTML = `
        <div class="port-indicator"></div>
        <div class="port-num">${iface.index}</div>
        <div class="port-speed"></div>`;
      container.appendChild(box);
    });
  }

  ifaces.forEach(iface => {
    const box = document.getElementById("port-box-" + iface.index);
    if (!box) return;

    if (iface.admin === "down") {
      box.className = "port-box admin-down";
    } else if (iface.status === "up") {
      box.className = "port-box up";
    } else {
      box.className = "port-box down";
    }

    const spd = box.querySelector(".port-speed");
    spd.textContent = iface.speed_mbps ? iface.speed_mbps + "M" : "";

    const tooltip = [
      iface.name,
      "Estado: " + iface.status,
      iface.speed_mbps ? "Speed: " + iface.speed_mbps + " Mbps" : "",
      "RX: " + iface.in_mbps  + " Mbps",
      "TX: " + iface.out_mbps + " Mbps",
    ].filter(Boolean).join(" | ");
    box.title = tooltip;
  });
}

// ── Interface table ─────────────────────────────────────────
let allInterfaces = [];

function renderTable(ifaces) {
  allInterfaces = ifaces;
  applyTableFilter();
}

function applyTableFilter() {
  const q = tableSearch.value.toLowerCase();
  const tbody = document.getElementById("ifaceBody");
  tbody.innerHTML = "";

  const filtered = q
    ? allInterfaces.filter(i => i.name.toLowerCase().includes(q) || String(i.index).includes(q))
    : allInterfaces;

  filtered.forEach(iface => {
    const tr = document.createElement("tr");

    const adminBadge  = `<span class="badge ${iface.admin  === "up" ? "badge-up" : "badge-admin"}">${iface.admin}</span>`;
    const statusBadge = `<span class="badge ${iface.status === "up" ? "badge-up" : "badge-down"}">${iface.status}</span>`;
    const speed  = iface.speed_mbps  ? iface.speed_mbps + " Mbps" : "—";
    const inMbps = iface.in_mbps  > 0 ? `<span class="rx-val">${iface.in_mbps.toFixed(3)}</span>` : `<span style="color:var(--text3)">0.000</span>`;
    const outMbps = iface.out_mbps > 0 ? `<span class="tx-val">${iface.out_mbps.toFixed(3)}</span>` : `<span style="color:var(--text3)">0.000</span>`;

    tr.innerHTML = `
      <td>${iface.index}</td>
      <td class="td-name">${iface.name}</td>
      <td>${adminBadge}</td>
      <td>${statusBadge}</td>
      <td>${speed}</td>
      <td>${inMbps}</td>
      <td>${outMbps}</td>
      <td>${iface.in_errors}</td>
      <td>${iface.out_errors}</td>`;
    tbody.appendChild(tr);
  });
}

tableSearch.addEventListener("input", applyTableFilter);

// ── Helpers ─────────────────────────────────────────────────
function showError(msg) { connectError.textContent = msg; }

function setConnecting(on) {
  connectBtn.disabled = on;
  connectBtn.querySelector(".btn-text").style.display = on ? "none" : "";
  connectBtn.querySelector(".btn-spinner").style.display = on ? "" : "none";
}

function showDashboard() {
  connectPanel.style.display = "none";
  dashboard.style.display    = "";
  setConnecting(false);
}

function showConnect() {
  dashboard.style.display    = "none";
  connectPanel.style.display = "";
  statusDot.className  = "status-dot";
  statusText.textContent = "Desconectado";
  lastUpdate.textContent = "—";
  // Reset chart
  cpuChart.data.labels = [];
  cpuChart.data.datasets[0].data = [];
  cpuChart.update();
}

function fmtBytes(b) {
  if (b >= 1024 * 1024) return (b / 1024 / 1024).toFixed(1) + " MB";
  if (b >= 1024)        return (b / 1024).toFixed(1) + " KB";
  return b + " B";
}

function delay(ms) { return new Promise(r => setTimeout(r, ms)); }
