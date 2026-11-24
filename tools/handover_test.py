"""标定交接单叙述场景的进程内核验：适用版本、结论聚合、签件独立复算与篡改拒绝。"""
import copy
from pathlib import Path
from tempfile import TemporaryDirectory

from paperbench import (archive, codec, compatibility, documents, events, handovers, lifecycle,
                        materials, patches, records, replay as replay_mod, rules, sheets, trials, zones)
from paperbench.database import Database
from paperbench.errors import Problem

PASS, FAIL, CONFLICT, INCONCLUSIVE, INCOMPARABLE = (
    handovers.PASS, handovers.FAIL, handovers.CONFLICT, handovers.INCONCLUSIVE, handovers.INCOMPARABLE)

TARGET_LAB = {'l': 770, 'a': 30, 'b': 148}
MAIN_SRC, MAIN_DST = 'D65', 'D50'
EDGE_SRC, EDGE_DST = 'E65', 'E50'
MIX_SRC, MIX_DST = 'X65', 'X50'
ONLY_SRC, ONLY_DST = 'I65', 'I50'
FAIL_SRC, FAIL_DST = 'F65', 'F50'

MAIN_LAB = {'l': 740, 'a': 20, 'b': 130}
EDGE_LAB = {'l': 700, 'a': 20, 'b': 130}
NARROW_LAB = {'l': 600, 'a': 20, 'b': 130}
SOLE_LAB = {'l': 510, 'a': 20, 'b': 130}


def delta_9(src_l):
    return {'l': 770 - src_l, 'a': 10, 'b': 9}


def delta_12(src_l):
    return {'l': 770 - src_l, 'a': 10, 'b': 6}


WIDE = {'l': {'low': 720, 'high': 780}, 'a': {'low': 10, 'high': 40}, 'b': {'low': 100, 'high': 160}}
EDGE_RANGE = {'l': {'low': 700, 'high': 715}, 'a': {'low': 10, 'high': 40}, 'b': {'low': 100, 'high': 160}}
NARROW = {'l': {'low': 590, 'high': 610}, 'a': {'low': 10, 'high': 40}, 'b': {'low': 100, 'high': 160}}
SOLE_RANGE = {'l': {'low': 500, 'high': 520}, 'a': {'low': 10, 'high': 40}, 'b': {'low': 100, 'high': 160}}


def check(condition, description):
    if not condition:
        raise AssertionError(description)


def expect_problem(action, description):
    try:
        action()
    except Problem:
        return
    raise AssertionError(description)


def handover(id_, version, src, dst, ranges, deltas, max_error, effective_at):
    return {'id': id_, 'version': version, 'source_condition': src, 'target_condition': dst,
            'ranges': ranges, 'deltas': deltas, 'max_error': max_error, 'effective_at': effective_at}


def setup(db):
    rules.register(db, {'id': 'R10', 'thickness_gap': 18, 'ph_gap': 5, 'color_gap': 10,
                        'hours': [0, 24], 'drift': 20, 'sample_edge': 5})
    materials.register(db, {'id': 'LOT', 'label': '交接单演练批次'})


def sheet_body(id_, back_lab, back_condition, front_condition=MAIN_DST, grain='x'):
    return {'id': id_, 'lot': 'LOT', 'width': 200, 'height': 200,
            'stock': {'thickness': 90, 'ph': 70, 'grain': grain},
            'faces': {'front': {'condition': front_condition, 'lab': TARGET_LAB},
                      'back': {'condition': back_condition, 'lab': back_lab}}}


def doc_zone(db, doc_id, dst_condition):
    documents.register(db, {'id': doc_id, 'title': doc_id, 'width': 120, 'height': 120, 'rule': 'R10'})
    doc = records.get(db, 'document', doc_id)
    zone = zones.register(db, doc, {'id': 'Z1', 'label': '方形缺损',
                                    'outline': [[10, 10], [18, 10], [18, 18], [10, 18]],
                                    'stock': {'thickness': 94, 'ph': 70, 'grain': 'x'},
                                    'surface': {'condition': dst_condition, 'lab': TARGET_LAB}})
    return doc, zone


def start(db, doc, zone, key, sheet_id, face='back', turn=0, cut=None):
    return trials.start(db, doc, zone, {'id': key, 'selection': {'sheet': sheet_id, 'face': face, 'turn': turn},
                                        'cut': cut or [40, 40, 48, 48]})


def color_result(db, doc, zone, sheet_id, face='back', at=99):
    sheet = records.get(db, 'sheet', sheet_id)
    return compatibility.evaluate(zone, sheet, face, 0, doc['rule'],
                                  handovers.all_handovers(db), at)['color_result']


