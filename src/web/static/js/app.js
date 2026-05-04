/**
 * MAC_ASD v13.0 — Web UI JavaScript
 * Shared utilities for all pages.
 */

// System status poll
async function checkSystemStatus() {
    try {
        const resp = await fetch('/api/status');
        const data = await resp.json();
        const dot = document.querySelector('.status-dot');
        const text = document.getElementById('system-status');
        if (dot && text) {
            dot.className = 'status-dot online';
            text.textContent = 'v' + data.version + ' / ' + data.profile;
        }
    } catch {
        const dot = document.querySelector('.status-dot');
        const text = document.getElementById('system-status');
        if (dot && text) {
            dot.className = 'status-dot offline';
            text.textContent = 'Нет соединения';
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    checkSystemStatus();
    setInterval(checkSystemStatus, 60000);
});

// Format bytes
function formatBytes(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

// Format date
function formatDate(iso) {
    if (!iso) return '—';
    return new Date(iso).toLocaleDateString('ru-RU');
}
