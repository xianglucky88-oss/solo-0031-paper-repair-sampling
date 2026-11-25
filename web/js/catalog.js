import {details, list, section} from './dom.js';
import {action, choice, field, form, integers, number, options} from './fields.js';
import {stock, stockFields, surface, surfaceFields} from './measurements.js';

const halfTurns = [['0', '同向 · 0°'], ['180', '纸面内转半圈 · 180°']];

export function catalogPane(ctx) {
  const {catalog: {rules, documents, lots, sheets, splits = []}, run, save} = ctx;
  const id = field('id', '编号');
  const dimensions = [number('width', '宽 mm'), number('height', '高 mm')];
  const splittable = sheets.filter(row => row.state !== 'split' && !row.split);
  return [
    section('规则与藏品', list(rules, row => [row.id, `观察 ${row.hours.join(' / ')} h · 样片边长 ≥ ${row.sample_edge} mm`]),
      details('登记规则', form([id, number('thickness_gap', '厚度差 μm', 18), number('ph_gap', 'pH 差 × 10', 5),
        number('color_gap', '色差限值 × 10', 35), field('hours', '观察时间点 h', '0 24'),
        number('drift', '试补漂移限值 × 10', 20), number('sample_edge', '样片最小边 mm', 5)], '冻结规则', run,
      values => save(['rules'], {...values, hours: integers(values.hours)}, '规则已冻结'))),
      list(documents, row => [row.title, `${row.id} · ${row.width} × ${row.height} mm · ${row.rule.id}`]),
      details('登记藏品', form([id, field('title', '藏品名称'), ...dimensions,
        choice('rule', '规则版', options(rules))], '登记藏品', run, values => save(['documents'], values, '藏品已登记', values.id)))),
    section('批次与纸页', list(lots, row => [row.label, `${row.id} · ${row.active ? '启用' : `停用：${row.reason}`}`]),
      details('登记批次', form([id, field('label', '批次名称')], '登记批次', run, values => save(['lots'], values, '批次已登记'))),
      details('停用批次', form([choice('id', '批次', options(lots.filter(row => row.active))), field('reason', '停用原因')],
        '停用批次', run, values => save(['retire'], values, '批次已停用'))),
      list(sheets, row => [row.id, `${row.width} × ${row.height} mm · ${row.lot} · 正面 ${row.faces.front.condition} / 反面 ${row.faces.back.condition}` +
        (row.state === 'split' || row.split ? ' · 已分张，原编号不可新裁' : '') +
        (row.lineage ? ` · 原页 ${row.lineage.root} · 累积转向 ${row.lineage.root_turn ?? row.lineage.turn}°` : '')]),
      details('纸页分张', form([
        choice('sheet', '待分原页', options(splittable)),
        choice('axis', '分线方向', [['x', '竖直线：固定横坐标 x'], ['y', '水平线：固定纵坐标 y']], 'x'),
        number('at', '实际分线位置 mm', 20),
        field('left_id', '左/上张编号'),
        choice('left_turn', '左/上张方向', halfTurns, '0'),
        field('right_id', '右/下张编号'),
        choice('right_turn', '右/下张方向', halfTurns, '180'),
      ], '登记分张', run, values => save(['sheets', values.sheet, 'split'], {
        axis: values.axis,
        at: values.at,
        left: {id: values.left_id, turn: Number(values.left_turn)},
        right: {id: values.right_id, turn: Number(values.right_turn)},
      }, '分张已登记；旧切口仍按原页坐标核对'))),
      list(splits, row => [`分线 ${row.sheet} @ ${row.axis}=${row.at}`,
        `${row.sheets.join(' / ')} · 线 ${row.line_rect.join(' ')}`]),
      details('登记纸页', form([id, choice('lot', '批次', options(lots.filter(row => row.active))), ...dimensions,
        ...stockFields, ...surfaceFields('front', '正面'), ...surfaceFields('back', '反面')], '登记纸页', run,
      values => save(['sheets'], {id: values.id, lot: values.lot, width: values.width, height: values.height,
        stock: stock(values), faces: {front: surface(values, 'front'), back: surface(values, 'back')}}, '纸页已登记')))),
  ];
}
