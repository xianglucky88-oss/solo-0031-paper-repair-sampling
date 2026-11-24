"""Exercise adopting a new repair rule mid-work through live HTTP.

Covers carrying observations across rules, skipped time points, failures under
the earlier rule, the new sample-size check, patches that stay tied to the old
rule, and recomputation of a release sealed before switching existed.
"""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from paperbench import httpd, replay
from paperbench.database import Database

OLD = {'id': 'R-OLD', 'thickness_gap': 18, 'ph_gap': 5, 'color_gap': 35,
       'hours': [0, 24], 'drift': 20, 'sample_edge': 5}
NEW = {'id': 'R-NEW', 'thickness_gap': 18, 'ph_gap': 5, 'color_gap': 35,
       'hours': [0, 12, 24], 'drift': 30, 'sample_edge': 9}
TIGHT = {'id': 'R-TIGHT', 'thickness_gap': 18, 'ph_gap': 5, 'color_gap': 20,
         'hours': [0, 24], 'drift': 20, 'sample_edge': 5}
FADED = {'id': 'S6', 'lot': 'L5', 'width': 100, 'height': 75,
         'stock': {'thickness': 95, 'ph': 70, 'grain': 'x'},
         'faces': {'front': {'condition': 'D50', 'lab': {'l': 735, 'a': 33, 'b': 145}},
                   'back': {'condition': 'D50', 'lab': {'l': 700, 'a': 20, 'b': 130}}}}
SHEET = {'id': 'S5', 'lot': 'L5', 'width': 100, 'height': 75,
         'stock': {'thickness': 95, 'ph': 70, 'grain': 'x'},
         'faces': {'front': {'condition': 'D50', 'lab': {'l': 765, 'a': 33, 'b': 145}},
                   'back': {'condition': 'D50', 'lab': {'l': 700, 'a': 20, 'b': 130}}}}
ZONE = {'id': 'Z1', 'label': '矩形演练区', 'outline': [[10, 10], [30, 10], [30, 30], [10, 30]],
        'stock': {'thickness': 95, 'ph': 70, 'grain': 'x'},
        'surface': {'condition': 'D50', 'lab': {'l': 765, 'a': 33, 'b': 145}}}
SELECTION = {'sheet': 'S5', 'face': 'front', 'turn': 0}


def check(condition, description):
    if not condition:
        raise AssertionError(description)


class QuietHandler(httpd.Handler):
    def log_message(self, message, *args):
        pass


class Client:
    def __init__(self, url):
        self.url = url

    def http(self, path, value=None, status=200):
        headers = {'Content-Type': 'application/json'} if value is not None else {}
        body = json.dumps(value).encode() if value is not None else None
        try:
            resource = urlopen(Request(self.url + path, body, headers), timeout=5)
        except HTTPError as exc:
            resource = exc
        with resource as response:
            data = response.read()
            check(response.code == status, f'{path}: expected {status}, got {response.code}: {data[:300]!r}')
        return json.loads(data)

    def api(self, path, value=None, status=200):
        return self.http('/api/' + path, value, status)


class Live:
    """Track one document's live version while posting its actions."""

    def __init__(self, client, key):
        self.client, self.key, self.version = client, key, 0

    def post(self, tail, body, status=200):
        result = self.client.api(f'documents/{self.key}/{tail}',
                                 {**body, 'expected': self.version}, status)
        if status == 200:
            check(result['version'] == self.version + 1, f'{self.key}/{tail} advances one version')
            self.version += 1
        return result

    def board(self):
        return self.client.api(f'documents/{self.key}')

    def zone(self):
        return self.post('zone', {'data': ZONE})

    def trial(self, key, cut):
        return self.post('trial', {'zone': 'Z1', 'data': {'id': key, 'selection': SELECTION, 'cut': cut}})

    def observe(self, key, hour, drift, status=200):
        observation = {'hour': hour, 'drift': drift, 'lifting': False, 'note': f'{hour} h 记录'}
        return self.post('observe', {'zone': 'Z1', 'data': {'id': key, 'observation': observation}}, status)

    def patch(self, key, trial, cut, status=200):
        return self.post('patch', {'zone': 'Z1',
                                   'data': {'id': key, 'trial': trial, 'cut': cut, 'origin': [10, 10]}}, status)

    def adopt(self, rule, status=200):
        return self.post('adopt', {'data': {'rule': rule}}, status)

    def finish(self):
        return self.post('finish', {'zone': 'Z1', 'data': {}})

    def seal(self):
        return self.client.api(f'documents/{self.key}/releases', {'expected': self.version})

    def trial_of(self, key):
        return next(trial for zone in self.board()['zones'] for trial in zone['trials'] if trial['id'] == key)


