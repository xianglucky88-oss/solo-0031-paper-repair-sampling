import {artifactMap, sheetMap} from './diagrams.js';
import {details, el, section} from './dom.js';
import {action, choice, field, form, integers, options} from './fields.js';
import {stock, stockFields, surface, surfaceFields} from './measurements.js';
import {trialSection} from './trials.js';

export function benchPane(ctx) {
  const {board, zone, sheet, sheetPicker, run, write, save} = ctx;
  if (!board) return [section('现场未选定', el('p', '尚无藏品登记', 'dim'))];
  const maps = el('div', '', 'figures');
  maps.append(artifactMap(board, zone?.id), sheetMap(sheet, sheetPicker));
  const register = details('登记损坏区', form([field('id', '损坏区编号'), field('label', '损坏区名称'),
    {...field('outline', '轮廓顶点 x y；x y (mm)'), wide: true}, ...stockFields, ...surfaceFields('target', '藏品')],
  '登记轮廓', run, values => save(['documents', board.document.id, 'zone'], {expected: board.version,
    data: {id: values.id, label: values.label, outline: values.outline.split(/[;；]/).map(integers),
      stock: stock(values), surface: surface(values, 'target')}}, '损坏区已登记', undefined, values.id)));
  if (!zone) return [maps, section('损坏区', register)];
  if (zone.active === false) {
    const retired = section(zone.label, el('p', `${zone.id} 已拆分至 ${(zone.split_into || []).join(' / ')}，仅作历史记录`, 'readout'), register);
    return [maps, retired];
  }
  const {target, placed, remaining} = zone.coverage;
  const measurement = zone.surface;
  const state = el('p', `${zone.id} · 第 ${zone.revision} 修订 · ${zone.complete ? '完工' : '处理中'}`, 'dim');
  const zoneInfo = section(zone.label, state, el('p', `覆盖 ${placed} / ${target} mm² · 剩余 ${remaining} mm²`, 'readout'),
    el('p', `目标纸面 ${measurement.condition} · Lab × 10：${['l', 'a', 'b'].map(key => measurement.lab[key]).join(' / ')} · 纤维轴 ${zone.stock.grain}`, 'dim'), register);
  const accepted = zone.trials.filter(t => t.status === 'accepted');
  const place = section('裁切与贴放');
  if (zone.complete) {
    place.append(form([field('reason', '复开原因')], '复开本区', run, data => write('reopen', data, '区域已开启新修订')));
  } else {
    if (accepted.length) place.append(form([field('id', '补片编号'), choice('trial', '合格试补', options(accepted)),
      field('cut', '取纸 左 上 右 下 (mm)'), field('origin', '贴放 左 上 (mm)')], '登记补片', run,
    values => write('patch', {id: values.id, trial: values.trial, cut: integers(values.cut),
      origin: integers(values.origin)}, '补片已登记')));
    else place.append(el('p', '本区尚无合格试补', 'dim'));
    const finish = action('确认完工', run, () => write('finish', {}, '区域已完工'));
    finish.disabled = remaining !== 0;
    place.append(finish);
  }
  const split = details('拆区分段交接', form([
    field('firstId', '新编号 A'), {...field('firstOutline', 'A 轮廓 x y；x y (mm)'), wide: true},
    field('secondId', '新编号 B'), {...field('secondOutline', 'B 轮廓 x y；x y (mm)'), wide: true}],
  '提交拆区', run, values => save(['documents', board.document.id, 'split'], {expected: board.version,
    data: {zone: zone.id, zones: [
      {id: values.firstId, outline: values.firstOutline.split(/[;；]/).map(integers)},
      {id: values.secondId, outline: values.secondOutline.split(/[;；]/).map(integers)}]}},
  '损坏区已拆分', board.document.id, values.firstId)));
  const lower = el('div', '', 'split');
  lower.append(trialSection(ctx, zone), place, split);
  return [maps, zoneInfo, lower];
}
