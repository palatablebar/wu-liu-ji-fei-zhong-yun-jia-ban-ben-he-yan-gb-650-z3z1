// 比例条：原因分布按最大值归一，分项构成按合计归一。纯展示。
function renderBars() {
  document.querySelectorAll('.bars').forEach((group) => {
    const fills = Array.from(group.querySelectorAll('.bar-fill'));
    const counts = fills.map((node) => Number(node.dataset.count || 0));
    const peak = Math.max(...counts, 1);
    fills.forEach((node, index) => {
      if (node.style.width) return;
      node.style.width = `${Math.round((counts[index] / peak) * 100)}%`;
    });
  });
}

function renderStacks() {
  document.querySelectorAll('.stack[data-stack]').forEach((group) => {
    let parts;
    try {
      parts = JSON.parse(group.dataset.stack);
    } catch (error) {
      group.textContent = '';
      return;
    }
    const entries = Object.entries(parts).map(([key, value]) => [key, Number(value) || 0]);
    const total = entries.reduce((sum, [, value]) => sum + value, 0);
    group.textContent = '';
    entries.forEach(([key, value]) => {
      const span = document.createElement('span');
      span.title = `${key} ${value.toFixed(2)}`;
      span.style.width = total > 0 ? `${(value / total) * 100}%` : '0%';
      group.appendChild(span);
    });
  });
}

function boot() {
  renderBars();
  renderStacks();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', boot);
} else {
  boot();
}
