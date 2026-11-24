"""整块试样贴用的进程内/HTTP 核验：取样、贴用、完工、复开与签件复算。"""
import copy
import json
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from paperbench import archive, codec, httpd, replay
from paperbench.database import Database
from paperbench.errors import Problem

RULE = {"id": "R1", "thickness_gap": 18, "ph_gap": 5, "color_gap": 35,
        "hours": [0, 24], "drift": 20, "sample_edge": 5}
SHEET = {"id": "S1", "lot": "LOT", "width": 120, "height": 100,
         "stock": {"thickness": 90, "ph": 69, "grain": "y"},
         "faces": {"front": {"condition": "D50", "lab": {"l": 771, "a": 32, "b": 147}},
                   "back": {"condition": "D65", "lab": {"l": 740, "a": 20, "b": 130}}}}
SHEET2 = {"id": "S2", "lot": "LOT2", "width": 120, "height": 100,
          "stock": {"thickness": 90, "ph": 69, "grain": "y"},
          "faces": {"front": {"condition": "D50", "lab": {"l": 771, "a": 32, "b": 147}},
                    "back": {"condition": "D65", "lab": {"l": 740, "a": 20, "b": 130}}}}
STOCK = {"thickness": 94, "ph": 70, "grain": "x"}
SURFACE = {"condition": "D50", "lab": {"l": 770, "a": 30, "b": 150}}
SELECTION = {"sheet": "S1", "face": "front", "turn": 90}


class Quiet(httpd.Handler):
    def log_message(self, *args):
        pass


def check(condition, label):
    if not condition:
        raise AssertionError(label)
    print('  ok:', label)


def expect(action, status, label):
    try:
        action()
    except Problem as exc:
        check(exc.status == status, f'{label}（{exc.status}）')
        return exc
    raise AssertionError(f'{label}：未拒绝')


def refuse(doc, action, data, status, label):
    result = doc.change(action, data, status)
    check('error' in result, label)


