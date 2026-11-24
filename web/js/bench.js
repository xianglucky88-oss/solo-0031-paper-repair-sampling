import {artifactMap, sheetMap} from './diagrams.js';
import {details, el, list, section} from './dom.js';
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
  const used = zone.used_samples || [];
  const usage = used.length ? list(used, sample => [
    `试样 ${sample.trial} 已整块贴用 · 第 ${sample.revision} 修订`,
    `${sample.selection.sheet} · ${sample.selection.face === 'front' ? '正面' : '反面'} · ${sample.selection.turn}° · 取纸 (${sample.cut.join(', ')}) · 贴放 ${sample.mounts.map(m => `(${m.origin.join(', ')})`).join(' ')}`,
  ]) : null;
  const zoneInfo = section(zone.label, state, el('p', `覆盖 ${placed} / ${target} mm² · 剩余 ${remaining} mm²`, 'readout'),
    el('p', `目标纸面 ${measurement.condition} · Lab × 10：${['l', 'a', 'b'].map(key => measurement.lab[key]).join(' / ')} · 纤维轴 ${zone.stock.grain}`, 'dim'),
    usage, register);
  const accepted = zone.trials.filter(t => t.status === 'accepted');
  const place = section('裁切与贴放');
  if (zone.complete) {
    place.append(form([field('reason', '复开原因')], '复开本区', run, data => write('reopen', data, '区域已开启新修订')));
  } else {
    if (accepted.length) {
      const fresh = accepted.filter(trial => !trial.used);
      if (fresh.length) place.append(form([field('id', '贴用编号'), choice('trial', '已观察试样', options(fresh,
        trial => `${trial.id} · 取纸 ${trial.allocation.cut.join(' ')}`)), field('origin', '贴放 左 上 (mm)')],
      '整块贴用试样', run, values => write('mount', {id: values.id, trial: values.trial, origin: integers(values.origin)},
        '试样已整块贴用，按实际覆盖计入')));
      else place.append(el('p', '本区合格试样均已贴用，可另裁新片', 'dim'));
      place.append(form([field('id', '补片编号'), choice('trial', '合格试补', options(accepted)),
        field('cut', '取纸 左 上 右 下 (mm)'), field('origin', '贴放 左 上 (mm)')], '登记补片', run,
      values => write('patch', {id: values.id, trial: values.trial, cut: integers(values.cut),
        origin: integers(values.origin)}, '补片已登记')));
    } else place.append(el('p', '本区尚无合格试补', 'dim'));
    const finish = action('确认完工', run, () => write('finish', {}, '区域已完工'));
    finish.disabled = remaining !== 0;
    place.append(finish);
  }
  const lower = el('div', '', 'split');
  lower.append(trialSection(ctx, zone), place);
  return [maps, zoneInfo, lower];
}
