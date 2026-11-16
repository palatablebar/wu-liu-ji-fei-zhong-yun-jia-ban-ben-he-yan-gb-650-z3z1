// 表格展示：点表头排序、按需加过滤框。只影响显示，不改数据。
const state = { sort: new WeakMap() };

function cellText(row, index) {
  const cell = row.children[index];
  return cell ? cell.textContent.trim() : '';
}

function isNumeric(text) {
  return text !== '' && !Number.isNaN(Number(text.replace(/,/g, '')));
}

function sortBy(table, index, ascending) {
  const body = table.tBodies[0];
  if (!body) return;
  const rows = Array.from(body.rows);
  rows.sort((left, right) => {
    const a = cellText(left, index);
    const b = cellText(right, index);
    if (isNumeric(a) && isNumeric(b)) {
      return ascending
        ? Number(a.replace(/,/g, '')) - Number(b.replace(/,/g, ''))
        : Number(b.replace(/,/g, '')) - Number(a.replace(/,/g, ''));
    }
    return ascending ? a.localeCompare(b, 'zh-Hans-CN') : b.localeCompare(a, 'zh-Hans-CN');
  });
  rows.forEach((row) => body.appendChild(row));
}

function attachSort(table) {
  const headers = table.querySelectorAll('thead th');
  headers.forEach((header, index) => {
    header.addEventListener('click', () => {
      const current = state.sort.get(table) || { index: -1, ascending: false };
      const ascending = current.index === index ? !current.ascending : true;
      state.sort.set(table, { index, ascending });
      sortBy(table, index, ascending);
    });
  });
}

function attachFilter(table) {
  const body = table.tBodies[0];
  if (!body) return;
  const tools = document.createElement('div');
  tools.className = 'table-tools';
  const input = document.createElement('input');
  input.type = 'search';
  input.placeholder = '筛选';
  input.setAttribute('aria-label', '筛选表格行');
  tools.appendChild(input);
  table.parentNode.insertBefore(tools, table);
  input.addEventListener('input', () => {
    const needle = input.value.trim().toLowerCase();
    Array.from(body.rows).forEach((row) => {
      const hit = !needle || row.textContent.toLowerCase().includes(needle);
      row.hidden = !hit;
    });
  });
}

function boot() {
  document.querySelectorAll('table.grid').forEach((table) => {
    attachSort(table);
    if (table.dataset.filter === '1') attachFilter(table);
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', boot);
} else {
  boot();
}
