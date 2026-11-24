export function el(tag, text = '', className = '') {
  const node = document.createElement(tag);
  node.textContent = text;
  if (className) node.className = className;
  return node;
}

export function section(title, ...children) {
  const node = el('section', '', 'band');
  node.append(el('h2', title), ...children);
  return node;
}

export function details(label, ...children) {
  const node = el('details');
  node.append(el('summary', label), ...children);
  return node;
}

export function list(items, describe) {
  const node = el('ul', '', 'ledger');
  for (const item of items) {
    const [title, sub] = describe(item);
    const line = el('li', title);
    if (sub) line.append(el('small', sub));
    node.append(line);
  }
  return node;
}

export function json(value) {
  return el('pre', JSON.stringify(value, null, 2));
}
