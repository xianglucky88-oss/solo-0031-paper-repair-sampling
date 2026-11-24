"""Exercise splitting one damage zone into two successors without touching the artifacts.

Two routes are covered: direct service calls for the geometry and bookkeeping, and one live
HTTP session for the handover request shape, tamper rejection and the untouched old release.
"""
import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from paperbench import archive, codec, comparison, documents, events, httpd, lifecycle, materials, records, rules, sheets
from paperbench.database import Database
from paperbench.errors import Problem

RULE = {'id': 'PB-1', 'thickness_gap': 18, 'ph_gap': 5, 'color_gap': 35,
        'hours': [0, 24], 'drift': 20, 'sample_edge': 5}
STOCK = {'thickness': 90, 'ph': 69, 'grain': 'y'}
SURFACE = {'condition': 'D50', 'lab': {'l': 771, 'a': 32, 'b': 147}}
SHEET = {'id': 'KOZO', 'lot': 'LOT', 'width': 120, 'height': 90,
         'stock': STOCK, 'faces': {'front': SURFACE, 'back': SURFACE}}
STEP = [[0, 0], [24, 0], [24, 8], [16, 8], [16, 16], [0, 16]]
LEFT = [[0, 0], [16, 0], [16, 16], [0, 16]]
RIGHT = [[16, 0], [24, 0], [24, 8], [16, 8]]
AT12_A = [[0, 0], [12, 0], [12, 16], [0, 16]]
AT12_B = [[12, 0], [24, 0], [24, 8], [16, 8], [16, 16], [12, 16]]


def check(condition, label):
    if not condition:
        raise AssertionError(label)
    print('  ok:', label)


def expect_problem(action, label):
    try:
        action()
    except Problem:
        print('  ok:', label)
        return
    raise AssertionError(label)


class Flow:
    def __init__(self, db, doc):
        self.db, self.doc, self.expected = db, doc, 0

    def change(self, action, data, zone=None, expected=None):
        request = {'expected': self.expected if expected is None else expected, 'data': data}
        if zone is not None:
            request['zone'] = zone
        result = lifecycle.change(self.db, self.doc, action, request)
        if expected is None:
            self.expected = result['version']
        return result['result']


def settle(flow, trial_id, zone):
    flow.change('observe', {'id': trial_id, 'observation': {'hour': 0, 'drift': 1, 'lifting': False, 'note': '初查'}}, zone)
    flow.change('observe', {'id': trial_id, 'observation': {'hour': 24, 'drift': 2, 'lifting': False, 'note': '复查'}}, zone)


def setup(db):
    rules.register(db, RULE)
    materials.register(db, {'id': 'LOT', 'label': '批次'})
    sheets.register(db, SHEET)
    documents.register(db, {'id': 'DOC', 'title': '阶形稿', 'width': 40, 'height': 40, 'rule': 'PB-1'})
    return records.get(db, 'document', 'DOC')


def build_step(db, doc, flow):
    flow.change('zone', {'id': 'Z1', 'label': '阶形缺口', 'outline': STEP, 'stock': STOCK, 'surface': SURFACE})
    flow.change('trial', {'id': 'T1', 'selection': {'sheet': 'KOZO', 'face': 'front', 'turn': 0},
                          'cut': [30, 0, 38, 8]}, 'Z1')
    settle(flow, 'T1', 'Z1')
    flow.change('patch', {'id': 'P1', 'trial': 'T1', 'cut': [0, 0, 16, 16], 'origin': [0, 0]}, 'Z1')
    flow.change('patch', {'id': 'P2', 'trial': 'T1', 'cut': [40, 0, 48, 8], 'origin': [16, 0]}, 'Z1')
    flow.change('finish', {}, 'Z1')


