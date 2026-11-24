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
  const {target, placed, remaining} = zone.coverage;
  const measurement = zone.surface;
  const state = el('p', `${zone.id} · 第 ${zone.revision} 修订 · ${zone.complete ? '完工' : '处理中'}`, 'dim');
  const zoneInfo = section(zone.label, state, el('p', `覆盖 ${placed} / ${target} mm² · 剩余 ${remaining} mm²`, 'readout'),
    el('p', `目标纸面 ${measurement.condition} · Lab × 10：${['l', 'a', 'b'].map(key => measurement.lab[key]).join(' / ')} · 纤维轴 ${zone.stock.grain}`, 'dim'),
    ...(zone.withdrawn.length ? [el('p', `已撤下：${zone.withdrawn.map(p => p.id).join('、')}（纸料已消耗，不退回）`, 'dim')] : []),
    register);
  // Pieces available to back a patch: a fresh accepted trial in this revision,
  // or the withdrawn piece's own basis on the same sheet, face and angle.
  const accepted = zone.trials.filter(t => t.status === 'accepted' && t.usable !== false);
  const place = section('裁切与贴放');
  if (zone.complete) {
    // Lift exactly one finished piece while the rest keep covering.
    place.append(form([choice('patch', '本区已完工补片', options(zone.patches)),
      field('reason', '换片原因')], '撤下这一片，开新修订', run,
    values => write('replace', {patch: values.patch, reason: values.reason}, '新修订已开，仅撤下所选补片')));
    place.append(form([field('reason', '复开原因')], '整区复开', run, data => write('reopen', data, '区域已开启新修订')));
  } else {
    if (zone.rework) {
      const lifted = zone.rework.withdrawn_patch;
      place.append(el('p', `本次返工撤下 ${lifted.id} · 待补回贴放 (${lifted.destination.join(', ')})`, 'readout'));
    }
    if (accepted.length) place.append(form([field('id', '补片编号'), choice('trial', '合格试补', options(accepted)),
      field('cut', '取纸 左 上 右 下 (mm)'), field('origin', '贴放 左 上 (mm)')], '登记补片', run,
    values => write('patch', {id: values.id, trial: values.trial, cut: integers(values.cut),
      origin: integers(values.origin)}, '补片已登记')));
    else place.append(el('p', '本区尚无可用试补', 'dim'));
    const finish = action('确认完工', run, () => write('finish', {}, '区域已完工'));
    finish.disabled = remaining !== 0;
    place.append(finish);
  }
  const lower = el('div', '', 'split');
  lower.append(trialSection(ctx, zone), place);
  return [maps, zoneInfo, lower];
}