@contextmanager
def server():
    with TemporaryDirectory() as tmp:
        http = httpd.server(Database(Path(tmp) / 'work.sqlite3'), 0)
        http.RequestHandlerClass = Quiet
        thread = Thread(target=http.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{http.server_address[1]}'

        def api(path, value=None, status=200, raw=False):
            data = json.dumps(value).encode() if value is not None else None
            headers = {'Content-Type': 'application/json'} if data else {}
            request = Request(base + '/api/' + path, data, headers)
            try:
                with urlopen(request, timeout=5) as response:
                    code, body = response.code, response.read()
            except HTTPError as exc:
                code, body = exc.code, exc.read()
            if code != status:
                raise AssertionError(f'{path}: 期望 {status}，得到 {code}：{body[:300]!r}')
            return body if raw else json.loads(body)

        try:
            yield api
        finally:
            http.shutdown()
            thread.join()


class Doc:
    def __init__(self, api, id_, outline):
        self.api, self.id, self.version = api, id_, 0
        api('documents', {"id": id_, "title": id_, "width": 120, "height": 100, "rule": "R1"})
        self.change('zone', {"id": "Z1", "label": "缺口", "outline": outline,
                             "stock": STOCK, "surface": SURFACE})

    def change(self, action, data, status=200):
        request = {"expected": self.version, "data": data}
        if action != 'zone':
            request['zone'] = "Z1"
        result = self.api(f'documents/{self.id}/{action}', request, status)
        if status == 200:
            self.version += 1
            check(result['version'] == self.version, f'{self.id}/{action} 现场版本逐次递增')
            return result['result']
        return result

    def trial(self, id_, cut, selection=SELECTION):
        return self.change('trial', {"id": id_, "selection": selection, "cut": cut})

    def observe_all(self, id_):
        self.change('observe', {"id": id_, "observation": {"hour": 0, "drift": 3,
                                                           "lifting": False, "note": "起始"}})
        return self.change('observe', {"id": id_, "observation": {"hour": 24, "drift": 4,
                                                                  "lifting": False, "note": "复检"}})

    def board(self):
        return self.api(f'documents/{self.id}')


def scenario_whole_sample(api):
    """8×12 sample turned 90° fills a 12×8 notch; finish and seal on actual coverage."""
    api('rules', RULE)
    api('lots', {"id": "LOT", "label": "整片演练批"})
    api('sheets', SHEET)
    doc = Doc(api, 'D1', [[10, 10], [22, 10], [22, 18], [10, 18]])
    doc.trial('T1', [0, 0, 8, 12])
    # Not yet observed: an identical sample may not be pasted.
    refuse(doc, 'mount', {"id": "PX", "trial": "T1", "origin": [10, 10]}, 409,
           '未完成观察的试样不能整块贴用')
    check(doc.board()['zones'][0]['coverage']['placed'] == 0, '被拒的贴用不计覆盖')
    check(len(api('sheets/S1')['cuts']) == 1, '被拒的贴用不新增裁切占位')
    doc.observe_all('T1')
    mount = doc.change('mount', {"id": "P1", "trial": "T1", "origin": [10, 10]})
    check(mount['destination'] == [10, 10, 22, 18], '90 度试样贴入 12×8 缺口')
    check(mount['selection'] == SELECTION, '纸面和转向沿用试补')
    check(mount['allocation']['cut'] == [0, 0, 8, 12], '仍只认当初取样的一刀')
    check(len(api('sheets/S1')['cuts']) == 1, '整块贴用不再占用第二处纸料')
    zone = doc.board()['zones'][0]
    check(zone['coverage'] == {'target': 96, 'placed': 96, 'remaining': 0}, '按实际覆盖完工')
    doc.change('finish', {})
    release = api(f'documents/{doc.id}/releases', {"expected": doc.version})
    signed = api(f'documents/{doc.id}/releases/{release["version"]}')
    row = signed['manifest'][0]
    check(row['whole'] is True and row['trial'] == 'T1' and row['cut'] == [0, 0, 8, 12],
          '签件逐片记明整块试样的实物、刀口与来源')
    check(row['destination'] == [10, 10, 22, 18] and row['origin'] == [10, 10], '签件记明贴放位置')
    check(row['sheet'] == 'S1' and row['face'] == 'front' and row['turn'] == 90, '签件保留纸面与转向')
    trial = signed['inputs']['zones'][0]['trials'][0]
    check(trial['status'] == 'accepted' and [r['hour'] for r in trial['rows']] == [0, 24],
          '签件内含观察判定依据')
    check(api(f'documents/{doc.id}/releases/{release["version"]}/replay')['consistent'],
          '整块贴用签件可独立复算')
    csv = api(f'documents/{doc.id}/releases/{release["version"]}/csv', raw=True)
    check(b'0 0 8 12' in csv and b'10 10 22 18' in csv, '裁切 CSV 记实际取纸与贴放')
    return doc, signed


def scenario_guards(api):
    """Observed sample still obeys notch bounds, in-place pieces and the live lot."""
    doc = Doc(api, 'D5', [[0, 0], [24, 0], [24, 8], [0, 8]])
    doc.trial('T1', [20, 0, 28, 12])
    doc.observe_all('T1')
    refuse(doc, 'mount', {"id": "PX", "trial": "T1", "origin": [24, 0]}, 422,
           '整块贴用不能越出缺口')
    refuse(doc, 'mount', {"id": "PS", "trial": "T1", "origin": [0, 0],
                          "selection": {**SELECTION, "turn": 0}}, 422,
           '整块贴用的纸面和转向不得与试补不一致')
    doc.trial('T2', [30, 0, 38, 12])
    doc.observe_all('T2')
    doc.change('mount', {"id": "P1", "trial": "T2", "origin": [0, 0]})
    refuse(doc, 'mount', {"id": "PY", "trial": "T1", "origin": [6, 0]}, 409,
           '整块贴用不能压到在位补片')
    refuse(doc, 'mount', {"id": "PZ", "trial": "T1", "origin": [12, 0], "cut": [24, 0, 32, 12]}, 422,
           '整块贴用只认试补当初的一刀')
    # Primary convenience route: the sample may be mounted through ``patch`` with no cut.
    doc.change('patch', {"id": "P2", "trial": "T1", "origin": [12, 0]})
    check(doc.board()['zones'][0]['coverage']['remaining'] == 0, 'patch 路由也可整块贴用并填满缺口')
    # A retired lot may no longer take new patches, whole or cut.
    api('lots', {"id": "LOT2", "label": "整片演练批 · 备用"})
    api('sheets', SHEET2)
    spare = {**SELECTION, "sheet": "S2"}
    doc.change('trial', {"id": "T3", "selection": spare, "cut": [0, 0, 8, 12]})
    doc.observe_all('T3')
    api('retire', {"id": "LOT2", "reason": "停用演练批次"})
    refuse(doc, 'mount', {"id": "P3", "trial": "T3", "origin": [24, 0]}, 409,
           '已停用纸批不能整块贴用')
    return doc


def scenario_duplicate_sample(api):
    """The same physical sample cannot be registered as a second piece at a free spot."""
    doc = Doc(api, 'D2', [[0, 0], [24, 0], [24, 8], [0, 8]])
    doc.trial('T1', [80, 0, 88, 12])
    doc.observe_all('T1')
    doc.change('mount', {"id": "P1", "trial": "T1", "origin": [0, 0]})
    refuse(doc, 'mount', {"id": "P2", "trial": "T1", "origin": [12, 0]}, 409,
           '同一块已贴试样不能换个正好放得下的空位再登记')
    check(doc.board()['zones'][0]['coverage']['placed'] == 96, '重复登记不增加覆盖')
    doc.trial('T2', [90, 0, 98, 12])
    doc.observe_all('T2')
    doc.change('mount', {"id": "P2", "trial": "T2", "origin": [12, 0]})
    check(doc.board()['zones'][0]['coverage']['remaining'] == 0, '另一块实物试样接续填满缺口')
    doc.change('finish', {})
    release = api(f'documents/{doc.id}/releases', {"expected": doc.version})
    signed = api(f'documents/{doc.id}/releases/{release["version"]}')

    # A successor can recompute a tampered signed release that reports one sample twice.
    forged = copy.deepcopy(signed)
    zones = forged['inputs']['zones']
    first, second = zones[0]['patches']
    clone = copy.deepcopy(first)
    clone['id'] = 'PX'
    clone['destination'] = [12, 0, 24, 8]
    clone['origin'] = [12, 0]
    zones[0]['patches'] = [first, clone]
    for trial in zones[0]['trials']:
        if trial['id'] == first['trial']:
            trial['mounts'] = [*trial['mounts'], {'patch': 'PX', 'revision': 1, 'origin': [12, 0]}]
    payload = {key: value for key, value in forged.items() if key != 'sha256'}
    forged['sha256'] = codec.digest(payload)
    # Replaying the frozen evidence itself must fail on the duplicated physical sample,
    # even though the two rectangles do not overlap and together fill the notch.
    expect(lambda: replay.reconstruct(forged['inputs']), 409,
           '复算拒绝同一试样报成两块在位片')
    expect(lambda: archive.verify(forged), 409, '签件将同一试样报成两块在位片即拒绝')
    check(second['trial'] == 'T2', '合法签件两片来自不同实物试样')

    # A signature that simply flips the two valid placements' origins is also refused,
    # because each piece is pinned by its own trial's recorded use.
    moved = copy.deepcopy(signed)
    moved['inputs']['zones'][0]['patches'][0]['origin'] = [12, 0]
    moved['inputs']['zones'][0]['patches'][0]['destination'] = [12, 0, 24, 8]
    moved['sha256'] = codec.digest({key: value for key, value in moved.items() if key != 'sha256'})
    expect(lambda: archive.verify(moved), 409, '签件改动贴放位置即拒绝')
    return signed


def scenario_reopen(api):
    """After reopen the old piece leaves live coverage; the sample still shows its use."""
    doc = Doc(api, 'D3', [[10, 10], [22, 10], [22, 18], [10, 18]])
    doc.trial('T1', [40, 0, 48, 12])
    doc.observe_all('T1')
    doc.change('mount', {"id": "P1", "trial": "T1", "origin": [10, 10]})
    doc.change('finish', {})
    doc.change('reopen', {"reason": "重做边部"})
    board = doc.board()
    check(board['zones'][0]['coverage']['placed'] == 0, '复开后旧贴片退出当前覆盖')
    used = [row for row in board['used_samples'] if row['trial'] == 'T1']
    check(len(used) == 1 and used[0]['cut'] == [40, 0, 48, 12], '复开后仍可查该试样已贴用')
    check(used[0]['mounts'][0]['patch'] == 'P1' and used[0]['mounts'][0]['origin'] == [10, 10],
          '试样保留贴用位置')
    check([40, 0, 48, 12] in [row['cut'] for row in api('sheets/S1')['cuts']], '原切口仍不可取纸')
    doc.trial('T2', [50, 0, 58, 12])
    refuse(doc, 'trial', {"id": "T3", "selection": SELECTION, "cut": [44, 4, 52, 16]}, 409,
           '原切口占用挡住相邻取样')
    return doc


def scenario_legacy(api):
    """Signatures sealed before whole-sample placements keep reading and replaying."""
    doc = Doc(api, 'D4', [[0, 0], [12, 0], [12, 8], [0, 8]])
    doc.trial('T1', [60, 0, 68, 12])
    doc.observe_all('T1')
    doc.change('patch', {"id": "P1", "trial": "T1", "cut": [70, 0, 78, 12], "origin": [0, 0]})
    doc.change('finish', {})
    release = api(f'documents/{doc.id}/releases', {"expected": doc.version})
    signed = api(f'documents/{doc.id}/releases/{release["version"]}')
    legacy = copy.deepcopy(signed)
    legacy['format'] = 1
    legacy['inputs'].pop('format', None)
    legacy['manifest'] = [{key: value for key, value in row.items() if key not in ('whole', 'origin')}
                          for row in legacy['manifest']]
    legacy['sha256'] = codec.digest({key: value for key, value in legacy.items() if key != 'sha256'})
    rows = archive.verify(legacy)
    check(rows and rows[0]['cut'] == [70, 0, 78, 12], '旧同条件签件照常复算')


def scenario_payloads(api):
    """The whole sample may be registered through mount or patch, echoing its own cut."""
    doc = Doc(api, 'D7', [[0, 0], [12, 0], [12, 8], [0, 8]])
    doc.trial('T1', [0, 20, 8, 32])
    doc.observe_all('T1')
    patch = doc.change('patch', {"id": "P1", "trial": "T1", "cut": [0, 20, 8, 32], "origin": [0, 0]})
    check(patch['whole'] is True and patch['destination'] == [0, 0, 12, 8],
          'patch 回填试补同一刀即整块贴用并按 90 度贴入')
    before = len(api('sheets/S1')['cuts'])
    refuse(doc, 'patch', {"id": "P2", "trial": "T1", "cut": [0, 20, 8, 32], "origin": [0, 0]}, 409,
           '整块试样也不能借 patch 重复登记')
    check(len(api('sheets/S1')['cuts']) == before, '被拒的重复登记不另占纸料')
    doc2 = Doc(api, 'D8', [[0, 0], [12, 0], [12, 8], [0, 8]])
    doc2.trial('T1', [10, 20, 18, 32])
    doc2.observe_all('T1')
    after_trial = len(api('sheets/S1')['cuts'])
    check(doc2.change('whole', {"id": "P1", "trial": "T1", "origin": [0, 0]})['whole'] is True,
          'whole 别名同样登记整块贴用')
    check(len(api('sheets/S1')['cuts']) == after_trial == before + 1,
          '整块贴用不在实物纸页上另占一处')
    return doc


def main():
    with server() as api:
        print('整块试样填小缺口')
        scenario_whole_sample(api)
        print('缺口、在位片、唯一刀口与停用批次')
        scenario_guards(api)
        print('同一实物不得重复登记与签件篡改')
        scenario_duplicate_sample(api)
        print('复开后追溯')
        scenario_reopen(api)
        print('旧签件兼容')
        scenario_legacy(api)
        print('两种登记路由')
        scenario_payloads(api)
    print('整块试样贴用检查通过')


if __name__ == '__main__':
    main()
