import {details, el, list, section} from './dom.js';
import {choice, field, form, integers, number, options} from './fields.js';

const faces = [['front', '正面'], ['back', '反面']];
const turns = [['0', '0°'], ['90', '90°']];
const disposition = {pending: '待观察', accepted: '合格', failed: '不合格'};
const criteria = {thickness: '厚度', ph: 'pH', grain: '纤维', condition: '测量条件', color: '色差'};
const selected = values => ({sheet: values.sheet, face: values.face, turn: Number(values.turn)});

export function trialSection(ctx, zone) {
  const {board, catalog, write, inspect, run, sheet} = ctx;
  const active = new Set(catalog.lots.filter(row => row.active).map(row => row.id));
  const available = catalog.sheets.filter(row => active.has(row.lot));
  const sheetChoice = available.some(row => row.id === sheet?.sheet.id) ? sheet.sheet.id : undefined;
  const picks = [choice('sheet', '实物纸页', options(available), sheetChoice),
    choice('face', '纸面', faces), choice('turn', '旋转', turns)];
  const result = el('p', '', 'readout');
  result.hidden = true;
  result.setAttribute('aria-live', 'polite');
  const preview = form(picks, '预检面向', run, async values => {
    const data = await inspect(['preview'], {zone: zone.id, selection: selected(values)});
    result.textContent = Object.entries(data.checks).map(([key, value]) =>
      `${criteria[key]}：${value === null ? '不可比较' : value ? '合格' : '不合格'}`).join(' · ');
    result.hidden = false;
    return data.compatible ? '该面向通过适配评估' : '该面向未通过适配评估';
  });
  const histories = zone.trials.map(trial => {
    const rows = list(trial.rows, r => [`${r.hour} h · 漂移 ${r.drift / 10} · ${r.lifting ? '翘边' : '未翘边'}`, r.note]);
    const summary = `${trial.id} · ${trial.selection.sheet} · ${trial.selection.face === 'front' ? '正面' : '反面'} · ${trial.selection.turn}° · ${disposition[trial.status]}${trial.used ? ' · 已整块贴用' : ''}`;
    const block = details(summary, rows);
    if (!zone.complete && trial.status === 'pending') {
      block.open = true;
      const hour = board.document.rule.hours[trial.rows.length];
      block.append(form([number('drift', '漂移 × 10', 0), {...field('lifting', '有翘边'), type: 'checkbox'},
        field('note', '观察记录')], `登记 ${hour} h 观察`, run,
      observation => write('observe', {id: trial.id, observation: {...observation, hour}}, '已登记观察')));
    }
    return block;
  });
  const actions = [];
  if (!zone.complete && available.length) actions.push(details('材料适配预检', preview, result),
    details('切取样片', form([field('id', '试补编号'), ...picks, field('cut', '裁切 左 上 右 下 (mm)')], '开始试补', run,
      values => write('trial', {id: values.id, selection: selected(values), cut: integers(values.cut)}, '样片已切取'))));
  return section('试补记录', ...histories, ...actions);
}
