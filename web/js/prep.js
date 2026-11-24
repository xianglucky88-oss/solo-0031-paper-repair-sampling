import {el, list, section} from './dom.js';
import {action, choice, field, form, integers, options} from './fields.js';

const STATUS = {
  committed: '已承诺', started: '已开裁', cut: '已裁',
  returned: '未裁交回', cancelled: '已撤销', superseded: '已被取代',
};

function slotLine(slot) {
  const face = `${slot.selection.face} · 旋转 ${slot.selection.turn}°`;
  const receipt = slot.receipt ? ` · 回执 ${slot.receipt}` : '';
  return [`${slot.id} · ${STATUS[slot.status] || slot.status} · 试补 ${slot.trial}${receipt}`,
    `${face} · 取纸 [${slot.cut.join(', ')}] · 拟贴 [${slot.destination.join(', ')}]`];
}

function groupCard(ctx, group) {
  const {board, writeGroup, run, zone} = ctx;
  const write = writeGroup;
  const card = el('article', '', 'prep-card');
  card.append(el('h3', `备料组 ${group.id} · ${group.status}`),
    list(group.slots, slotLine));
  const post = (actionName, data, text) => write(actionName, data, text);
  for (const slot of group.slots) {
    if (slot.zone !== zone.id) continue;
    if (slot.status === 'committed') {
      card.append(action(`开裁 ${slot.id}`, run,
        () => post('start_cut', {group: group.id, slot: slot.id}, `${slot.id} 已确认开裁`)));
    }
    if (slot.status === 'started') {
      const cutForm = form([field('receipt', '已裁回执编号')], `登记 ${slot.id} 已裁`, run,
        values => post('receive', {group: group.id, slot: slot.id, receipt: values.receipt, cut: true},
          `${slot.id} 已裁回执已登记`));
      const backForm = form([field('receipt', '交回回执编号')], `登记 ${slot.id} 未裁交回`, run,
        values => post('receive', {group: group.id, slot: slot.id, receipt: values.receipt, cut: false},
          `${slot.id} 未动刀交回`));
      card.append(cutForm, backForm);
    }
    if (slot.status === 'cut' && slot.revision === zone.revision) {
      card.append(form([field('id', '补片编号'), field('cut', '取纸 左 上 右 下 (mm)'),
        field('origin', '贴放 左 上 (mm)')], `凭回执贴补 ${slot.id}`, run,
      values => post('prepatch', {id: values.id, group: group.id, slot: slot.id, trial: slot.trial,
        cut: integers(values.cut), origin: integers(values.origin)}, '备料片已贴入')));
    }
  }
  if (group.status === 'committed' || group.status === 'started') {
    card.append(action(`整组撤销 ${group.id}`, run,
      () => post('cancel', {group: group.id}, '备料组已撤销')));
  }
  return card;
}

export function prepSection(ctx) {
  const {board, zone, writeGroup, run} = ctx;
  const node = section('成组备料与开裁回执');
  const accepted = zone.trials.filter(t => t.status === 'accepted');
  if (!accepted.length) {
    node.append(el('p', '本区当前修订尚无合格试补，无法备料', 'dim'));
    return node;
  }
  // 成组备料：每行一个备料位，使用“编号|取纸|贴放”分号分隔的紧凑录入
  const buildForm = form([
    field('group', '备料组编号'),
    choice('trial', '合格试补', options(accepted)),
    {...field('rows', '每行一块：备料位编号 | 取纸 左 上 右 下 | 贴放 左 上'), wide: true},
  ], '成组备料', run, values => {
    const slots = values.rows.split(/\n/).map(line => line.trim()).filter(Boolean).map(line => {
      const [id, cutText, originText] = line.split('|').map(part => part.trim());
      return {id, zone: zone.id, trial: values.trial,
        cut: integers(cutText), origin: integers(originText)};
    });
    return write('prepare', {id: values.group, slots}, `备料组 ${values.group} 已成组接受`);
  });
  node.append(buildForm);
  const groups = (board.prep_groups || []).filter(g => g.slots.some(s => s.zone === zone.id));
  if (groups.length) {
    const listWrap = el('div', '', 'prep-list');
    listWrap.append(...groups.map(g => groupCard(ctx, g)));
    node.append(listWrap);
  } else {
    node.append(el('p', '本区暂无备料组', 'dim'));
  }
  return node;
}
