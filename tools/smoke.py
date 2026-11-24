"""Exercise bounded live HTTP workflows against a disposable SQLite database."""
import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from paperbench import demo, httpd
from paperbench.database import Database

DOC = 'documents/FOL-07'
ZONE = 'Z1'
SHEET = 'sheets/KOZO-4A'
STAGES = ('rules', 'zone', 'stock', 'preview', 'trial', 'observe', 'patch', 'finish',
          'seal', 'reopen', 'replay', 'export', 'replace')


class QuietHandler(httpd.Handler):
    def log_message(self, message, *args):
        pass


def check(condition, description):
    if not condition:
        raise AssertionError(description)


class Bench:
    def __init__(self, url, through):
        self.url, self.through = url, through
        self.version = 0

    def http(self, path, value=None, status=200, raw=False):
        headers = {'Content-Type': 'application/json'} if value is not None else {}
        body = json.dumps(value).encode() if value is not None else None
        request = Request(self.url + path, body, headers)
        try:
            resource = urlopen(request, timeout=5)
        except HTTPError as exc:
            resource = exc
        with resource as response:
            data = response.read()
            check(response.code == status, f'{path}: expected {status}, got {response.code}: {data[:300]!r}')
        return data if raw else json.loads(data)

    def api(self, path, *args, **kwargs):
        return self.http('/api/' + path, *args, **kwargs)

    def change(self, action, data, status=200, expected=None):
        request = {'expected': self.version if expected is None else expected, 'data': data}
        if action != 'zone':
            request['zone'] = ZONE
        result = self.api(f'{DOC}/{action}', request, status)
        if status == 200:
            self.version += 1
            check(self.version == result['version'], 'mutation advances one version')
            return result['result']

    def stage(self, name):
        print(f'通过 {name}')
        return self.through == name