class Workflow:
    """经 lifecycle.change 走完整事件流，使开样时点等于真实现场版本。"""

    def __init__(self, db, doc):
        self.db, self.doc, self.expected = db, doc, 0

    def change(self, action, data, zone=None):
        request = {'expected': self.expected, 'data': data}
        if action != 'zone':
            request['zone'] = zone
        result = lifecycle.change(self.db, self.doc, action, request)
        self.expected = result['version']
        return result['result']


def exercise():
    with TemporaryDirectory(prefix='paperbench-handover-') as tmp:
        db = Database(Path(tmp) / 'handover.sqlite3')
        with db.transaction(write=True) as conn:
            setup(conn)
            d9_main, d12_main = delta_9(MAIN_LAB['l']), delta_12(MAIN_LAB['l'])

            # 主线：r1 自 v0 生效；r2 与第二张合格单在 v8 生效（第一件完工、第二件开样之前）。
            handovers.register(conn, handover('HV-1', 1, MAIN_SRC, MAIN_DST, WIDE, d9_main, 1, 0))
            handovers.register(conn, handover('HV-1', 2, MAIN_SRC, MAIN_DST, WIDE, d9_main, 1, 8))
            handovers.register(conn, handover('HV-3', 1, MAIN_SRC, MAIN_DST, WIDE, d9_main, 1, 8))

            # 第一件：选面测值落在一张旧版交接单的量程边界，换算 9、误差 1，可以开样。
            handovers.register(conn, handover('HV-E', 1, EDGE_SRC, EDGE_DST, EDGE_RANGE,
                                              delta_9(EDGE_LAB['l']), 1, 0))
            doc12, zone12 = doc_zone(conn, 'FOL-12', EDGE_DST)
            sheets.register(conn, sheet_body('S-EDGE', EDGE_LAB, EDGE_SRC))
            t_edge = start(conn, doc12, zone12, 'T1', 'S-EDGE')
            check(t_edge['opened_at'] == 0, '开样时点取当前现场版本（开样前为 0）')
            edge_basis = t_edge['color_basis']['bases']
            check([b['id'] for b in edge_basis] == ['HV-E'] and edge_basis[0]['version'] == 1,
                  '第一件仅一份适用依据（旧版）')
            check(edge_basis[0]['converted_distance'] == 9.0, '换算色差 9')
            check(t_edge['color_basis']['verdict'] == PASS, '闭区间边界内测值且误差保证合格')
            check(handovers.applicable(handovers.all_handovers(conn), EDGE_SRC, EDGE_DST,
                                       {'l': 699, 'a': 20, 'b': 130}, 0) == [], '量程外不适用')

            # 主线藏品：T1 在 r2 生效前开（一份 r1 依据）；r2 生效后 T2 同时有 r2 与 HV-3 两份依据。
            documents.register(conn, {'id': 'FOL-10', 'title': 'FOL-10', 'width': 120, 'height': 120, 'rule': 'R10'})
            doc10 = records.get(conn, 'document', 'FOL-10')
            wf = Workflow(conn, doc10)
            zone1 = {'id': 'Z1', 'label': '方形缺损', 'outline': [[10, 10], [18, 10], [18, 18], [10, 18]],
                     'stock': {'thickness': 94, 'ph': 70, 'grain': 'x'},
                     'surface': {'condition': MAIN_DST, 'lab': TARGET_LAB}}
            zone2 = {'id': 'Z2', 'label': '第二缺损', 'outline': [[30, 30], [38, 30], [38, 38], [30, 38]],
                     'stock': {'thickness': 94, 'ph': 70, 'grain': 'x'},
                     'surface': {'condition': MAIN_DST, 'lab': TARGET_LAB}}
            wf.change('zone', zone1)
            wf.change('zone', zone2)
            sheets.register(conn, sheet_body('S-MAIN', MAIN_LAB, MAIN_SRC))
            select_main = {'sheet': 'S-MAIN', 'face': 'back', 'turn': 0}
            t1 = wf.change('trial', {'id': 'T1', 'selection': select_main, 'cut': [0, 0, 8, 8]}, 'Z1')
            check(t1['opened_at'] == 2, '主线第一件开样于 r2 生效前的 v2')
            check([(b['id'], b['version']) for b in t1['color_basis']['bases']] == [('HV-1', 1)],
                  '第一件按原有一份 r1 核验')
            wf.change('observe', {'id': 'T1', 'observation': {'hour': 0, 'drift': 1, 'lifting': False, 'note': '初查'}}, 'Z1')
            wf.change('observe', {'id': 'T1', 'observation': {'hour': 24, 'drift': 2, 'lifting': False, 'note': '复查'}}, 'Z1')
            wf.change('patch', {'id': 'P1', 'trial': 'T1', 'cut': [20, 0, 24, 8], 'origin': [10, 10]}, 'Z1')
            wf.change('patch', {'id': 'P2', 'trial': 'T1', 'cut': [24, 0, 28, 8], 'origin': [14, 10]}, 'Z1')
            wf.change('finish', {}, 'Z1')
            check(events.version(conn, doc10['id']) == 8, '第一件完工后现场为 v8，r2 自此生效')
            t2 = wf.change('trial', {'id': 'T2', 'selection': select_main, 'cut': [10, 0, 18, 8]}, 'Z2')
            check(t2['opened_at'] == 8, '第二件开样时点在 r2 生效之后')
            check(sorted((b['id'], b['version']) for b in t2['color_basis']['bases'])
                  == [('HV-1', 2), ('HV-3', 1)], '第二件应有两份依据，HV-1 已升级为 r2')
            check(records.get(conn, 'trial', 'T1', doc10['id'])['color_basis']['bases'][0]['version'] == 1,
                  '已开试样的依据不被新版追溯改写')
            wf.change('observe', {'id': 'T2', 'observation': {'hour': 0, 'drift': 1, 'lifting': False, 'note': '初查'}}, 'Z2')
            wf.change('observe', {'id': 'T2', 'observation': {'hour': 24, 'drift': 2, 'lifting': False, 'note': '复查'}}, 'Z2')
            wf.change('patch', {'id': 'P3', 'trial': 'T2', 'cut': [40, 0, 44, 8], 'origin': [30, 30]}, 'Z2')
            wf.change('patch', {'id': 'P4', 'trial': 'T2', 'cut': [44, 0, 48, 8], 'origin': [34, 30]}, 'Z2')
            wf.change('finish', {}, 'Z2')
            seal_version = wf.expected

            # 观察结束前再发布同样适用、换算 12、误差 1 的单：新开样报冲突，前两件仍可完成观察、贴放并签出。
            doc11, zone11 = doc_zone(conn, 'FOL-11', MIX_DST)
            handovers.register(conn, handover('HV-X1', 1, MIX_SRC, MIX_DST, WIDE,
                                              delta_9(MAIN_LAB['l']), 1, 0))
            handovers.register(conn, handover('HV-X2', 1, MIX_SRC, MIX_DST, WIDE,
                                              delta_12(MAIN_LAB['l']), 1, 0))
            sheets.register(conn, sheet_body('S-MIX', MAIN_LAB, MIX_SRC))
            check(color_result(conn, doc11, zone11, 'S-MIX')['verdict'] == CONFLICT,
                  '明确合格与明确超限依据并存报冲突')
            expect_problem(lambda: start(conn, doc11, zone11, 'TC', 'S-MIX'), '冲突时拒绝开样')

            # 只有一份适用单：换算 9、最大误差 2，应报证据不足；另一面同条件测值不能替选中面放行。
            handovers.register(conn, handover('HV-5', 1, ONLY_SRC, MAIN_DST, NARROW,
                                              delta_9(NARROW_LAB['l']), 2, 0))
            # 目标条件取正面同条件 D50；反面是独立异条件，由唯一一张窄量程交接单覆盖。
            doc14, zone14 = doc_zone(conn, 'FOL-14', MAIN_DST)
            sheets.register(conn, sheet_body('S-ONLY', NARROW_LAB, ONLY_SRC, front_condition=MAIN_DST))
            only = handovers.applicable(handovers.all_handovers(conn), ONLY_SRC, MAIN_DST, NARROW_LAB, 99)
            check([item['id'] for item in only] == ['HV-5'], '来源只有一张适用单')
            check(color_result(conn, doc14, zone14, 'S-ONLY')['verdict'] == INCONCLUSIVE, '无法确认报证据不足')
            expect_problem(lambda: start(conn, doc14, zone14, 'TB', 'S-ONLY'), '证据不足拒绝开样')
            front = start(conn, doc14, zone14, 'TF', 'S-ONLY', face='front')
            check(front['color_basis'] == {'basis': 'same_condition', 'verdict': PASS, 'distance': 0.0, 'bases': []},
                  '同条件正面照常直接比较')
            expect_problem(lambda: start(conn, doc14, zone14, 'TB2', 'S-ONLY', face='back'),
                           '另一面的同条件测值不能替选中面放行')

            # 每份都明确超限：唯一适用单换算 12、误差 1（最坏 11 仍超 10）。
            handovers.register(conn, handover('HV-8', 1, FAIL_SRC, FAIL_DST, SOLE_RANGE,
                                              delta_12(SOLE_LAB['l']), 1, 0))
            doc15, zone15 = doc_zone(conn, 'FOL-15', FAIL_DST)
            sheets.register(conn, sheet_body('S-SOLE', SOLE_LAB, FAIL_SRC))
            check([item['id'] for item in handovers.applicable(
                handovers.all_handovers(conn), FAIL_SRC, FAIL_DST, SOLE_LAB, 99)] == ['HV-8'], '唯一超限单适用')
            check(color_result(conn, doc15, zone15, 'S-SOLE')['verdict'] == FAIL, '每份明确超限时报超限')
            expect_problem(lambda: start(conn, doc15, zone15, 'TF2', 'S-SOLE'), '明确超限拒绝开样')

            # 无适用单：条件不可比。
            unmatched = compatibility.color_verdict(zone15, {'condition': 'UV', 'lab': MAIN_LAB},
                                                     doc15['rule'], handovers.all_handovers(conn), 99)
            check(unmatched['verdict'] == INCOMPARABLE and unmatched['bases'] == [], '无适用单报条件不可比')

            # 封存：签件含全部交接单，接手人仅凭签件独立复算；前两件首次签出。
            sealed = archive.seal(conn, doc10, {'expected': seal_version})
            release = records.get(conn, 'release', str(seal_version), doc10['id'])
            check(release['format'] == 2 and release['inputs']['handovers'], '签件冻结交接单发布事实')
            check(archive.load(conn, doc10, seal_version)['sha256'] == sealed['sha256'], '复算通过')

            def rehash(payload):
                payload['sha256'] = codec.digest({k: v for k, v in payload.items() if k != 'sha256'})

            # 漏列第二件的一份采用依据：发布事实、开样时点齐全、剩余依据足以合格、摘要重算正确，复算仍拒绝。
            tampered = copy.deepcopy(release)
            trial2 = next(t for z in tampered['inputs']['zones'] for t in z['trials'] if t['id'] == 'T2')
            trial2['color_basis']['bases'].pop()
            rehash(tampered)
            expect_problem(lambda: archive.verify(tampered), '漏列适用依据必须拒绝复算')
            # 篡改单份依据的发布事实（最大误差）同样拒绝。
            tampered2 = copy.deepcopy(release)
            trial1 = next(t for z in tampered2['inputs']['zones'] for t in z['trials'] if t['id'] == 'T1')
            trial1['color_basis']['bases'][0]['max_error'] = 9
            rehash(tampered2)
            expect_problem(lambda: archive.verify(tampered2), '依据与发布事实不符必须拒绝')

            # 旧同条件签件（format 1）照常读回和复算：构造一个同条件试补的合成 v1 输入。
            same_sheet = {'id': 'S-LEGACY', 'lot': 'LOT', 'width': 200, 'height': 200,
                          'stock': {'thickness': 90, 'ph': 70, 'grain': 'x'},
                          'faces': {'front': {'condition': MAIN_DST, 'lab': TARGET_LAB},
                                    'back': {'condition': MAIN_DST, 'lab': TARGET_LAB}}}
            legacy_zone = {'id': 'ZL', 'label': '旧格式区', 'revision': 1, 'complete': True,
                           'outline': [[10, 10], [18, 10], [18, 18], [10, 18]],
                           'stock': {'thickness': 94, 'ph': 70, 'grain': 'x'},
                           'surface': {'condition': MAIN_DST, 'lab': TARGET_LAB},
                           'trials': [{
                               'id': 'TL', 'zone': 'ZL', 'revision': 1, 'status': 'accepted',
                               'rows': [{'hour': 0, 'drift': 1, 'lifting': False, 'note': '初查'},
                                        {'hour': 24, 'drift': 2, 'lifting': False, 'note': '复查'}],
                               'selection': {'sheet': 'S-LEGACY', 'face': 'front', 'turn': 0},
                               'allocation': {'cut': [0, 0, 8, 8]}}],
                           'patches': [{
                               'id': 'PL', 'zone': 'ZL', 'revision': 1, 'trial': 'TL',
                               'selection': {'sheet': 'S-LEGACY', 'face': 'front', 'turn': 0},
                               'allocation': {'cut': [20, 0, 28, 8]}, 'destination': [10, 10, 18, 18]}]}
            legacy_inputs = {'document': doc10, 'version': 1, 'zones': [legacy_zone],
                             'sheets': {'S-LEGACY': same_sheet}}
            legacy_manifest = replay_mod.reconstruct_v1(legacy_inputs)
            check(legacy_manifest and legacy_manifest[0]['patch'] == 'PL', 'v1 同条件复算路径保留')

            # format 2 签件里特性上线前的同条件试补没有 color_basis，仍应按同条件兜底复算。
            legacy_trial = dict(legacy_zone['trials'][0])
            legacy_trial.pop('color_basis', None)
            legacy_zone2 = dict(legacy_zone, trials=[legacy_trial])
            legacy2 = {'document': doc10, 'version': 2, 'zones': [legacy_zone2],
                       'sheets': {'S-LEGACY': same_sheet}, 'handovers': [], 'format': 2}
            check(replay_mod.reconstruct(legacy2)[0]['patch'] == 'PL', '无 color_basis 的历史同条件试补兜底通过')

    print('交接单叙述场景全部通过')


if __name__ == '__main__':
    exercise()