def scenario_seam():
    print('== 沿接缝拆区并签出')
    with TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / 'seam.sqlite3')
        with db.transaction(write=True) as conn:
            doc = setup(conn)
            flow = Flow(conn, doc)
            build_step(conn, doc, flow)
            check(archive.seal(conn, doc, {'expected': flow.expected})['patch_count'] == 2, '原区可签出')
            old_version = flow.expected
            old_release = records.get(conn, 'release', str(old_version), 'DOC')

            receipt = flow.change('split', {'zone': 'Z1', 'zones': [
                {'id': 'ZA', 'label': '左段', 'outline': LEFT},
                {'id': 'ZB', 'label': '右段', 'outline': RIGHT}]})
            check(receipt['patches'][0]['zone'] == 'ZA' and receipt['patches'][1]['zone'] == 'ZB', '两片各自归区')
            check(receipt['trials'] == [{'id': 'T1', 'zones': ['ZA', 'ZB'], 'cut': [30, 0, 38, 8]}],
                  '唯一一笔试样取纸跨两区')
            check(receipt['zones'][0]['complete'] and receipt['zones'][1]['complete'], '两区各自完工')
            check(records.get(conn, 'trial', 'T1', 'DOC')['zone'] in {'ZA', 'ZB'}, '试补的家区落在新区')

            from paperbench import workbench
            board = workbench.board(conn, doc)
            live = {z['id']: z for z in board['zones'] if z.get('active', True)}
            check(set(live) == {'ZA', 'ZB'}, '原区不再有效')
            check(live['ZA']['coverage']['target'] == 256 and live['ZA']['coverage']['placed'] == 256, '左区覆盖 256')
            check(live['ZB']['coverage']['target'] == 64 and live['ZB']['coverage']['placed'] == 64, '右区覆盖 64')
            check(live['ZA']['surface'] == SURFACE and live['ZA']['stock'] == STOCK, '材性与纸面沿用原区')

            expect_problem(lambda: flow.change('finish', {}, 'Z1'), '原区不接受操作')
            expect_problem(lambda: flow.change('trial', {'id': 'T2', 'selection': {
                'sheet': 'KOZO', 'face': 'front', 'turn': 0}, 'cut': [60, 0, 68, 8]}, 'Z1'), '原区不能开新试补')

            check(archive.seal(conn, doc, {'expected': flow.expected})['version'] == flow.expected, '新区现场可签出')
            new_release = records.get(conn, 'release', str(flow.expected), 'DOC')
            check(new_release['inputs']['splits'][0]['source']['outline'] == STEP, '签件含旧轮廓')
            check({z['id'] for z in new_release['inputs']['zones']} == {'ZA', 'ZB'}, '签件只含两个新区')
            rows = {(row['patch'], row['zone']) for row in new_release['manifest']}
            check(rows == {('P1', 'ZA'), ('P2', 'ZB')}, '逐片归属可离线核对')
            check(all(row['sheet'] == 'KOZO' for row in new_release['manifest']), '实物纸页未变')
            check(archive.load(conn, doc, old_version)['sha256'] == old_release['sha256'], '旧签件原样取回并复算')

            diff = comparison.compare(old_release, records.get(conn, 'release', str(flow.expected), 'DOC'))
            check([item['kind'] for item in diff] == ['changed', 'changed'], '早晚版仅区域归属变化')
            for item in diff:
                check(item['before']['cut'] == item['after']['cut'] and
                      item['before']['sheet'] == item['after']['sheet'], '裁切与实物不变')
                check(item['before']['zone'] != item['after']['zone'], '区域归属改变')


def scenario_cut_patch():
    print('== 在 x=12 拆区切过在位片应整体拒绝')
    with TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / 'cut.sqlite3')
        with db.transaction(write=True) as conn:
            doc = setup(conn)
            flow = Flow(conn, doc)
            build_step(conn, doc, flow)
            before = records.listing(conn, 'zone', 'DOC')
            version = flow.expected
            expect_problem(lambda: flow.change('split', {'zone': 'Z1', 'zones': [
                {'id': 'ZA', 'outline': AT12_A}, {'id': 'ZB', 'outline': AT12_B}]}), '切过补片被拒')
            check(events.version(conn, 'DOC') == version, '拒绝不推进现场版本')
            check(records.listing(conn, 'zone', 'DOC') == before, '拒绝后区域记录不变')
            check(len(records.listing(conn, 'cut', 'KOZO')) == 3, '拒绝后裁切占位不变')