def exercise(b):
    sample = dict(demo.requests())
    check(b'type="module"' in b.http('/', raw=True), 'native web entry')
    check(b'import' in b.http('/js/app.js', raw=True), 'module served')
    rule = b.api('rules', sample['rules'])
    check(rule == b.api('rules', sample['rules']), 'rule repeat')
    b.api('rules', {**rule, 'drift': 1}, 409)
    if b.stage('rules'): return

    b.api('documents', sample['documents'])
    zone = sample[f'{DOC}/zone']['data']
    b.change('zone', {**zone, 'outline': [[1, 1], [2, 3], [3, 3], [3, 1]]}, 422)
    b.change('zone', zone)
    b.change('zone', {**zone, 'id': 'OVERLAP'}, 422)
    check(b.api(DOC)['zones'][0]['coverage']['target'] == 804, 'L-shaped area')
    if b.stage('zone'): return

    b.api('lots', sample['lots'])
    stocks = [body for path, body in demo.requests() if path == 'sheets']
    for stock in stocks:
        b.api('sheets', stock)
    check(b.api(SHEET)['cuts'] == [], 'no initial reservations')
    b.api('sheets', {**stocks[0], 'width': 70}, 409)
    if b.stage('stock'): return

    trial = sample[f'{DOC}/trial']['data']
    selected = trial['selection']
    def preview(**changes):
        return b.api(f'{DOC}/preview', {'zone': ZONE, 'selection': {**selected, **changes}})
    check(preview()['compatible'], 'matching face and rotation')
    check(preview(face='back')['checks']['color'] is None, 'different condition is not comparable')
    check(preview(face='back', sheet='KOZO-4B', turn=0)['checks']['color'] is False, 'same condition can still fail Lab')
    check(not preview(turn=0)['checks']['grain'], 'unrotated grain mismatch')
    check(b.api(DOC)['version'] == 1 and not b.api(SHEET)['cuts'], 'preview is read-only')
    if b.stage('preview'): return

    b.change('trial', {**trial, 'cut': [0, 0, 2, 2]}, 422)
    b.change('trial', trial)
    b.change('trial', {**trial, 'id': 'STALE'}, 409, expected=1)
    b.api('documents', {**sample['documents'], 'id': 'FOL-08'})
    back_zone = {**zone, 'surface': stocks[0]['faces']['back']}
    b.api('documents/FOL-08/zone', {'expected': 0, 'data': back_zone})
    back_trial = {**trial, 'selection': {**selected, 'face': 'back'}}
    check(b.api('documents/FOL-08/preview', {'zone': ZONE, 'selection': back_trial['selection']})['compatible'],
          'other artifact can use the reverse face')
    b.api('documents/FOL-08/trial', {'expected': 1, 'zone': ZONE, 'data': back_trial}, 409)
    check(len(b.api(SHEET)['cuts']) == 1 and b.api('documents/FOL-08')['version'] == 1, 'global cut, atomic conflict')
    if b.stage('trial'): return

    first = sample[f'{DOC}/observe']['data']
    last = {**first, 'observation': {**first['observation'], 'hour': 24, 'note': '仍平整'}}
    b.change('observe', last, 409)
    check(b.change('observe', first)['status'] == 'pending', 'early evidence does not release trial')
    check(b.change('observe', last)['status'] == 'accepted', 'second time point releases trial')
    b.change('observe', last, 409)
    if b.stage('observe'): return

    top = {'id': 'P1', 'trial': 'T1', 'cut': [20, 0, 36, 38], 'origin': [66, 55]}
    bottom = {'id': 'P2', 'trial': 'T1', 'cut': [36, 0, 50, 14], 'origin': [90, 71]}
    b.change('patch', {**bottom, 'origin': [76, 71]}, 422)
    check(len(b.api(SHEET)['cuts']) == 1, 'rejected shape did not reserve stock')
    check(b.change('patch', top)['destination'] == [66, 55, 104, 71], '90 degree footprint')
    b.change('patch', {**bottom, 'origin': [90, 65]}, 409)
    b.change('finish', {}, 409)
    b.change('patch', bottom)
    if b.stage('patch'): return

    b.api(f'{DOC}/releases', {'expected': b.version}, 409)
    b.change('finish', {})
    b.change('patch', bottom, 409)
    if b.stage('finish'): return

    first_version = b.version
    base = f'{DOC}/releases/{first_version}'
    receipt = b.api(f'{DOC}/releases', {'expected': first_version})
    check(receipt == b.api(f'{DOC}/releases', {'expected': first_version}), 'idempotent seal')
    old = b.api(base, raw=True)
    if b.stage('seal'): return

    b.change('reopen', {'reason': '重做边部贴合'})
    b.change('reopen', {'reason': '禁止连续复开'}, 409)
    b.change('patch', {**top, 'id': 'P3'}, 409)
    b.change('trial', {**trial, 'id': 'T2'}, 409)
    check(b.api(DOC)['zones'][0]['coverage']['placed'] == 0, 'live coverage restarts')
    check(b.api(base, raw=True) == old and len(b.api(SHEET)['cuts']) == 3, 'sealed bytes and consumption unchanged')
    if b.stage('reopen'): return

    new_trial = {**trial, 'id': 'T2', 'cut': [50, 0, 58, 8]}
    b.change('trial', new_trial)
    b.change('observe', {**first, 'id': 'T2'})
    b.change('observe', {**last, 'id': 'T2'})
    b.change('patch', {**top, 'id': 'P3', 'trial': 'T2', 'cut': [60, 0, 76, 38]})
    b.change('patch', {**bottom, 'id': 'P4', 'trial': 'T2', 'cut': [76, 0, 90, 14]})
    b.change('finish', {})
    b.api('retire', {'id': 'KOZO-4', 'reason': '停用演练批次'})
    b.api('documents/FOL-08/trial', {'expected': 1, 'zone': ZONE, 'data': {**back_trial, 'cut': [95, 0, 103, 8]}}, 409)
    check(b.api(f'{base}/replay')['consistent'], 'retired stock still replays')
    b.api(f'{DOC}/releases', {'expected': b.version})
    changes = b.api(f'{DOC}/compare/{first_version}/{b.version}')['changes']
    check([item['kind'] for item in changes] == ['changed', 'changed'], 'stable target tracking')
    check(len(b.api(f'{DOC}/events')) == b.version, 'complete version provenance')
    if b.stage('replay'): return

    csv = b.api(f'{base}/csv', raw=True)
    check(csv.count(b'\n') == 3 and b'66 55 104 71' in csv, 'two stable cutting rows')
    check(csv == b.api(f'{base}/csv', raw=True) and b.api(f'{base}?download', raw=True) == old, 'stable exports')
    b.api(f'{DOC}/releases/1/csv', status=404)
    if b.stage('export'): return

    replace_one(b, b.version)