def register(client):
    client.api('rules', OLD)
    client.api('rules', NEW)
    client.api('rules', TIGHT)
    client.api('lots', {'id': 'L5', 'label': '切换演练批次'})
    client.api('sheets', SHEET)
    client.api('sheets', FADED)
    client.api('sheets', {**SHEET, 'id': 'S7'})


def make_doc(client, key):
    client.api('documents', {'id': key, 'title': f'{key} 演练', 'width': 120, 'height': 90, 'rule': OLD['id']})
    live = Live(client, key)
    live.zone()
    return live


def sheet_cuts(client):
    return client.api('sheets/S5')['cuts']


def carried(client):
    """A trial observed only at 0 h may continue at the added 12 h and 24 h."""
    live = make_doc(client, 'FOL-10')
    live.trial('T1', [0, 0, 20, 20])
    live.observe('T1', 0, 3)
    live.adopt(NEW['id'])
    board = live.board()
    check(board['rule']['id'] == NEW['id'], 'new rule is current after adoption')
    check([entry['rule']['id'] for entry in board['rules']] == [OLD['id'], NEW['id']],
          'the earlier rule stays in the record')
    check(board['rules'][-1]['from'] == live.version, 'the switch starts at this live version')
    live.adopt(NEW['id'], 409)
    live.adopt(OLD['id'], 409)
    judgment = live.trial_of('T1')['judgment']
    check(judgment['next'] == 12 and judgment['continuable'], 'added 12 h can be observed')

    live.observe('T1', 24, 3, 409)
    live.observe('T1', 12, 3)
    live.observe('T1', 24, 3)
    trial = live.trial_of('T1')
    check(trial['status'] == 'accepted' and trial['judgment']['eligible'], 'ordinal continuation releases trial')

    live.patch('P1', 'T1', [40, 0, 60, 20])
    live.finish()
    receipt = live.seal()
    release = client.api(f'documents/FOL-10/releases/{live.version}')
    row = release['manifest'][0]
    check(row['rule'] == NEW['id'], 'patch records the rule in force when applied')
    check([item['hour'] for item in row['reused']] == [0] and row['reused'][0]['rule'] == OLD['id'],
          'patch carries the original 0 h observation reused across rules')
    check(client.api(f'documents/FOL-10/releases/{live.version}/replay')['consistent'], 'continued release replays')
    check(sum(1 for cut in sheet_cuts(client) if cut['key'] == 'FOL-10:trial:T1') == 1,
          'the sample was cut once')
    return receipt


def skipped(client):
    """A trial that already observed past the added hour cannot be reused."""
    live = make_doc(client, 'FOL-11')
    live.trial('T1', [20, 0, 40, 20])
    live.observe('T1', 0, 3)
    live.observe('T1', 24, 3)
    check(live.trial_of('T1')['status'] == 'accepted', 'complete under the old rule')
    before = sheet_cuts(client)
    live.adopt(NEW['id'])
    trial = live.trial_of('T1')
    check(trial['judgment']['skipped'] == [12] and not trial['judgment']['eligible'],
          'skipped 12 h blocks eligibility')
    live.observe('T1', 12, 3, 409)
    live.patch('P1', 'T1', [60, 0, 80, 20], 409)
    after = sheet_cuts(client)
    check(any(cut['key'] == 'FOL-11:trial:T1' for cut in after), 'old sample stays reserved')
    check(len(before) == len(after), 'a rejected patch reserves nothing')

    live.trial('T2', [40, 20, 60, 40])
    live.observe('T2', 0, 3)
    live.observe('T2', 12, 3)
    live.observe('T2', 24, 3)
    live.patch('P2', 'T2', [60, 0, 80, 20])
    check(live.trial_of('T2')['judgment']['eligible'], 'a fresh trial passes the new rule')
    live.finish()
    live.seal()
    sealed = client.api(f'documents/FOL-11/releases/{live.version}')
    check([row['trial'] for row in sealed['manifest']] == ['T2'],
          'the skipped trial contributes no patch to the sealed evidence')


