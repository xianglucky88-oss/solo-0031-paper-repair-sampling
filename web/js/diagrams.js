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

function asPoints(shape) {
  // A rectangle is [l,t,r,b]; an outline is a list of [x,y] vertices.
  if (shape.length === 4 && typeof shape[0] === 'number') {
    const [x, y, r, b] = shape;
    return [[x, y], [r, y], [r, b], [x, b]];
  }
  return shape;
}

function polygon(shape, cls, label) {
  return svg('polygon', {points: asPoints(shape).map(point => point.join(',')).join(' '), class: cls}, label);
}

function textOf(shape) {
  return asPoints(shape).map(point => point.join(' ')).join(' ; ');
}

function figure(title, dimensions, label, nodes, ...below) {
  const node = el('figure', '', 'plot');
  const caption = el('figcaption');
  caption.append(el('strong', title), el('small', label, 'dim'));
  const [w, h] = dimensions;
  const pad = Math.max(w, h) * .06;
  const plot = svg('svg', {class: 'diagram', viewBox: `${-pad} ${-pad} ${w + 2 * pad} ${h + 2 * pad}`,
    role: 'img', 'aria-label': `${title}，${label}`});
  plot.append(svg('rect', {x: 0, y: 0, width: w, height: h, class: 'page'}), ...nodes);
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
    [...zonesDrawn, ...patches.map(p => polygon(p.destination, 'patch', `补片 ${p.id}`))],
    list(patches, p => [`${p.id} · 贴放 (${textOf(p.destination)})`, `${p.zone} · 第 ${p.revision} 修订 · 试补 ${p.trial} · ${p.shape === 'outline' ? '整片' : '矩形'}`]));
}

export function sheetMap(view, sheetPicker) {
  if (!view) {
    const empty = el('div', '', 'plot');
    empty.append(el('h3', '实物纸页裁切图'), el('p', '尚未登记纸页', 'dim'));
    return empty;
  }
  const {sheet, lot, cuts} = view;
  return figure(`裁切台 · ${sheet.id}`, [sheet.width, sheet.height],
    `${sheet.width} × ${sheet.height} mm · ${lot.active ? '启用' : '已停用'} · 橙：样片 · 绿：补片`,
    cuts.map(c => polygon(c.shape ?? c.cut, c.kind === 'trial' ? 'sample' : 'patch', `${c.document} / ${c.id}`)),
    sheetPicker, list(cuts, c => [`${c.id} · 取纸 (${textOf(c.shape ?? c.cut)})`, `${c.document}/${c.zone} · 第 ${c.revision} 修订`]));
}