def scenario_partitions():
    print('== 重叠、缝隙与填平凹口都被拒绝')
    with TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / 'bad.sqlite3')
        with db.transaction(write=True) as conn:
            doc = setup(conn)
            flow = Flow(conn, doc)
            flow.change('zone', {'id': 'Z1', 'label': '阶形', 'outline': STEP,
                                 'stock': STOCK, 'surface': SURFACE})
            expect_problem(lambda: flow.change('split', {'zone': 'Z1', 'zones': [
                {'id': 'ZA', 'outline': [[0, 0], [16, 0], [16, 16], [0, 16]]},
                {'id': 'ZB', 'outline': [[14, 0], [24, 0], [24, 8], [16, 8], [16, 16], [14, 16]]}]}),
                '新区重叠被拒')
            expect_problem(lambda: flow.change('split', {'zone': 'Z1', 'zones': [
                {'id': 'ZA', 'outline': [[0, 0], [15, 0], [15, 16], [0, 16]]},
                {'id': 'ZB', 'outline': [[16, 0], [24, 0], [24, 8], [16, 8], [16, 16], [15, 16]]}]}),
                '留缝被拒')
            expect_problem(lambda: flow.change('split', {'zone': 'Z1', 'zones': [
                {'id': 'ZA', 'outline': [[0, 0], [16, 0], [16, 16], [0, 16]]},
                {'id': 'ZB', 'outline': [[16, 0], [24, 0], [24, 16], [16, 16]]}]}),
                '填平旧凹口被拒')
            check(len(records.listing(conn, 'cut', 'KOZO')) == 0, '非法拆分不占用纸料')


