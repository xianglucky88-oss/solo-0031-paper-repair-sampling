import {details, list, section} from './dom.js';
import {choice, field, form, integers, number, options} from './fields.js';
import {stock, stockFields, surface, surfaceFields} from './measurements.js';

const axes = ['l', 'a', 'b'];

function handoverFields() {
  const range = axis => [number(`${axis}Low`, `${axis.toUpperCase()} 量程下限`),
    number(`${axis}High`, `${axis.toUpperCase()} 量程上限`)];
  const delta = axis => number(`${axis}Delta`, `${axis.toUpperCase()} 增减量`);
  return [
    field('id', '交接单编号'), number('version', '版本号', 1),
    field('source_condition', '来源测量条件', 'D65'), field('target_condition', '目标测量条件', 'D50'),
    number('max_error', '换算最大误差 × 10', 1), number('effective_at', '生效现场版本', 0),
    ...axes.flatMap(range), ...axes.map(delta),
  ];
}

function handoverBody(values) {
  return {
    id: values.id, version: values.version,
    source_condition: values.source_condition, target_condition: values.target_condition,
    max_error: values.max_error, effective_at: values.effective_at,
    ranges: Object.fromEntries(axes.map(axis =>
      [axis, {low: values[`${axis}Low`], high: values[`${axis}High`]}])),
    deltas: Object.fromEntries(axes.map(axis => [axis, values[`${axis}Delta`]])),
  };
}

export function catalogPane(ctx) {
  const {catalog: {rules, documents, lots, sheets, handovers = []}, run, save} = ctx;
  const id = field('id', '编号');
  const dimensions = [number('width', '宽 mm'), number('height', '高 mm')];
  const handoverList = list(handovers, row => [
    `${row.id} r${row.version} · ${row.source_condition} → ${row.target_condition}`,
    `生效 v${row.effective_at} · 最大误差 ${row.max_error} · 增减 L${row.deltas.l}/a${row.deltas.a}/b${row.deltas.b}`,
  ]);
  return [
    section('规则与藏品',
      list(rules, row => [row.id, `观察 ${row.hours.join(' / ')} h · 样片边长 ≥ ${row.sample_edge} mm`]),
      details('登记规则', form([id, number('thickness_gap', '厚度差 μm', 18), number('ph_gap', 'pH 差 × 10', 5),
        number('color_gap', '色差限值 × 10', 35), field('hours', '观察时间点 h', '0 24'),
        number('drift', '试补漂移限值 × 10', 20), number('sample_edge', '样片最小边 mm', 5)], '冻结规则', run,
      values => save(['rules'], {...values, hours: integers(values.hours)}, '规则已冻结'))),
      list(documents, row => [row.title, `${row.id} · ${row.width} × ${row.height} mm · ${row.rule.id}`]),
      details('登记藏品', form([id, field('title', '藏品名称'), ...dimensions,
        choice('rule', '规则版', options(rules))], '登记藏品', run,
        values => save(['documents'], values, '藏品已登记', values.id)))),
    section('标定交接单', handoverList,
      details('登记交接单', form(handoverFields(), '发布交接单', run,
        values => save(['handovers'], handoverBody(values), '交接单已发布')))),
    section('批次与纸页',
      list(lots, row => [row.label, `${row.id} · ${row.active ? '启用' : `停用：${row.reason}`}`]),
      details('登记批次', form([id, field('label', '批次名称')], '登记批次', run,
        values => save(['lots'], values, '批次已登记'))),
      details('停用批次', form([choice('id', '批次', options(lots.filter(row => row.active))), field('reason', '停用原因')],
        '停用批次', run, values => save(['retire'], values, '批次已停用'))),
      list(sheets, row => [row.id, `${row.width} × ${row.height} mm · ${row.lot} · 正面 ${row.faces.front.condition} / 反面 ${row.faces.back.condition}`]),
      details('登记纸页', form([id, choice('lot', '批次', options(lots.filter(row => row.active))), ...dimensions,
        ...stockFields, ...surfaceFields('front', '正面'), ...surfaceFields('back', '反面')], '登记纸页', run,
      values => save(['sheets'], {id: values.id, lot: values.lot, width: values.width, height: values.height,
        stock: stock(values), faces: {front: surface(values, 'front'), back: surface(values, 'back')}}, '纸页已登记')))),
  ];
}
