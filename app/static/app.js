// 表单动作与请求反馈。核心规则在后端，这里只做提交与展示。
const state = {
  busy: false,
  lastError: null,
};

function outFor(form) {
  const selector = form.dataset.target;
  return selector ? document.querySelector(selector) : null;
}

function paint(node, text, isError) {
  if (!node) return;
  node.textContent = text;
  node.classList.toggle('err', Boolean(isError));
}

function summarise(payload) {
  if (payload && payload.report) {
    const report = payload.report;
    return [
      `file        ${report.file}`,
      `rows        ${report.count}`,
      `set_version ${report.rate_set_version}`,
      `overlaps    ${report.overlaps.length}`,
      `problems    ${report.problems.length}`,
      `stale       ${report.stale}`,
      report.overlaps.length ? JSON.stringify(report.overlaps[0]) : '',
    ].filter(Boolean).join('\n');
  }
  if (payload && payload.result) {
    return JSON.stringify(payload.result, null, 2);
  }
  return JSON.stringify(payload, null, 2);
}

async function submit(form) {
  if (state.busy) return;
  const target = outFor(form);
  const url = form.dataset.post;
  if (!url) return;
  state.busy = true;
  paint(target, '处理中', false);
  try {
    const response = await fetch(url, { method: 'POST', body: new FormData(form) });
    const payload = await response.json();
    if (!response.ok) {
      paint(target, `${payload.code || response.status} ${payload.detail || ''}`, true);
      return;
    }
    paint(target, summarise(payload), false);
    if (form.dataset.reload === '1') {
      window.setTimeout(() => window.location.reload(), 260);
    }
  } catch (error) {
    paint(target, `请求失败 ${error.message}`, true);
  } finally {
    state.busy = false;
  }
}

function bind() {
  document.querySelectorAll('form[data-post]').forEach((form) => {
    form.addEventListener('submit', (event) => {
      event.preventDefault();
      submit(form);
    });
    const trigger = form.querySelector('button[data-post]');
    if (trigger) {
      trigger.addEventListener('click', (event) => {
        event.preventDefault();
        const previous = form.dataset.post;
        form.dataset.post = trigger.dataset.post;
        submit(form).finally(() => {
          form.dataset.post = previous;
        });
      });
    }
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', bind);
} else {
  bind();
}