def failed(client):
    """A trial failed under the old rule cannot be revived by a looser limit."""
    live = make_doc(client, 'FOL-12')
    live.trial('T1', [0, 20, 20, 40])
    live.observe('T1', 0, 25)
    check(live.trial_of('T1')['status'] == 'failed', 'old drift limit fails at 0 h')
    live.adopt(NEW['id'])
    trial = live.trial_of('T1')
    check(trial['judgment']['permanently_failed'] and not trial['judgment']['continuable'],
          'old failure stays final under the looser rule')
    live.observe('T1', 12, 3, 409)
    live.patch('P1', 'T1', [60, 20, 80, 40], 409)

    live.trial('T2', [20, 20, 40, 40])
    live.observe('T2', 0, 28)
    live.observe('T2', 12, 28)
    live.observe('T2', 24, 28)
    live.patch('P2', 'T2', [60, 20, 80, 40])
    live.finish()
    live.seal()
    release = client.api(f'documents/FOL-12/releases/{live.version}')
    check(release['manifest'][0]['rule'] == NEW['id'], 'new trial uses the loosened drift limit')


def undersized(client):
    """A cut that predates the bigger minimum edge still cannot authorise a patch."""
    live = make_doc(client, 'FOL-13')
    live.trial('T1', [60, 60, 68, 68])
    live.observe('T1', 0, 3)
    live.adopt(NEW['id'])
    live.observe('T1', 12, 3)
    live.observe('T1', 24, 3)
    check(live.trial_of('T1')['judgment']['eligible'], 'observations carry over under the new rule')
    before = sheet_cuts(client)
    live.patch('P1', 'T1', [80, 40, 100, 60], 409)
    check(sheet_cuts(client) == before, 'the too-small sample authorises nothing and reserves nothing')


def old_patches(client):
    """Patches granted under the old rule stay verifiable under that rule."""
    live = make_doc(client, 'FOL-14')
    live.trial('T1', [0, 40, 20, 60])
    live.observe('T1', 0, 3)
    live.observe('T1', 24, 3)
    live.patch('P1', 'T1', [20, 40, 40, 60])
    live.adopt(NEW['id'])
    live.patch('P2', 'T1', [80, 20, 100, 40], 409)
    live.finish()
    live.seal()
    release = client.api(f'documents/FOL-14/releases/{live.version}')
    check(release['manifest'][0]['rule'] == OLD['id'], 'old patch keeps the old rule in evidence')
    check(release['inputs']['document']['rule']['id'] == NEW['id'], 'sealed document shows the new current rule')
    check(client.api(f'documents/FOL-14/releases/{live.version}/replay')['consistent'],
          'old patch replays under the rule that granted it')
    check([entry['rule']['id'] for entry in release['inputs']['document']['rule_history']] == [OLD['id'], NEW['id']],
          'both rules are frozen in the release')


def stricter(client):
    """An observation that met the old limit but misses the new one cannot carry over."""
    client.api('documents', {'id': 'FOL-16', 'title': '收紧阈值演练', 'width': 120, 'height': 90,
                             'rule': NEW['id']})
    live = Live(client, 'FOL-16')
    live.zone()
    own = {**SELECTION, 'sheet': 'S7'}
    live.post('trial', {'zone': 'Z1', 'data': {'id': 'T1', 'selection': own, 'cut': [0, 50, 20, 70]}})
    live.observe('T1', 0, 25)
    live.observe('T1', 12, 25)
    live.observe('T1', 24, 25)
    check(live.trial_of('T1')['judgment']['eligible'], 'drift 2.5 is within the loose limit')
    live.adopt(OLD['id'])
    trial = live.trial_of('T1')
    check(trial['judgment']['rejected'] and not trial['judgment']['continuable'],
          'recorded 2.5 misses the stricter 2.0 limit and cannot be reused')
    live.observe('T1', 24, 3, 409)
    live.patch('P1', 'T1', [80, 40, 100, 60], 409)
    live.post('trial', {'zone': 'Z1', 'data': {'id': 'T2', 'selection': own, 'cut': [20, 50, 40, 70]}})
    live.observe('T2', 0, 3)
    live.observe('T2', 24, 3)
    live.patch('P2', 'T2', [80, 40, 100, 60])
    check(live.trial_of('T2')['judgment']['authorizing'], 'a fresh trial under the stricter rule works')