def scenario_partial_and_second_zone():
    print('== 未完工区域拆分后各自续做，另一区不受影响')
    with TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / 'partial.sqlite3')
        with db.transaction(write=True) as conn:
            doc = setup(conn)
            flow = Flow(conn, doc)
            flow.change('zone', {'id': 'Z1', 'label': '阶形缺口', 'outline': STEP,
                                 'stock': STOCK, 'surface': SURFACE})
            flow.change('zone', {'id': 'Z9', 'label': '远处小缺口',
                                 'outline': [[30, 30], [34, 30], [34, 34], [30, 34]],
                                 'stock': STOCK, 'surface': SURFACE})
            flow.change('trial', {'id': 'T1', 'selection': {'sheet': 'KOZO', 'face': 'front', 'turn': 0},
                                  'cut': [30, 0, 38, 8]}, 'Z1')
            settle(flow, 'T1', 'Z1')
            flow.change('patch', {'id': 'P1', 'trial': 'T1', 'cut': [0, 0, 16, 16], 'origin': [0, 0]}, 'Z1')
            # Split at x=18: the placed patch stays wholly in the left successor, but that
            # successor still has a strip beyond it, so neither side is complete.
            receipt = flow.change('split', {'zone': 'Z1', 'zones': [
                {'id': 'ZA', 'outline': [[0, 0], [18, 0], [18, 8], [16, 8], [16, 16], [0, 16]]},
                {'id': 'ZB', 'outline': [[18, 0], [24, 0], [24, 8], [18, 8]]}]})
            check([z['complete'] for z in receipt['zones']] == [False, False], '两区都未完工')
            from paperbench import workbench
            board = workbench.board(conn, doc)
            check(board['ready'] is False, '未完工时不能签出')
            live = {z['id']: z for z in board['zones'] if z.get('active', True)}
            check(live['ZA']['coverage'] == {'target': 272, 'placed': 256, 'remaining': 16}, '左区还差 16')
            check(live['ZB']['coverage'] == {'target': 48, 'placed': 0, 'remaining': 48}, '右区待补 48')
            check(live['Z9']['coverage']['target'] == 16, '另一区原样')

            # The shared T1 trial sample still supports a new patch in the left successor.
            flow.change('patch', {'id': 'P4', 'trial': 'T1', 'cut': [90, 0, 92, 8], 'origin': [16, 0]}, 'ZA')
            check(records.get(conn, 'patch', 'P4', 'DOC')['zone'] == 'ZA', '共享试补可供新区续贴')

            # A second trial can be cut for the right successor and a new patch placed there.
            flow.change('trial', {'id': 'T2', 'selection': {'sheet': 'KOZO', 'face': 'front', 'turn': 0},
                                  'cut': [60, 0, 68, 8]}, 'ZB')
            settle(flow, 'T2', 'ZB')
            flow.change('patch', {'id': 'P2', 'trial': 'T2', 'cut': [80, 0, 86, 8], 'origin': [18, 0]}, 'ZB')
            flow.change('finish', {}, 'ZA')
            flow.change('finish', {}, 'ZB')
            check(workbench.board(conn, doc)['ready'] is False, '远处区仍未完工前不签出')
            flow.change('trial', {'id': 'T3', 'selection': {'sheet': 'KOZO', 'face': 'front', 'turn': 0},
                                  'cut': [100, 0, 108, 8]}, 'Z9')
            settle(flow, 'T3', 'Z9')
            flow.change('patch', {'id': 'P3', 'trial': 'T3', 'cut': [110, 0, 114, 4], 'origin': [30, 30]}, 'Z9')
            flow.change('finish', {}, 'Z9')
            check(workbench.board(conn, doc)['ready'] is True, '三区全部完工后可签出')
            archive.seal(conn, doc, {'expected': flow.expected})
            release = records.get(conn, 'release', str(flow.expected), 'DOC')
            zones = {row['zone'] for row in release['manifest']}
            check(zones == {'ZA', 'ZB', 'Z9'}, '签件含两新区和未拆分的一区')
            check(len({(row['patch'], row['cut'][0]) for row in release['manifest']}) == 4, '四片取纸各一')
            check(archive.verify(release) == release['manifest'], '各区分区复算一致')


def scenario_tamper_split():
    print('== 篡改拆区出处或归属被复算拒绝')
    with TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / 'tamper.sqlite3')
        with db.transaction(write=True) as conn:
            doc = setup(conn)
            flow = Flow(conn, doc)
            build_step(conn, doc, flow)
            flow.change('split', {'zone': 'Z1', 'zones': [
                {'id': 'ZA', 'outline': LEFT}, {'id': 'ZB', 'outline': RIGHT}]})
            archive.seal(conn, doc, {'expected': flow.expected})
            release = records.get(conn, 'release', str(flow.expected), 'DOC')

            def rehash(payload):
                payload['sha256'] = codec.digest({k: v for k, v in payload.items() if k != 'sha256'})

            broken = copy.deepcopy(release)
            broken['inputs']['splits'][0]['source']['outline'] = [[0, 0], [16, 0], [16, 16], [0, 16]]
            rehash(broken)
            expect_problem(lambda: archive.verify(broken), '旧轮廓被改后拒绝')

            broken = copy.deepcopy(release)
            broken['inputs']['splits'][0]['zones'][1]['outline'] = [[16, 0], [24, 0], [24, 16], [16, 16]]
            rehash(broken)
            expect_problem(lambda: archive.verify(broken), '填平凹口的新轮廓拒绝')

            broken = copy.deepcopy(release)
            broken['manifest'][0]['zone'] = 'ZB'
            broken['manifest'][1]['zone'] = 'ZA'
            rehash(broken)
            expect_problem(lambda: archive.verify(broken), '补片归属被换后拒绝')

            broken = copy.deepcopy(release)
            broken['manifest'][0]['cut'] = [0, 0, 16, 8]
            rehash(broken)
            expect_problem(lambda: archive.verify(broken), '取纸或覆盖被改后拒绝')

            broken = copy.deepcopy(release)
            broken['inputs']['splits'][0]['trials'][0]['cut'] = [30, 0, 38, 9]
            rehash(broken)
            expect_problem(lambda: archive.verify(broken), '拆区回执里试补取纸被改后拒绝')

            broken = copy.deepcopy(release)
            broken['inputs']['splits'][0]['zones'][0]['id'] = 'ZX'
            rehash(broken)
            expect_problem(lambda: archive.verify(broken), '拆区回执里的新区编号与在册不符被拒')


