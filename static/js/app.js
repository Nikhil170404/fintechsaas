// Live clock on dashboard
const timeEl = document.getElementById('current-time');
if (timeEl) {
  function tick() {
    const now = new Date();
    timeEl.textContent = now.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' });
  }
  tick();
  setInterval(tick, 60000);
}

// Auto-dismiss flash messages after 5s
document.querySelectorAll('.alert.alert-success, .alert.alert-info').forEach(el => {
  setTimeout(() => {
    const bsAlert = bootstrap.Alert.getOrCreateInstance(el);
    bsAlert.close();
  }, 5000);
});
