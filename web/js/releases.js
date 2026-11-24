import {path} from './api.js';
import {details, el, json, list, section} from './dom.js';
import {action, choice, form} from './fields.js';

const actionNames = {zone: '登记损坏区', trial: '切取样片', observe: '登记观察',
  patch: '贴放补片', finish: '完工', reopen: '复开'};

function download(url, label) {
  const link = el('a', label, 'download');
  link.href = url;
  return link;
}

export function releasePane({board, run, save, inspect}) {
  if (!board) return [section('封存交付', el('p', '尚无藏品登记', 'dim'))];
  const doc = board.document.id;
  const seal = action('封存当前现场', run, () => save(['documents', doc, 'releases'], {expected: board.version}, '现场已封存'));
  seal.disabled = !board.ready;
  const ledger = section('封存交付', el('p', `现场 v${board.version} · ${board.ready ? '各区已完工' : '待各区完工'}`, 'readout'), seal);
  for (const release of [...board.releases].reverse()) {
    const base = ['documents', doc, 'releases', release.version];
    const ops = el('div', '', 'actions');
    ops.append(download(path(...base, 'csv'), '↓ 裁切 CSV'), download(`${path(...base)}?download`, '↓ 证据 JSON'),
      action('复算校验', run, async () => {
        const result = await inspect(['releases', release.version, 'replay']);
        return `v${result.version} 复算一致 · ${result.patch_count} 片`;
      }));
    const meta = el('p', release.sha256, 'dim');
    ledger.append(details(`封存 v${release.version} · ${release.patch_count} 片`, meta, ops));
  }
  const timeline = el('div');
  const getEvents = action('读取现场事件', run, async () => {
    const rows = await inspect(['events']);
    timeline.replaceChildren(...rows.map(row => details(`v${row.version} · ${actionNames[row.action]} · ${row.facts.zone}`, json(row.facts.result))));
    return `已读取 ${rows.length} 条事件`;
  });
  const result = [ledger, section('现场溯源', getEvents, timeline)];
  if (board.releases.length >= 2) {
    const versions = board.releases.map(r => [String(r.version), `v${r.version}`]);
    const diff = el('div');
    result.splice(1, 0, section('封存版差', form([choice('old', '早版', versions), choice('next', '晚版', versions, versions.at(-1)[0])],
      '比较两版', run, async values => {
        const comparison = await inspect(['compare', values.old, values.next]);
        const name = {added:'增加', removed:'移除', changed:'更换证据'};
        const describe = row => row ? `${row.patch}/${row.sheet}/${row.face}/${row.turn}° · 裁切 (${row.cut.join(', ')})` : '无';
        diff.replaceChildren(list(comparison.changes, r => {
          const row = r.after || r.before;
          return [`${name[r.kind]}：${row.zone} · 贴放 (${row.destination.join(', ')})`, `${describe(r.before)} → ${describe(r.after)}`];
        }));
        return `${comparison.changes.length} 处版差`;
      }), diff));
  }
  return result;
}