def scenario_reopened_and_nested():
    print('== 复开到第 2 修订后拆分只移动在位片，且可再拆一次')
    with TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / 'nested.sqlite3')
        with db.transaction(write=True) as conn:
            doc = setup(conn)
            flow = Flow(conn, doc)
            build_step(conn, doc, flow)
            flow.change('reopen', {'reason': '重做边部'}, 'Z1')
            check(records.get(conn, 'zone', 'Z1', 'DOC')['revision'] == 2, '原区进入第 2 修订')
            flow.change('trial', {'id': 'T2', 'selection': {'sheet': 'KOZO', 'face': 'front', 'turn': 0},
                                  'cut': [50, 30, 58, 38]}, 'Z1')
            settle(flow, 'T2', 'Z1')
            flow.change('patch', {'id': 'P5', 'trial': 'T2', 'cut': [60, 30, 76, 46], 'origin': [0, 0]}, 'Z1')
            flow.change('patch', {'id': 'P6', 'trial': 'T2', 'cut': [80, 30, 84, 38], 'origin': [16, 0]}, 'Z1')
            flow.change('patch', {'id': 'P7', 'trial': 'T2', 'cut': [90, 30, 94, 38], 'origin': [20, 0]}, 'Z1')
            flow.change('finish', {}, 'Z1')

            flow.change('split', {'zone': 'Z1', 'zones': [
                {'id': 'ZA', 'outline': LEFT}, {'id': 'ZB', 'outline': RIGHT}]})
            old_patch = records.get(conn, 'patch', 'P1', 'DOC')
            check(old_patch['zone'] == 'Z1' and old_patch['revision'] == 1, '旧修订补片留在历史')
            check(old_patch.get('origin') is None, '旧修订补片不加拆区出处')
            moved = records.get(conn, 'patch', 'P6', 'DOC')
            check(moved['zone'] == 'ZB' and moved['origin'] == {'zone': 'Z1', 'revision': 2}, '第 2 修订出处')
            check(moved['lineage'] == ['Z1'], '出处链保留')

            # Split the right successor at x=20, which runs between P6 and P7.
            flow.change('split', {'zone': 'ZB', 'zones': [
                {'id': 'ZB1', 'outline': [[16, 0], [20, 0], [20, 8], [16, 8]]},
                {'id': 'ZB2', 'outline': [[20, 0], [24, 0], [24, 8], [20, 8]]}]})
            left_piece = records.get(conn, 'patch', 'P6', 'DOC')
            right_piece = records.get(conn, 'patch', 'P7', 'DOC')
            check(left_piece['zone'] == 'ZB1' and right_piece['zone'] == 'ZB2', '二次拆区各归其片')
            check(left_piece['lineage'] == ['Z1', 'ZB'] and right_piece['origin'] == {'zone': 'ZB', 'revision': 1},
                  '二次拆区累计出处链')
            from paperbench import workbench
            live = {z['id']: z for z in workbench.board(conn, doc)['zones'] if z.get('active', True)}
            check(set(live) == {'ZA', 'ZB1', 'ZB2'}, '两层拆分只留叶子区')
            check(live['ZA']['coverage']['placed'] == 256 and live['ZB1']['coverage']['placed'] == 32
                  and live['ZB2']['coverage']['placed'] == 32, '补片覆盖不因二次拆分改变')
            record = records.get(conn, 'split', 'ZB@1', 'DOC')
            check(record['source']['outline'] == RIGHT, '二次拆区出处可查')
            archive.seal(conn, doc, {'expected': flow.expected})
            release = records.get(conn, 'release', str(flow.expected), 'DOC')
            check(len(release['inputs']['splits']) == 2, '签件含两次拆区出处')
            check({row['zone'] for row in release['manifest']} == {'ZA', 'ZB1', 'ZB2'}, '签件列出各叶子区在册补片')
            check(archive.verify(release) == release['manifest'], '嵌套拆区复算一致')


