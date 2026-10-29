const $ = (id) => document.getElementById(id);
let lastPayload = '';

function value(value, fallback = '—') {
  return value === null || value === undefined ? fallback : value;
}

function timeLabel(value) {
  if (!value) return 'Unknown time';
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : date.toLocaleString();
}

function drawChart(history) {
  const canvas = $('temperatureChart');
  const ctx = canvas.getContext('2d');
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  const ratio = window.devicePixelRatio || 1;
  canvas.width = width * ratio;
  canvas.height = height * ratio;
  ctx.scale(ratio, ratio);
  ctx.clearRect(0, 0, width, height);

  const points = history.map(row => Number(row.temperature_c)).filter(Number.isFinite);
  ctx.strokeStyle = 'rgba(148,163,184,.14)';
  ctx.lineWidth = 1;
  for (let i = 1; i < 5; i++) {
    const y = height * i / 5;
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(width, y); ctx.stroke();
  }
  if (!points.length) return;
  const min = Math.min(...points) - 1;
  const max = Math.max(...points) + 1;
  ctx.beginPath();
  points.forEach((point, index) => {
    const x = points.length === 1 ? width / 2 : index * width / (points.length - 1);
    const y = height - ((point - min) / (max - min || 1)) * (height - 30) - 15;
    index ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
  });
  ctx.strokeStyle = '#5b67f1'; ctx.lineWidth = 3;
  ctx.lineJoin = 'round'; ctx.lineCap = 'round'; ctx.stroke();

  ctx.fillStyle = '#5b67f1';
  points.forEach((point, index) => {
    const x = points.length === 1 ? width / 2 : index * width / (points.length - 1);
    const y = height - ((point - min) / (max - min || 1)) * (height - 30) - 15;
    ctx.beginPath(); ctx.arc(x, y, 3, 0, Math.PI * 2); ctx.fill();
  });
}

function updateState() {
  fetch('/api/state').then(response => {
    if (response.status === 401) { window.location.href = '/login'; return null; }
    return response.json();
  }).then(state => {
    if (!state) return;
    const badge = $('mqttBadge');
    badge.className = 'status-pill ' + (state.mqtt === 'connected' ? 'online' : 'offline');
    badge.innerHTML = `<span></span>${state.mqtt}`;
    const latest = state.latest;
    if (latest) {
      const payload = JSON.stringify(latest);
      $('temperature').textContent = value(latest.temperature_c);
      $('humidity').textContent = value(latest.humidity_percent);
      $('pressure').textContent = value(latest.pressure_hpa);
      $('humiditySource').textContent = latest.humidity_percent == null ? 'Unavailable · BMP280 has no humidity sensor' : (latest.humidity_source === 'demo' ? 'Demo value' : 'Relative humidity');
      $('distance').textContent = value(latest.distance_cm);
      $('vibration').textContent = latest.vibration ? 'Detected' : 'Clear';
      $('vibrationState').textContent = latest.vibration ? 'Movement sensor active' : 'No vibration detected';
      $('temperatureSource').textContent = latest.bmp280_source === 'demo' ? 'Demo value · sensor unavailable' : (latest.bmp280_source === 'sensor' ? 'BMP280 live reading' : 'Sensor unavailable');
      $('lastSeen').textContent = 'Last update: ' + timeLabel(latest.received_at || latest.timestamp);
      const alerts = Array.isArray(latest.alerts) ? latest.alerts.filter(Boolean) : [];
      $('boxStatus').textContent = alerts.length ? alerts.join(' · ') : 'Box is secure';
      $('alarmIcon').textContent = alerts.length ? '!' : '✓';
      if (alerts.length && payload !== lastPayload) {
        $('alertsList').innerHTML = alerts.map(alert => `<div class="alert-item"><span>!</span><p>${escapeHtml(alert)}</p></div>`).join('');
      } else if (!alerts.length) {
        $('alertsList').innerHTML = '<div class="alert-item safe"><span>✓</span><p>No active alerts</p></div>';
      }
      lastPayload = payload;
    }
    drawChart(state.history || []);
    $('messageList').innerHTML = (state.messages || []).map(item => `
      <div class="message-item"><span class="message-action">${escapeHtml(item.action)}</span><p>${escapeHtml(item.text)}</p><time>${timeLabel(item.sent_at)}</time></div>`
    ).join('') || '<p class="empty-state">No messages sent yet.</p>';
  }).catch(() => {
    $('mqttBadge').className = 'status-pill offline';
    $('mqttBadge').innerHTML = '<span></span>dashboard offline';
  });
}

function escapeHtml(value) {
  const node = document.createElement('div');
  node.textContent = value ?? '';
  return node.innerHTML;
}

$('messageForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  const button = event.currentTarget.querySelector('button');
  button.disabled = true;
  const response = await fetch('/api/message', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({action: $('action').value, text: $('messageText').value})
  });
  const result = await response.json();
  const feedback = $('sendFeedback');
  feedback.textContent = result.error || 'Message sent successfully.';
  feedback.className = 'send-feedback ' + (result.error ? 'error' : 'success');
  if (!result.error) $('messageText').value = '';
  button.disabled = false;
  updateState();
});

window.addEventListener('resize', updateState);
updateState();
setInterval(updateState, 3000);