def refit(client):
    """A sample whose face fit the old rule must pass the new rule's fit again."""
    client.api('documents', {'id': 'FOL-15', 'title': '换面演练', 'width': 120, 'height': 90, 'rule': OLD['id']})
    live = Live(client, 'FOL-15')
    live.zone()
    faded = {**SELECTION, 'sheet': 'S6'}
    live.post('trial', {'zone': 'Z1', 'data': {'id': 'T1', 'selection': faded, 'cut': [0, 50, 20, 70]}})
    live.observe('T1', 0, 3)
    live.observe('T1', 24, 3)
    check(live.trial_of('T1')['judgment']['eligible'], 'face fit the old colour limit')
    live.adopt(TIGHT['id'])
    before = sheet_cuts(client)
    live.patch('P1', 'T1', [80, 40, 100, 60], 409)
    check(len(sheet_cuts(client)) == len(before), 'failed refit reserves nothing')
    live.observe('T1', 12, 3, 409)
    check(live.trial_of('T1')['judgment']['eligible'], 'observations alone still look eligible')
    check(len(sheet_cuts(client)) == len(before), 'but the tighter colour fit still blocks the patch')


def legacy_replay():
    """A release sealed before switching existed still recomputes as-is."""
    inside = {'id': 'Z', 'label': '旧签件', 'outline': [[10, 10], [30, 10], [30, 30], [10, 30]],
              'revision': 1, 'stock': ZONE['stock'], 'surface': ZONE['surface'], 'complete': True}
    trial = {'id': 'T', 'zone': 'Z', 'revision': 1, 'selection': SELECTION, 'status': 'accepted',
             'allocation': {'key': 'OLD:trial:T', 'document': 'OLD', 'zone': 'Z', 'revision': 1,
                            'kind': 'trial', 'id': 'T', 'cut': [0, 0, 20, 20]},
             'rows': [{'hour': 0, 'drift': 3, 'lifting': False, 'note': 'a'},
                      {'hour': 24, 'drift': 3, 'lifting': False, 'note': 'b'}]}
    patch = {'id': 'P', 'zone': 'Z', 'revision': 1, 'trial': 'T', 'selection': SELECTION,
             'allocation': {'key': 'OLD:patch:P', 'document': 'OLD', 'zone': 'Z', 'revision': 1,
                            'kind': 'patch', 'id': 'P', 'cut': [40, 0, 60, 20]},
             'destination': [10, 10, 30, 30]}
    inputs = {'document': {'id': 'OLD', 'title': '旧签件', 'width': 120, 'height': 90, 'rule': OLD},
              'version': 1, 'zones': [{**inside, 'trials': [trial], 'patches': [patch]}],
              'sheets': {'S5': {**SHEET}}}
    rows = replay.reconstruct(inputs)
    check(rows == [{'zone': 'Z', 'revision': 1, 'patch': 'P', 'trial': 'T', 'sheet': 'S5', 'lot': 'L5',
                    'face': 'front', 'turn': 0, 'cut': [40, 0, 60, 20], 'destination': [10, 10, 30, 30],
                    'rule': OLD['id']}], 'legacy manifest recomputes byte-for-byte')


def main():
    with TemporaryDirectory(prefix='paperbench-switch-') as tmp:
        with httpd.server(Database(Path(tmp) / 'work.sqlite3'), 0) as server:
            server.RequestHandlerClass = QuietHandler
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                client = Client(f'http://127.0.0.1:{server.server_address[1]}')
                register(client)
                carried(client)
                skipped(client)
                failed(client)
                undersized(client)
                old_patches(client)
                refit(client)
                stricter(client)
                legacy_replay()
            finally:
                server.shutdown()
                thread.join()
    print('通过 switch')


if __name__ == '__main__':
    main()