def scenario_request_shapes():
    print('== 拆区请求的各种等价写法都被接受，异材质写法被拒')
    with TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / 'shapes.sqlite3')
        with db.transaction(write=True) as conn:
            doc = setup(conn)
            flow = Flow(conn, doc)
            build_step(conn, doc, flow)
            # Material explicitly restated and matching the source zone is fine.
            flow.change('split', {'zone': 'Z1', 'zones': [
                {'id': 'ZA', 'label': '左段', 'outline': LEFT, 'stock': STOCK, 'surface': SURFACE},
                {'id': 'ZB', 'outline': RIGHT}]})
            check(records.get(conn, 'zone', 'ZA', 'DOC')['stock'] == STOCK, '沿用原区材性')

            # Rebuild a fresh document to test a conflicting material claim.
            documents.register(conn, {'id': 'DOC2', 'title': '阶形稿二', 'width': 40, 'height': 40, 'rule': 'PB-1'})
            other = records.get(conn, 'document', 'DOC2')
            second = Flow(conn, other)
            second.change('zone', {'id': 'Z1', 'label': '阶形缺口', 'outline': STEP,
                                   'stock': STOCK, 'surface': SURFACE})
            second.change('trial', {'id': 'T9', 'selection': {'sheet': 'KOZO', 'face': 'front', 'turn': 0},
                                    'cut': [30, 20, 38, 28]}, 'Z1')
            settle(second, 'T9', 'Z1')
            second.change('patch', {'id': 'Q1', 'trial': 'T9', 'cut': [0, 30, 16, 46], 'origin': [0, 0]}, 'Z1')
            second.change('patch', {'id': 'Q2', 'trial': 'T9', 'cut': [40, 20, 48, 28], 'origin': [16, 0]}, 'Z1')
            bad = {**STOCK, 'ph': 10}
            expect_problem(lambda: second.change('split', {'zone': 'Z1', 'zones': [
                {'id': 'ZA', 'outline': LEFT, 'stock': bad},
                {'id': 'ZB', 'outline': RIGHT}]}), '异材质新区被拒')

            # `parts` alias and [id, outline] tuples both work.
            second.change('split', {'zone': 'Z1', 'parts': [['ZA', LEFT], ['ZB', RIGHT]]})
            check({z['id'] for z in [records.get(conn, 'zone', 'ZA', 'DOC2'), records.get(conn, 'zone', 'ZB', 'DOC2')]}
                  == {'ZA', 'ZB'}, 'parts 别名与二元组写法可用')


class Quiet(httpd.Handler):
    def log_message(self, *args):
        pass