def replace_one(b, before_replacement):
    """Lift a single bad piece while the intact one keeps covering."""
    zone = b.api(DOC)['zones'][0]
    check(zone['complete'] and [p['id'] for p in zone['patches']] == ['P3', 'P4'], 'both pieces finished')
    b.change('replace', {'patch': 'MISSING', 'reason': '不存在'}, 409)
    b.change('replace', {'patch': 'P3', 'reason': '贴放偏斜'})
    zone = b.api(DOC)['zones'][0]
    check([p['id'] for p in zone['patches']] == ['P4'], 'only the named piece is lifted')
    check([p['id'] for p in zone['withdrawn']] == ['P3'], 'the piece is recorded as withdrawn')
    check(zone['coverage']['placed'] == 196, 'the intact piece still counts as cover')
    check(zone['patches'][0]['revision'] == 2 and zone['patches'][0]['trial'] == 'T2',
          'retained piece keeps its revision and trial')
    b.api(f'{DOC}/releases', {'expected': b.version}, 409)
    # The lifted piece's cut stays consumed, and its refit may not borrow it.
    b.change('patch', {'id': 'P5', 'trial': 'T2', 'cut': [60, 0, 76, 38], 'origin': [66, 55]}, 409)
    # The original lot is retired, so its trial cannot back a newly cut piece.
    b.change('patch', {'id': 'P5', 'trial': 'T2', 'cut': [4, 40, 20, 78], 'origin': [66, 55]}, 409)
    # A fresh trial in this rework may use a newly registered, active sheet.
    base_sheet = next(body for path, body in demo.requests() if path == 'sheets' and body['id'] == 'KOZO-4A')
    b.api('lots', {'id': 'KOZO-5', 'label': '楮皮试制 · 第五批'})
    b.api('sheets', {**base_sheet, 'id': 'KOZO-5A', 'lot': 'KOZO-5'})
    fresh = dict(demo.requests())[f'{DOC}/trial']['data']
    b.change('trial', {**fresh, 'id': 'T3', 'selection': {**fresh['selection'], 'sheet': 'KOZO-5A'},
                       'cut': [60, 0, 68, 8]})
    observation = dict(demo.requests())[f'{DOC}/observe']['data']
    b.change('observe', {**observation, 'id': 'T3'})
    b.change('observe', {**observation, 'id': 'T3',
                         'observation': {**observation['observation'], 'hour': 24, 'note': '仍平整'}})
    b.change('patch', {'id': 'P5', 'trial': 'T3', 'cut': [0, 30, 16, 68], 'origin': [66, 55]})
    b.change('finish', {})
    second = b.version
    b.api(f'{DOC}/releases', {'expected': second})
    release = b.api(f'{DOC}/releases/{second}')
    check([row['revision'] for row in release['manifest']] == [2, 3],
          'manifest names the revision each piece was set in')
    check(b.api(f'{DOC}/releases/{second}/replay')['consistent'], 'replacement release replays')
    check(b.api(f'{DOC}/releases/{second}?download', raw=True) == b.api(f'{DOC}/releases/{second}', raw=True),
          'replacement release downloads unchanged')
    changes = b.api(f'{DOC}/compare/{before_replacement}/{second}')['changes']
    check([item['kind'] for item in changes] == ['changed'],
          'only the refitted position changes, the untouched piece does not')
    # Replacing again on an active sheet may carry the lifted piece's own
    # accepted trial over, with no new sample and no extra observation round.
    b.change('replace', {'patch': 'P5', 'reason': '边角仍开'})
    b.change('patch', {'id': 'P6', 'trial': 'T3', 'cut': [16, 30, 32, 68], 'origin': [66, 55]})
    b.change('finish', {})
    third = b.version
    b.api(f'{DOC}/releases', {'expected': third})
    release = b.api(f'{DOC}/releases/{third}')
    check([(row['patch'], row['revision'], row['trial']) for row in release['manifest']]
          == [('P4', 2, 'T2'), ('P6', 4, 'T3')], 'kept basis is recorded with its original revision')
    check(b.api(f'{DOC}/releases/{third}/replay')['consistent'], 'carried-over basis replays')
    check([item['kind'] for item in b.api(f'{DOC}/compare/{second}/{third}')['changes']] == ['changed'],
          'second replacement again touches only one piece')
    # A retired batch still explains every piece already stuck down, but the
    # same lot may no longer be cut for a new one.
    b.api('retire', {'id': 'KOZO-5', 'reason': '演练停用新纸页批次'})
    b.change('replace', {'patch': 'P4', 'reason': '边部再换'})
    b.change('patch', {'id': 'P7', 'trial': 'T2', 'cut': [90, 0, 106, 38], 'origin': [90, 71]}, 409)
    b.change('finish', {}, 409)
    if b.stage('replace'): return


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--through', default='replace', choices=STAGES)
    args = parser.parse_args()
    with TemporaryDirectory(prefix='paperbench-') as tmp:
        with httpd.server(Database(Path(tmp) / 'work.sqlite3'), 0) as server:
            server.RequestHandlerClass = QuietHandler
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                exercise(Bench(f'http://127.0.0.1:{server.server_address[1]}', args.through))
            finally:
                server.shutdown()
                thread.join()


if __name__ == '__main__':
    main()
