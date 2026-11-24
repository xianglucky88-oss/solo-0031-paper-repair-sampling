import {request} from './api.js';
import {benchPane} from './bench.js';
import {catalogPane} from './catalog.js';
import {action, choice, input, options} from './fields.js';
import {releasePane} from './releases.js';

const panes = {bench: benchPane, catalog: catalogPane, release: releasePane};
const nav = [...document.querySelectorAll('[data-pane]')];
const context = document.querySelector('#context');
const status = document.querySelector('#status');
const content = document.querySelector('#pane');
let state = {};
let current = 'bench';
let busy = false;

function message(text, error = false) {
  status.textContent = text || '';
  status.classList.toggle('error', error);
}

async function run(button, task) {
  if (busy) return;
  busy = true;
  if (button) button.disabled = true;
  message('处理中…');
  try {
    message(await task());
  } catch (err) {
    message(err.message || '请求失败', true);
  } finally {
    if (button) button.disabled = false;
    busy = false;
  }
}

async function refresh(doc = state.doc, zoneId = state.zone?.id, sheetId = state.sheet?.sheet.id) {
  const catalog = await request(['catalog']);
  doc = catalog.documents.some(d => d.id === doc) ? doc : catalog.documents[0]?.id;
  sheetId = catalog.sheets.some(s => s.id === sheetId) ? sheetId : catalog.sheets[0]?.id;
  const [board, sheet] = await Promise.all([doc && request(['documents', doc]), sheetId && request(['sheets', sheetId])]);
  const zone = board?.zones.find(z => z.id === zoneId) || board?.zones[0];
  state = {doc, board, zone, sheet, catalog};
  render();
}

async function save(parts, body, text, doc, zoneId) {
  await request(parts, body);
  try {
    await refresh(doc, zoneId);
  } catch (err) {
    throw new Error(`${text}，但刷新失败：${err.message}`);
  }
  return text;
}

function select(spec, change) {
  const [label, control] = input(spec);
  control.addEventListener('change', async () => {
    const value = control.value;
    const previous = spec.value;
    control.value = previous;
    await run(control, () => change(value));
  });
  return label;
}

function render() {
  const {doc, board, zone, sheet, catalog} = state;
  const contextNodes = [];
  if (doc) contextNodes.push(select(choice('document', '当前藏品', options(catalog.documents, row => `${row.id} · ${row.title}`), doc),
    async value => { await refresh(value, null); return `已切换至 ${value}`; }));
  if (zone && current === 'bench') contextNodes.push(select(choice('zone', '损坏区', options(board.zones, row => `${row.id} · ${row.label}`), zone.id),
    value => {state.zone = board.zones.find(z => z.id === value); render(); return ''; }));
  contextNodes.push(action('↻ 刷新现场', run, async () => { await refresh(); return '已刷新现场'; }));
  context.replaceChildren(...contextNodes);
  const sheetPicker = sheet && select(choice('sheet', '查看实物纸页', options(catalog.sheets), sheet.sheet.id),
    async value => { await refresh(doc, zone?.id, value); return `已读取 ${value} 裁切记录`; });
  const inspect = (tail, body) => request(['documents', doc, ...tail], body);
  const write = (name, data, text) => save(['documents', doc, name], {expected: board.version, zone: zone.id, data}, text);
  content.replaceChildren(...panes[current]({...state, run, save, write, inspect, sheetPicker}));
}

for (const button of nav) button.addEventListener('click', () => {
  if (busy || !state.catalog) return;
  current = button.dataset.pane;
  for (const item of nav) item.setAttribute('aria-pressed', item === button);
  message('');
  render();
});

run(null, () => refresh());
