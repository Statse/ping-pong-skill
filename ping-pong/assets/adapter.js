// Optional localhost adapter. Native hosts can use widget.js without this file.
const widget = document.querySelector('ping-pong-animation');
const message = document.querySelector('#message');
let saving = false;
let connected = false;
let timer;
async function request(url, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 2000);
  try {
    const response = await fetch(url, {...options, signal: controller.signal});
    if (!response.ok) throw new Error('Request failed');
    return await response.json();
  } finally { clearTimeout(timeout); }
}
async function poll() {
  try {
    const state = await request('/status');
    connected = true;
    widget.status = state.status;
    if (!saving) widget.enabled = state.enabled;
    message.textContent = '';
    timer = setTimeout(poll, 500);
  } catch (_) {
    connected = false;
    widget.status = 'disconnected';
    message.textContent = 'Rally is no longer connected.';
  }
}
widget.addEventListener('animation-preference', async event => {
  if (!connected) {
    message.textContent = 'Preference not saved: rally is disconnected.';
    return;
  }
  saving = true;
  widget.toggle.disabled = true;
  try {
    await request('/enabled', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify(event.detail)
    });
  } catch (_) {
    message.textContent = 'Preference could not be saved.';
  } finally {
    saving = false;
    widget.toggle.disabled = false;
  }
});
window.addEventListener('pagehide', () => {
  clearTimeout(timer);
  widget.status = 'disconnected';
});
poll();
