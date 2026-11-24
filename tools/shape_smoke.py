"""End-to-end checks for the whole-piece (single polygon outline) repair feature."""
import json
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from paperbench import archive, httpd
from paperbench.database import Database
from paperbench.errors import Problem

L = [[20, 20], [32, 20], [32, 23], [25, 23], [25, 28], [20, 28]]
RULE = {"id": "R1", "thickness_gap": 18, "ph_gap": 5, "color_gap": 35,
        "hours": [0, 24], "drift": 20, "sample_edge": 5}
SHEET = {"id": "S1", "lot": "LOT", "width": 120, "height": 100,
         "stock": {"thickness": 90, "ph": 69, "grain": "y"},
         "faces": {"front": {"condition": "D50", "lab": {"l": 771, "a": 32, "b": 147}},
                  "back": {"condition": "D65", "lab": {"l": 740, "a": 20, "b": 130}}}}
STOCK = {"thickness": 94, "ph": 70, "grain": "x"}
FRONT_SURFACE = {"condition": "D50", "lab": {"l": 770, "a": 30, "b": 150}}
BACK_SURFACE = {"condition": "D65", "lab": {"l": 740, "a": 20, "b": 130}}


class Quiet(httpd.Handler):
    def log_message(self, *args):
        pass


def check(cond, label):
    if not cond:
        raise AssertionError(label)
    print('  ok:', label)


def rotate_clockwise(points, origin):
    minx = min(x for x, _ in points)
    miny = min(y for _, y in points)
    maxy = max(y for _, y in points)
    height = maxy - miny
    rot = [[(height - 1) - (y - miny) + minx, (x - minx) + minx] for x, y in points]
    rx0 = min(x for x, _ in rot)
    ry0 = min(y for _, y in rot)
    ox, oy = origin
    return [[x - rx0 + ox, y - ry0 + oy] for x, y in rot]