def scenario_http():
    print('== 经 HTTP 拆区、拒改签件与取回旧版')
    with TemporaryDirectory() as tmp:
        database = Database(Path(tmp) / 'http.sqlite3')
        server = httpd.server(database, 0)
        server.RequestHandlerClass = Quiet
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_address[1]}/api/'

        def call(path, value=None, status=200):
            data = json.dumps(value).encode() if value is not None else None
            headers = {'Content-Type': 'application/json'} if data else {}
            try:
                with urlopen(Request(base + path, data, headers), timeout=5) as response:
                    body, code = response.read(), response.code
            except HTTPError as exc:
                body, code = exc.read(), exc.code
            check(code == status, f'{path}: {code} {body[:200]!r}')
            return json.loads(body) if body else None

        try:
            call('rules', RULE)
            call('lots', {'id': 'LOT', 'label': '批次'})
            call('sheets', SHEET)
            call('documents', {'id': 'DOC', 'title': '阶形稿', 'width': 40, 'height': 40, 'rule': 'PB-1'})
            call('documents/DOC/zone', {'expected': 0, 'data': {
                'id': 'Z1', 'label': '阶形缺口', 'outline': STEP, 'stock': STOCK, 'surface': SURFACE}})
            call('documents/DOC/trial', {'expected': 1, 'zone': 'Z1', 'data': {
                'id': 'T1', 'selection': {'sheet': 'KOZO', 'face': 'front', 'turn': 0}, 'cut': [30, 0, 38, 8]}})
            call('documents/DOC/observe', {'expected': 2, 'zone': 'Z1', 'data': {
                'id': 'T1', 'observation': {'hour': 0, 'drift': 1, 'lifting': False, 'note': '初查'}}})
            call('documents/DOC/observe', {'expected': 3, 'zone': 'Z1', 'data': {
                'id': 'T1', 'observation': {'hour': 24, 'drift': 2, 'lifting': False, 'note': '复查'}}})
            call('documents/DOC/patch', {'expected': 4, 'zone': 'Z1', 'data': {
                'id': 'P1', 'trial': 'T1', 'cut': [0, 0, 16, 16], 'origin': [0, 0]}})
            call('documents/DOC/patch', {'expected': 5, 'zone': 'Z1', 'data': {
                'id': 'P2', 'trial': 'T1', 'cut': [40, 0, 48, 8], 'origin': [16, 0]}})
            call('documents/DOC/finish', {'expected': 6, 'zone': 'Z1', 'data': {}})
            call('documents/DOC/releases', {'expected': 7})
            old = call('documents/DOC/releases/7')

            call('documents/DOC/split', {'expected': 7, 'data': {'zone': 'Z1', 'zones': [
                {'id': 'ZA', 'label': '左段', 'outline': LEFT},
                {'id': 'ZB', 'label': '右段', 'outline': RIGHT}]}})
            board = call('documents/DOC')
            check({z['id'] for z in board['zones'] if z.get('active', True)} == {'ZA', 'ZB'}, 'HTTP 拆区生效')
            check(any(z['id'] == 'Z1' and z.get('active') is False for z in board['zones']), 'HTTP 原区停用可查')
            call('documents/DOC/finish', {'expected': 8, 'zone': 'Z1', 'data': {}}, 409)
            call('documents/DOC/split', {'expected': 8, 'data': {'zone': 'Z1', 'zones': [
                {'id': 'ZC', 'outline': LEFT}, {'id': 'ZD', 'outline': RIGHT}]}}, 409)
            call('documents/DOC/releases', {'expected': 8})
            new = call('documents/DOC/releases/8')
            check({row['zone'] for row in new['manifest']} == {'ZA', 'ZB'}, 'HTTP 新签件分区结算')
            check(call('documents/DOC/releases/7') == old, '旧签件经 HTTP 原样取回')

            tampered = copy.deepcopy(new)
            tampered['manifest'][0]['zone'] = 'Z1'
            tampered['sha256'] = codec.digest({k: v for k, v in tampered.items() if k != 'sha256'})

            def reject():
                archive.verify(tampered)
            expect_problem(reject, '改动清单区域归属被拒')
        finally:
            server.shutdown()
            thread.join()


if __name__ == '__main__':
    scenario_seam()
    scenario_cut_patch()
    scenario_partitions()
    scenario_partial_and_second_zone()
    scenario_reopened_and_nested()
    scenario_tamper_split()
    scenario_request_shapes()
    scenario_http()
    print('全部通过')
