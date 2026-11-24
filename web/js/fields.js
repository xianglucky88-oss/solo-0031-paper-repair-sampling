import {el} from './dom.js';

export const field = (name, label, value = '') => ({name, label, value});
export const number = (name, label, value) => ({name, label, value, type: 'number'});
export const choice = (name, label, options, value) => ({name, label, options, value});
export const options = (rows, describe = row => row.id) => rows.map(row => [row.id, describe(row)]);
let fieldId = 0;

export function input(spec) {
  const label = el('label', '', spec.wide ? 'wide' : '');
  const caption = el('span', spec.label);
  caption.id = `field-caption-${++fieldId}`;
  const node = el(spec.options ? 'select' : 'input');
  node.setAttribute('aria-labelledby', caption.id);
  node.name = spec.name;
  node.required = spec.type !== 'checkbox';
  if (spec.options) {
    for (const [value, text] of spec.options) {
      const option = el('option', text);
      option.value = value;
      node.append(option);
    }
  } else {
    node.type = spec.type || 'text';
    if (node.type === 'checkbox') node.checked = Boolean(spec.value);
    if (node.type === 'number') node.step = '1';
  }
  if (spec.value !== undefined && spec.type !== 'checkbox') node.value = spec.value;
  label.append(caption, node);
  return [label, node];
}

export function form(specs, label, run, operation) {
  const wrapper = el('form');
  const grid = el('div', '', 'fields');
  const nodes = specs.map(input);
  grid.append(...nodes.map(([label]) => label));
  const submit = el('button', label);
  submit.type = 'submit';
  wrapper.append(grid, submit);
  wrapper.addEventListener('submit', event => {
    event.preventDefault();
    const values = Object.fromEntries(nodes.map(([, node]) => [node.name,
      node.type === 'number' ? node.valueAsNumber : node.type === 'checkbox' ? node.checked : node.value]));
    run(submit, () => operation(values));
  });
  return wrapper;
}

export function integers(text) {
  const parts = text.trim().split(/[\s,，]+/);
  if (parts.some(part => !/^-?\d+$/.test(part) || !Number.isSafeInteger(Number(part)))) {
    throw new Error('坐标或时间点须为整数');
  }
  return parts.map(Number);
}

export function action(label, run, handler) {
  const button = el('button', label);
  button.type = 'button';
  button.addEventListener('click', () => run(button, handler));
  return button;
}
