import {el, list} from './dom.js';

function svg(tag, attrs, label) {
  const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  if (label) {
    const title = svg('title', {});
    title.textContent = label;
    node.append(title);
  }
  return node;
}

function rectangle([x, y, r, b], cls, label) {
  return svg('rect', {x, y, width: r - x, height: b - y, class: cls}, label);
}

function figure(title, dimensions, label, nodes, ...below) {
  const node = el('figure', '', 'plot');
  const caption = el('figcaption');
  caption.append(el('strong', title), el('small', label, 'dim'));
  const [w, h] = dimensions;
  const pad = Math.max(w, h) * .06;
  const plot = svg('svg', {class: 'diagram', viewBox: `${-pad} ${-pad} ${w + 2 * pad} ${h + 2 * pad}`,
    role: 'img', 'aria-label': `${title}，${label}`});
  plot.append(rectangle([0, 0, w, h], 'page'), ...nodes);
  node.append(caption, plot, ...below);
  return node;
}

export function artifactMap(board, active) {
  const {document: doc, zones} = board;
  const zonesDrawn = zones.map(zone => svg('polygon', {
    points: zone.outline.map(point => point.join(',')).join(' '),
    class: `zone${zone.complete ? ' done' : ''}${zone.id === active ? ' active' : ''}`,
  }, `${zone.id} ${zone.label}`));
  const patches = zones.flatMap(zone => zone.patches);
  return figure('藏品贴放图', [doc.width, doc.height], `${doc.width} × ${doc.height} mm · 橙：待补区 · 绿：补片或完工区`,
    [...zonesDrawn, ...patches.map(p => rectangle(p.destination, 'patch', `补片 ${p.id}`))],
    list(patches, p => [`${p.id} · 贴放 (${p.destination.join(', ')})`, `${p.zone} · 第 ${p.revision} 修订 · 试补 ${p.trial}`]));
}

export function sheetMap(view, sheetPicker) {
  if (!view) {
    const empty = el('div', '', 'plot');
    empty.append(el('h3', '实物纸页裁切图'), el('p', '尚未登记纸页', 'dim'));
    return empty;
  }
  const {sheet, lot, cuts, quota_used, quota_remaining} = view;
  const cutClass = kind => kind === 'trial' ? 'sample' : kind === 'prep' ? 'prep' : 'patch';
  return figure(`裁切台 · ${sheet.id}`, [sheet.width, sheet.height],
    `${sheet.width} × ${sheet.height} mm · ${lot.active ? '启用' : '已停用'} · 取纸笔数 ${quota_used}/${sheet.quota}（剩 ${quota_remaining}）`,
    cuts.map(c => rectangle(c.cut, cutClass(c.kind), `${c.document} / ${c.id}`)),
    sheetPicker, list(cuts, c => [`${c.id} · 取纸 (${c.cut.join(', ')})`,
      `${c.document}/${c.zone} · 第 ${c.revision} 修订 · ${c.kind === 'prep' ? '备料' : c.kind === 'trial' ? '试补' : '补片'}`]));
}
