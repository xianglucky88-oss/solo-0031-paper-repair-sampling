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
  const rule = board.rule;
  const rules = board.rules || [];
  const ruleInfo = el('p', `当前规范 ${rule.id} · 观察 ${rule.hours.join(' / ')} h · 样片边长 ≥ ${rule.sample_edge} mm · `
    + `漂移限值 ${rule.drift / 10}`, 'dim');
  const historyList = list(rules, entry => [`${entry.rule.id} · 自现场 v${entry.from} 起`,
    `观察 ${entry.rule.hours.join(' / ')} h · 边长 ≥ ${entry.rule.sample_edge} mm · 漂移 ${entry.rule.drift / 10}`]);
  const applied = new Set(rules.map(entry => entry.rule.id));
  const candidates = (ctx.catalog.rules || []).filter(row => !applied.has(row.id));
  const switchRule = candidates.length ? details('采用新规范',
    el('p', '自下一个现场版本起生效；已取纸、既有观察与已贴补片不改记，旧样片占用不释放。', 'dim'),
    form([choice('rule', '新规范', options(candidates))], '从下一步采用', run,
      values => save(['documents', board.document.id, 'adopt'], {expected: board.version,
        data: {rule: values.rule}}, `已自下一步起采用 ${values.rule}`))) : null;
  const zoneInfo = section(zone.label, state, el('p', `覆盖 ${placed} / ${target} mm² · 剩余 ${remaining} mm²`, 'readout'),
    el('p', `目标纸面 ${measurement.condition} · Lab × 10：${['l', 'a', 'b'].map(key => measurement.lab[key]).join(' / ')} · 纤维轴 ${zone.stock.grain}`, 'dim'),
    ruleInfo, details('规范修订记录', historyList, switchRule || el('p', '尚无其他规范可切换', 'dim')), register);
  const trialBlock = trialSection(ctx, zone);
  const accepted = trialBlock.accepted;
  const place = section('裁切与贴放');
  if (zone.complete) {
    place.append(form([field('reason', '复开原因')], '复开本区', run, data => write('reopen', data, '区域已开启新修订')));
  } else {
    if (accepted.length) place.append(form([field('id', '补片编号'), choice('trial', '合格试补', options(accepted)),
      field('cut', '取纸 左 上 右 下 (mm)'), field('origin', '贴放 左 上 (mm)')], '登记补片', run,
    values => write('patch', {id: values.id, trial: values.trial, cut: integers(values.cut),
      origin: integers(values.origin)}, '补片已登记')));
    else place.append(el('p', '本区尚无通过当前规范的试补', 'dim'));
    const finish = action('确认完工', run, () => write('finish', {}, '区域已完工'));
    finish.disabled = remaining !== 0;
    place.append(finish);
  }
  const lower = el('div', '', 'split');
  lower.append(trialBlock.node, place);
  return [maps, zoneInfo, lower];
}
