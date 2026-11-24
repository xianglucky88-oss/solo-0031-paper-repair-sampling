import {details, el, list, section} from './dom.js';
import {choice, field, form, integers, number, options} from './fields.js';

const faces = [['front', '正面'], ['back', '反面']];
const turns = [['0', '0°'], ['90', '90°']];
const disposition = {pending: '待观察', accepted: '合格', failed: '不合格'};
const criteria = {thickness: '厚度', ph: 'pH', grain: '纤维', condition: '测量条件', color: '色差'};
const selected = values => ({sheet: values.sheet, face: values.face, turn: Number(values.turn)});

function judgmentText(judgment) {
  if (!judgment) return '';
  if (judgment.permanently_failed) return '旧规已判不合格，须另开试补';
  if (judgment.authorizing) return '已通过当前规范，可授权补片';
  if (judgment.eligible && !judgment.sample_edge_ok) return '观察齐备，但样片边长不足当前规范，须另开试补';
  if (judgment.eligible && !judgment.face_fit_ok) return '观察齐备，但选面未通过当前规范适配，须另开试补';
  if (judgment.eligible && !judgment.active) return '观察齐备，但纸样批次已停用';
  if (judgment.skipped.length) return `已跳过 ${judgment.skipped.join(' / ')} h，须另开试补`;
  if (judgment.rejected.length) return `${judgment.rejected.join(' / ')} h 不满足当前阈值，须另开试补`;
  if (judgment.next !== null) return `可续记 ${judgment.next} h`;
  return '待观察';
}

export function trialSection(ctx, zone) {
  const {board, catalog, write, inspect, run, sheet} = ctx;
  const rule = board.rule;
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
    const rows = list(trial.rows, r => [`${r.hour} h · 漂移 ${r.drift / 10} · ${r.lifting ? '翘边' : '未翘边'} · ${r.rule || trial.rule}`,
      r.note]);
    const reused = trial.reused_observations || [];
    const summary = `${trial.id} · ${trial.selection.sheet} · ${trial.selection.face === 'front' ? '正面' : '反面'} · `
      + `${trial.selection.turn}° · ${disposition[trial.status]} · 依据 ${trial.rule}`
      + (reused.length ? ` · 复用 ${reused.map(row => `${row.hour} h`).join(' / ')}` : '');
    const block = details(summary, rows, el('p', judgmentText(trial.judgment), 'dim'));
    if (!zone.complete && trial.judgment?.continuable) {
      block.open = true;
      const hour = trial.judgment.next;
      block.append(form([number('drift', `漂移 × 10（限 ${rule.drift}）`, 0), {...field('lifting', '有翘边'), type: 'checkbox'},
        field('note', '观察记录')], `按 ${rule.id} 登记 ${hour} h 观察`, run,
      observation => write('observe', {id: trial.id, observation: {...observation, hour}}, '已登记观察')));
    }
    return block;
  });
  const actions = [];
  if (!zone.complete && available.length) actions.push(details('材料适配预检', preview, result),
    details('切取样片', form([field('id', '试补编号'), ...picks, field('cut', '裁切 左 上 右 下 (mm)')], '开始试补', run,
      values => write('trial', {id: values.id, selection: selected(values), cut: integers(values.cut)}, '样片已切取'))));
  const accepted = zone.trials.filter(t => t.judgment?.authorizing);
  return {node: section('试补记录', el('p', `当前规范 ${rule.id} · 观察 ${rule.hours.join(' / ')} h · `
    + `样片边长 ≥ ${rule.sample_edge} mm · 漂移限值 ${rule.drift / 10}`, 'readout'),
  ...histories, ...actions), accepted};
}