@contextmanager
def server():
    with TemporaryDirectory() as tmp:
        http = httpd.server(Database(Path(tmp) / 'work.sqlite3'), 0)
        http.RequestHandlerClass = Quiet
        thread = Thread(target=http.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{http.server_address[1]}'

        def call(path, value=None):
            data = json.dumps(value).encode() if value is not None else None
            headers = {'Content-Type': 'application/json'} if data else {}
            request = Request(base + '/api/' + path, data, headers)
            try:
                with urlopen(request, timeout=5) as response:
                    return response.code, json.loads(response.read())
            except HTTPError as exc:
                return exc.code, json.loads(exc.read())

        try:
            yield base, call
        finally:
            http.shutdown()


def register_back_trial(call, doc, trial_id, cut):
    call('documents', {"id": doc, "title": doc, "width": 120, "height": 100, "rule": "R1"})
    call(f'documents/{doc}/zone', {"expected": 0, "data": {
        "id": "Z1", "label": "区", "outline": [[0, 60], [10, 60], [10, 70], [0, 70]],
        "stock": STOCK, "surface": BACK_SURFACE}})
    return call(f'documents/{doc}/trial', {"expected": 1, "zone": "Z1", "data": {
        "id": trial_id, "selection": {"sheet": "S1", "face": "back", "turn": 90}, "cut": cut}})


def scenario_a():
    """Edge-touching old cut allowed; placement, 61 mm2 coverage, seal, replay and CSV."""
    with server() as (base, call):
        call('rules', RULE)
        call('lots', {"id": "LOT", "label": "批"})
        call('sheets', SHEET)
        notch = rotate_clockwise(L, [40, 30])
        call('documents', {"id": "D1", "title": "转角件", "width": 120, "height": 100, "rule": "R1"})
        call('documents/D1/zone', {"expected": 0, "data": {
            "id": "Z1", "label": "转角缺口", "outline": notch, "stock": STOCK, "surface": FRONT_SURFACE}})
        call('documents/D1/trial', {"expected": 1, "zone": "Z1", "data": {
            "id": "T1", "selection": {"sheet": "S1", "face": "front", "turn": 90}, "cut": [0, 40, 8, 48]}})
        call('documents/D1/observe', {"expected": 2, "zone": "Z1", "data": {
            "id": "T1", "observation": {"hour": 0, "drift": 3, "lifting": False, "note": "a"}}})
        call('documents/D1/observe', {"expected": 3, "zone": "Z1", "data": {
            "id": "T1", "observation": {"hour": 24, "drift": 4, "lifting": False, "note": "b"}}})
        code, _ = register_back_trial(call, 'D2', 'TB', [25, 23, 31, 28])
        check(code == 200, 'A: edge-touching back-face taking coexists with the planned L piece')

        code, body = call('documents/D1/patch', {"expected": 4, "zone": "Z1", "data": {
            "id": "P9", "trial": "T1", "outline": L, "origin": [40, 30]}})
        check(code == 200, f'A: L piece accepted next to an edge-touching cut: {body}')
        check(body['result']['destination'] == notch, 'A: destination is the 90 CW outline pinned at [40,30]')

        board = call('documents/D1')[1]
        check(board['zones'][0]['coverage'] == {'target': 61, 'placed': 61, 'remaining': 0},
              'A: real coverage is exactly 61 mm2')
        code, _ = call('documents/D1/finish', {"expected": 5, "zone": "Z1", "data": {}})
        check(code == 200, 'A: zone finishes at exact coverage')
        code, _ = call('documents/D1/releases', {"expected": 6})
        check(code == 200, 'A: release sealed')
        code, replay = call('documents/D1/releases/6/replay')
        check(code == 200 and replay['consistent'], 'A: offline replay recomputes placement and occupancy')
        release = call('documents/D1/releases/6')[1]
        check(release['format'] == 2, 'A: new releases use format 2')
        csv_text = urlopen(base + '/api/documents/D1/releases/6/csv').read().decode()
        check('20 20 32 20 32 23 25 23 25 28 20 28' in csv_text, 'A: CSV carries the full outline, not the bbox')

        stored = [row for row in call('sheets/S1')[1]['cuts'] if row['id'] == 'P9'][0]
        check(stored['shape'] == L, 'A: source sheet occupancy is the actual L outline, not its bbox')

        tampered = json.loads(json.dumps(release))
        tampered['inputs']['zones'][0]['patches'][0]['destination'][0][0] += 1
        try:
            archive.verify(tampered)
            raised = False
        except Problem:
            raised = True
        check(raised, 'A: replay rejects a record whose placement outline does not recompute')


def scenario_b():
    """The old rectangular taking moved 1 mm left intersects the piece, so the piece is refused."""
    with server() as (_, call):
        call('rules', RULE)
        call('lots', {"id": "LOT", "label": "批"})
        call('sheets', SHEET)
        notch = rotate_clockwise(L, [40, 30])
        call('documents', {"id": "D1", "title": "转角件", "width": 120, "height": 100, "rule": "R1"})
        call('documents/D1/zone', {"expected": 0, "data": {
            "id": "Z1", "label": "转角缺口", "outline": notch, "stock": STOCK, "surface": FRONT_SURFACE}})
        call('documents/D1/trial', {"expected": 1, "zone": "Z1", "data": {
            "id": "T1", "selection": {"sheet": "S1", "face": "front", "turn": 90}, "cut": [0, 40, 8, 48]}})
        call('documents/D1/observe', {"expected": 2, "zone": "Z1", "data": {
            "id": "T1", "observation": {"hour": 0, "drift": 3, "lifting": False, "note": "a"}}})
        call('documents/D1/observe', {"expected": 3, "zone": "Z1", "data": {
            "id": "T1", "observation": {"hour": 24, "drift": 4, "lifting": False, "note": "b"}}})
        code, _ = register_back_trial(call, 'D2', 'TB', [24, 23, 30, 28])
        check(code == 200, 'B: shifted old rectangular taking is itself valid')
        before = len(call('sheets/S1')[1]['cuts'])
        code, body = call('documents/D1/patch', {"expected": 4, "zone": "Z1", "data": {
            "id": "P9", "trial": "T1", "outline": L, "origin": [40, 30]}})
        check(code == 409, f'B: L piece is refused when the old cut overlaps it: {body}')
        check(len(call('sheets/S1')[1]['cuts']) == before, 'B: refused piece leaves no stock reservation')


def scenario_c():
    """Piece cut first; later back-face rectangular takings: edge one allowed, intersecting one refused."""
    with server() as (_, call):
        call('rules', RULE)
        call('lots', {"id": "LOT", "label": "批"})
        call('sheets', SHEET)
        notch = rotate_clockwise(L, [40, 30])
        call('documents', {"id": "D1", "title": "转角件", "width": 120, "height": 100, "rule": "R1"})
        call('documents/D1/zone', {"expected": 0, "data": {
            "id": "Z1", "label": "转角缺口", "outline": notch, "stock": STOCK, "surface": FRONT_SURFACE}})
        call('documents/D1/trial', {"expected": 1, "zone": "Z1", "data": {
            "id": "T1", "selection": {"sheet": "S1", "face": "front", "turn": 90}, "cut": [0, 40, 8, 48]}})
        call('documents/D1/observe', {"expected": 2, "zone": "Z1", "data": {
            "id": "T1", "observation": {"hour": 0, "drift": 3, "lifting": False, "note": "a"}}})
        call('documents/D1/observe', {"expected": 3, "zone": "Z1", "data": {
            "id": "T1", "observation": {"hour": 24, "drift": 4, "lifting": False, "note": "b"}}})
        code, _ = call('documents/D1/patch', {"expected": 4, "zone": "Z1", "data": {
            "id": "P9", "trial": "T1", "outline": L, "origin": [40, 30]}})
        check(code == 200, 'C: whole piece cut first')

        code, _ = register_back_trial(call, 'D2', 'TE', [25, 23, 31, 28])
        check(code == 200, 'C: edge-touching rectangular taking still works after the piece')
        code, body = register_back_trial(call, 'D3', 'TX', [24, 23, 30, 28])
        check(code == 409, f'C: intersecting rectangular taking is refused after the piece: {body}')


def scenario_d():
    """Placement guards: inside damage zone, no overlap with in-place patches, valid source outline."""
    with server() as (_, call):
        call('rules', RULE)
        call('lots', {"id": "LOT", "label": "批"})
        call('sheets', SHEET)
        call('documents', {"id": "D1", "title": "件", "width": 120, "height": 100, "rule": "R1"})
        # Room for a rect patch plus an L patch placed without rotation (grain y matches turn 0).
        call('documents/D1/zone', {"expected": 0, "data": {
            "id": "Z1", "label": "大区", "outline": [[0, 0], [60, 0], [60, 50], [0, 50]],
            "stock": {**STOCK, "grain": "y"}, "surface": FRONT_SURFACE}})
        call('documents/D1/trial', {"expected": 1, "zone": "Z1", "data": {
            "id": "T1", "selection": {"sheet": "S1", "face": "front", "turn": 0}, "cut": [0, 60, 8, 68]}})
        call('documents/D1/observe', {"expected": 2, "zone": "Z1", "data": {
            "id": "T1", "observation": {"hour": 0, "drift": 3, "lifting": False, "note": "a"}}})
        call('documents/D1/observe', {"expected": 3, "zone": "Z1", "data": {
            "id": "T1", "observation": {"hour": 24, "drift": 4, "lifting": False, "note": "b"}}})

        # turn 0: origin is the bbox top-left and the outline is translated without rotation
        code, body = call('documents/D1/patch', {"expected": 4, "zone": "Z1", "data": {
            "id": "P0", "trial": "T1", "outline": L, "origin": [5, 5]}})
        check(code == 200, f'D: turn-0 whole piece placed: {body}')
        check(body['result']['destination'] == [[x + 5 - 20, y + 5 - 20] for x, y in L],
              'D: turn 0 keeps the outline orientation and pins its bbox to the origin')

        # another piece overlapping the in-place patch must be refused
        code, body = call('documents/D1/patch', {"expected": 5, "zone": "Z1", "data": {
            "id": "P1", "trial": "T1", "outline": L, "origin": [10, 10]}})
        check(code == 409, f'D: overlapping piece refused: {body}')

        # piece extending outside the damage zone is a 422 business-contract failure
        code, body = call('documents/D1/patch', {"expected": 5, "zone": "Z1", "data": {
            "id": "P2", "trial": "T1", "outline": L, "origin": [50, 45]}})
        check(code == 422, f'D: piece leaving the damage zone is refused: {body}')

        # invalid source outline (self-touching) is rejected before any reservation
        bad = [[0, 0], [10, 0], [10, 10], [5, 10], [5, 5], [10, 5], [10, 15], [0, 15]]
        code, body = call('documents/D1/patch', {"expected": 5, "zone": "Z1", "data": {
            "id": "P3", "trial": "T1", "outline": bad, "origin": [0, 0]}})
        check(code == 422, f'D: self-touching source outline is refused: {body}')


def scenario_e():
    """Polygon pieces survive a reopen/reseal and appear correctly in the version comparison."""
    with server() as (_, call):
        call('rules', RULE)
        call('lots', {"id": "LOT", "label": "批"})
        call('sheets', SHEET)
        notch = rotate_clockwise(L, [40, 30])
        call('documents', {"id": "D1", "title": "转角件", "width": 120, "height": 100, "rule": "R1"})
        call('documents/D1/zone', {"expected": 0, "data": {
            "id": "Z1", "label": "转角缺口", "outline": notch, "stock": STOCK, "surface": FRONT_SURFACE}})
        call('documents/D1/trial', {"expected": 1, "zone": "Z1", "data": {
            "id": "T1", "selection": {"sheet": "S1", "face": "front", "turn": 90}, "cut": [0, 40, 8, 48]}})
        call('documents/D1/observe', {"expected": 2, "zone": "Z1", "data": {
            "id": "T1", "observation": {"hour": 0, "drift": 3, "lifting": False, "note": "a"}}})
        call('documents/D1/observe', {"expected": 3, "zone": "Z1", "data": {
            "id": "T1", "observation": {"hour": 24, "drift": 4, "lifting": False, "note": "b"}}})
        # versions after this: zone=1 trial=2 observe=3,4
        call('documents/D1/patch', {"expected": 4, "zone": "Z1", "data": {
            "id": "P9", "trial": "T1", "outline": L, "origin": [40, 30]}})
        call('documents/D1/finish', {"expected": 5, "zone": "Z1", "data": {}})
        # patch=5 finish=6; seal stores version 6
        call('documents/D1/releases', {"expected": 6})

        # Reopen; the new revision restarts coverage but consumed stock stays recorded.
        call('documents/D1/reopen', {"expected": 6, "zone": "Z1", "data": {"reason": "重贴"}})
        # reopen=7; use stock in a free region of the sheet
        call('documents/D1/trial', {"expected": 7, "zone": "Z1", "data": {
            "id": "T2", "selection": {"sheet": "S1", "face": "front", "turn": 90}, "cut": [2, 60, 9, 67]}})
        call('documents/D1/observe', {"expected": 8, "zone": "Z1", "data": {
            "id": "T2", "observation": {"hour": 0, "drift": 3, "lifting": False, "note": "a"}}})
        call('documents/D1/observe', {"expected": 9, "zone": "Z1", "data": {
            "id": "T2", "observation": {"hour": 24, "drift": 4, "lifting": False, "note": "b"}}})
        # trial=8 observe=9,10; same target geometry, but cut from a free L on the source sheet
        shifted_source = [[x, y + 40] for x, y in L]
        call('documents/D1/patch', {"expected": 10, "zone": "Z1", "data": {
            "id": "P10", "trial": "T2", "outline": shifted_source, "origin": [40, 30]}})
        call('documents/D1/finish', {"expected": 11, "zone": "Z1", "data": {}})
        # patch=11 finish=12; second seal stores version 12
        call('documents/D1/releases', {"expected": 12})
        code, diff = call('documents/D1/compare/6/12')
        check(code == 200, f'E: compare works with polygon destinations: {diff}')
        # identical target outline, different source -> a single changed row
        kinds = sorted(item['kind'] for item in diff['changes'])
        check(kinds == ['changed'], f'E: same polygon placement with new source is changed: {kinds}')
        changed = diff['changes'][0]
        check(changed['before']['cut'] == L and changed['after']['cut'] == shifted_source,
              'E: comparison exposes both source outlines')

def scenario_f():
    """A legacy format-1 release (rectangle cut/destination only) still verifies and exports."""
    from paperbench import replay
    legacy_rect = [66, 55, 104, 71]
    cut_rect = [20, 0, 36, 38]
    sample_rect = [4, 5, 12, 13]
    rule = {"id": "R1", "thickness_gap": 18, "ph_gap": 5, "color_gap": 35,
            "hours": [0, 24], "drift": 20, "sample_edge": 5}
    sheet = {"id": "S1", "lot": "LOT", "width": 120, "height": 100,
             "stock": {"thickness": 90, "ph": 69, "grain": "y"},
             "faces": {"front": {"condition": "D50", "lab": {"l": 771, "a": 32, "b": 147}}}}
    zone_outline = [[66, 55], [104, 55], [104, 71], [66, 71]]
    trial = {"id": "T1", "zone": "Z1", "revision": 1,
             "selection": {"sheet": "S1", "face": "front", "turn": 90},
             "allocation": {"key": "k1", "cut": sample_rect}, "status": "accepted",
             "rows": [{"hour": 0, "drift": 3, "lifting": False, "note": "a"},
                      {"hour": 24, "drift": 4, "lifting": False, "note": "b"}]}
    patch = {"id": "P1", "zone": "Z1", "revision": 1, "trial": "T1",
             "selection": {"sheet": "S1", "face": "front", "turn": 90},
             "allocation": {"key": "k2", "cut": cut_rect}, "destination": legacy_rect}
    zone = {"id": "Z1", "revision": 1, "complete": True, "outline": zone_outline,
            "stock": {"thickness": 94, "ph": 70, "grain": "x"},
            "surface": {"condition": "D50", "lab": {"l": 770, "a": 30, "b": 150}},
            "trials": [trial], "patches": [patch]}
    inputs = {"document": {"rule": rule}, "zones": [zone], "sheets": {"S1": sheet}}
    manifest = replay.reconstruct(inputs)
    check(manifest[0]['destination'] == legacy_rect and manifest[0]['cut'] == cut_rect,
          'F: legacy rectangle manifest recomputes unchanged')
    from paperbench.codec import digest
    payload = {"format": 1, "inputs": inputs, "manifest": manifest}
    release = {**payload, "sha256": digest(payload)}
    check(archive.verify(release) == manifest, 'F: format-1 release verifies')
    from paperbench.export import cutting_csv
    csv_text = cutting_csv(manifest).decode()
    check('20 0 36 38' in csv_text and '66 55 104 71' in csv_text, 'F: legacy CSV stays four-int rectangles')


def main():
    scenario_a()
    print('SCENARIO A PASSED')
    scenario_b()
    print('SCENARIO B PASSED')
    scenario_c()
    print('SCENARIO C PASSED')
    scenario_d()
    print('SCENARIO D PASSED')
    scenario_e()
    print('SCENARIO E PASSED')
    scenario_f()
    print('SCENARIO F PASSED')


if __name__ == '__main__':
    main()
