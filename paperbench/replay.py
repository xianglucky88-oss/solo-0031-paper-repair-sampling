from collections import defaultdict

from . import compatibility, observations, placement
from .errors import Problem
from .outlines import area, contains, outline
from .rectangles import footprint, overlaps, size


def require(condition):
    if not condition:
        raise Problem('封存证据复算不一致', 409)


def trial_zones(trial):
    return list(trial.get('zones') or [trial['zone']])


def _partition(old, first, second):
    """复算拆区：两个新区必须正好分完旧区，不越界、不重叠、不留缝。"""
    xs = sorted({x for points in (old, first, second) for x, _ in points})
    ys = sorted({y for points in (old, first, second) for _, y in points})
    for left, right in zip(xs, xs[1:]):
        for top, bottom in zip(ys, ys[1:]):
            rect = [left, top, right, bottom]
            inside = [contains(points, rect) for points in (old, first, second)]
            require(not (inside[1] and inside[2]))
            require(not ((inside[1] or inside[2]) and not inside[0]))
            require(not (inside[0] and not (inside[1] or inside[2])))
    require(area(first) + area(second) == area(old))


def split_records(inputs):
    """复算拆区回执：旧轮廓由两个新区正好分完，并按新区编号建立索引。"""
    index = {}
    for record in inputs.get('splits', []):
        source = record['source']
        require(len(record['zones']) == 2)
        first = outline(record['zones'][0]['outline'], 3000, 3000)
        second = outline(record['zones'][1]['outline'], 3000, 3000)
        _partition(source['outline'], first, second)
        for position, part in enumerate(record['zones']):
            require(part['id'] not in index)
            index[part['id']] = record
    return index


def reconstruct(inputs):
    rule = inputs['document']['rule']
    occupied = defaultdict(list)
    manifest = []
    splits = split_records(inputs)
    zones = [zone for zone in inputs['zones'] if zone.get('active', True)]
    require(bool(zones))
    trials = {trial['id']: trial for zone in zones for trial in zone['trials']}

    def account(selected, allocation, zone, *, account_cut=True):
        sheet = inputs['sheets'][selected['sheet']]
        cut = allocation['cut']
        require(0 <= cut[0] < cut[2] <= sheet['width'] and 0 <= cut[1] < cut[3] <= sheet['height'])
        if account_cut:
            require(not any(overlaps(cut, other) for other in occupied[sheet['id']]))
            occupied[sheet['id']].append(cut)
        require(compatibility.evaluate(zone, sheet, selected['face'], selected['turn'], rule)['compatible'])
        return sheet

    def check_origin(zone):
        origin = zone.get('origin')
        if origin is None:
            return
        record = splits.get(zone['id'])
        require(record is not None)
        require(record['source']['id'] == origin['zone'])
        require(record['source']['revision'] == origin['revision'])
        require(record['source']['outline'] == origin['outline'])
        part = next((item for item in record['zones'] if item['id'] == zone['id']), None)
        require(part is not None and part['outline'] == zone['outline'])

    def check_split_trial(record, trial):
        """拆区回执里的一笔试样取纸须与在册试补一致，且该试补确实服务拆出的区。"""
        if record is None:
            return
        listed = next((item for item in record.get('trials', []) if item['id'] == trial['id']), None)
        if listed is None:
            return
        require(listed['cut'] == trial['allocation']['cut'])
        require({part['id'] for part in record['zones']} <= set(listed['zones']))

    accounted = set()
    claimed = {}
    for zone in zones:
        require(zone['complete'])
        check_origin(zone)
        record = splits.get(zone['id'])
        if record is not None:
            for entry in record.get('patches', []):
                if entry['zone'] == zone['id']:
                    claimed[entry['id']] = zone['id']
        own = {trial['id']: trial for trial in zone['trials']}
        for trial in own.values():
            require(trial['revision'] == zone['revision'] and zone['id'] in trial_zones(trial))
            check_split_trial(record, trial)
            cut = trial['allocation']['cut']
            require(min(size(cut)) >= rule['sample_edge'])
            account(trial['selection'], trial['allocation'], zone, account_cut=trial['id'] not in accounted)
            accounted.add(trial['id'])
            rows = []
            for row in trial['rows']:
                require(observations.disposition(rows, rule) == 'pending')
                rows.append(observations.accept(rows, row, rule))
            require(observations.disposition(rows, rule) == trial['status'])
        placed = []
        for patch in zone['patches']:
            trial = trials.get(patch['trial'])
            require(trial is not None)
            selected = patch['selection']
            require(trial['status'] == 'accepted' and selected == trial['selection'])
            require(patch['zone'] == zone['id'] and patch['revision'] == zone['revision'])
            require(zone['id'] in trial_zones(trial))
            sheet = account(selected, patch['allocation'], zone)
            dest, cut = patch['destination'], patch['allocation']['cut']
            require(dest == footprint(dest[:2], cut, selected['turn']))
            placement.check(zone, dest, placed)
            placed.append(patch)
            row = dict(zone=zone['id'], revision=zone['revision'], patch=patch['id'],
                       trial=trial['id'], sheet=sheet['id'], lot=sheet['lot'], face=selected['face'],
                       turn=selected['turn'], cut=cut, destination=dest, rule=rule['id'])
            manifest.append(row)
        require(placement.coverage(zone, placed)['remaining'] == 0)
    # Every patch reassigned by a split must appear under exactly the zone the split assigned.
    seen = {(row['patch'], row['zone']) for row in manifest}
    for patch, zone in claimed.items():
        require((patch, zone) in seen)
    return manifest
