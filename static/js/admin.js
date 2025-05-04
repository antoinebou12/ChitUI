// static/js/admin.js

// Elements
const uptimeEl       = document.getElementById("uptime");
const printersEl     = document.getElementById("connectedPrinters");
const refreshLogsBtn = document.getElementById("refreshLogs");
const clearLogsBtn   = document.getElementById("clearLogs");
const logContentEl   = document.getElementById("logContent");
const logLevelSelect = document.getElementById("logLevel");

let lastHealth = null;

/**
 * Fetch health (uptime) and printer count.
 */
async function fetchStatus() {
  try {
    const [healthResp, printersResp] = await Promise.all([
      fetch("/api/health").then(r => r.json()),
      fetch("/api/printer/list").then(r => r.json())
    ]);

    if (healthResp.success) {
      lastHealth = healthResp.data.uptime;  // total seconds since boot
    }
    if (printersResp.success) {
      printersEl.textContent = Object.keys(printersResp.data).length;
    }
  } catch (err) {
    console.error("Error fetching status:", err);
    lastHealth = null;
    printersEl.textContent = "Error";
  }
}

/**
 * Render the uptime (with seconds) from lastHealth.
 */
function renderUptime() {
  if (typeof lastHealth !== "number") {
    uptimeEl.textContent = "Error";
    return;
  }
  // add the number of seconds elapsed since we fetched lastHealth
  const now = Math.floor((Date.now() / 1000));
  const elapsed = lastHealth + (now - Math.floor(lastHealthFetchTime));
  // But to keep it simpler: just use lastHealth and tick upwards every second.
  const secs = lastHealth + (Math.floor((Date.now() - lastHealthFetchTimeMs) / 1000));
  const days    = Math.floor(secs / 86400);
  const hours   = Math.floor((secs % 86400) / 3600);
  const mins    = Math.floor((secs % 3600) / 60);
  const seconds = secs % 60;
  uptimeEl.textContent = `${days}d ${hours}h ${mins}m ${seconds}s`;
}

// We’ll store the wall‐clock time when we fetched lastHealth
let lastHealthFetchTime    = 0;
let lastHealthFetchTimeMs  = 0;

/**
 * Fetch & render right away.
 */
async function refreshStatus() {
  await fetchStatus();
  lastHealthFetchTime   = Math.floor(Date.now() / 1000) - lastHealth;
  lastHealthFetchTimeMs = Date.now() - (lastHealth * 1000);
  renderUptime();
}

// Logs code unchanged…
async function refreshLogs() {
  logContentEl.textContent = "Loading logs…";
  try {
    const resp = await fetch("/api/logs");
    const json = await resp.json();
    if (!json.success || !json.data?.lines) {
      logContentEl.textContent = "Failed to load logs.";
      return;
    }
    const level = logLevelSelect.value;
    const lines = json.data.lines;
    const filtered = level === "all"
      ? lines
      : lines.filter(l => l.toLowerCase().includes(level));
    logContentEl.textContent = filtered.length
      ? filtered.join("")
      : `No ${level.toUpperCase()} entries.`;
  } catch (err) {
    console.error("Error fetching logs:", err);
    logContentEl.textContent = "Error fetching logs.";
  }
}

function clearLogs() {
  logContentEl.textContent = "";
}

document.addEventListener("DOMContentLoaded", () => {
  // initial fetch
  refreshStatus();
  refreshLogs();

  // re-fetch health & printers every 30s
  setInterval(refreshStatus, 30_000);

  // but tick the uptime display every second
  setInterval(renderUptime, 1000);

  // logs UI
  refreshLogsBtn.addEventListener("click", refreshLogs);
  clearLogsBtn.addEventListener("click", clearLogs);
  logLevelSelect.addEventListener("change", refreshLogs);
});


// Restart‐Server button
const restartBtn = document.getElementById('restartServer');
if (restartBtn) {
  restartBtn.addEventListener('click', async (e) => {
    e.preventDefault();
    if (!confirm('Really restart the server? All connections will drop.')) return;

    restartBtn.disabled = true;
    restartBtn.innerHTML = '<i class="bi bi-arrow-clockwise me-1"></i> Restarting…';

    try {
      const resp = await fetch('/admin/restart', { method: 'POST' });
      const json = await resp.json();
      if (json.success) {
        alert(json.message);
      } else {
        alert('Failed to restart: ' + (json.error?.message || resp.statusText));
        restartBtn.disabled = false;
        restartBtn.textContent = 'Restart Server';
      }
    } catch (err) {
      console.error(err);
      alert('Error communicating with server.');
      restartBtn.disabled = false;
      restartBtn.textContent = 'Restart Server';
    }
  });
}
