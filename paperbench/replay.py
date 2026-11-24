from collections import defaultdict

from . import compatibility, observations, placement
from .errors import Problem
from .rectangles import footprint, overlaps, size


def require(condition):
    if not condition:
        raise Problem('封存证据复算不一致', 409)


def reconstruct(inputs):
    rule = inputs['document']['rule']
    occupied = defaultdict(list)
    drawn = set()
    manifest = []

    def account(zone, selected, allocation):
        sheet = inputs['sheets'][selected['sheet']]
        cut = allocation['cut']
        require(0 <= cut[0] < cut[2] <= sheet['width'] and 0 <= cut[1] < cut[3] <= sheet['height'])
        require(not any(overlaps(cut, other) for other in occupied[sheet['id']]))
        occupied[sheet['id']].append(cut)
        require(compatibility.evaluate(zone, sheet, selected['face'], selected['turn'], rule)['compatible'])
        # Each physical sample is charged once.  A sample carried over from an
        # earlier revision is not drawn a second time in the new revision, and
        # reusing an old trial does not make its stock fresh again.
        key = (sheet['id'], *cut)
        require(key not in drawn)
        drawn.add(key)
        return sheet

    def judged(zone, trial):
        require(trial['zone'] == zone['id'] and 1 <= trial['revision'] <= zone['revision'])
        require(min(size(trial['allocation']['cut'])) >= rule['sample_edge'])
        rows = []
        for row in trial['rows']:
            require(observations.disposition(rows, rule) == 'pending')
            rows.append(observations.accept(rows, row, rule))
        require(observations.disposition(rows, rule) == trial['status'])

    require(bool(inputs['zones']))
    for zone in inputs['zones']:
        require(zone['complete'])
        revision = zone['revision']
        epoch = zone.get('epoch', 1)
        records = zone.get('replacements', [])
        replacements = {record['revision']: record for record in records}
        require(len(replacements) == len(records))
        require(all(epoch < at for at in replacements))
        lifted = {patch['id']: patch for patch in zone.get('withdrawn', [])}
        require(len(lifted) == len(zone.get('withdrawn', [])))
        covering = {patch['id']: patch for patch in zone['patches']}
        require(len(covering) == len(zone['patches']))
        trials = {trial['id']: trial for trial in zone['trials']}
        require(len(trials) == len(zone['trials']))
        for trial in trials.values():
            judged(zone, trial)
        # Each lifted piece is charged to exactly one replacement, and the
        # replacement's retained set must be the pieces still covering at that
        # point -- nothing may quietly vanish or reappear.
        charged = set()
        for at in sorted(replacements):
            record = replacements[at]
            require(record['withdrawn'] in lifted)
            require(record['withdrawn'] not in covering and record['withdrawn'] not in charged)
            require(record['withdrawn'] not in record['retained'])
            charged.add(record['withdrawn'])
            earlier = {item['withdrawn'] for when, item in replacements.items() if when < at}
            expected = sorted(key for key, patch in covering.items()
                              if epoch <= patch['revision'] < at and key not in earlier)
            require(record['retained'] == expected)
        require(charged == set(lifted))
        retained = {key for item in records for key in item['retained']}
        placed = []
        for key in sorted(covering):
            patch = covering[key]
            require(patch['zone'] == zone['id'] and epoch <= patch['revision'] <= revision)
            record = replacements.get(patch['revision'])
            if record is None:
                # A piece added in the revision being sealed, or one a
                # replacement declared retained, keeps its own revision; any
                # other old revision would have been dropped or withdrawn.
                require(patch['revision'] == revision or key in retained)
            else:
                # A replacement refits exactly the lifted piece's footprint and
                # may keep its accepted trial only on the same sheet, face, turn.
                require(record['withdrawn'] not in covering)
                require(patch['destination'] == record['withdrawn_patch']['destination'])
            trial = trials.get(patch['trial'])
            require(trial is not None and trial['status'] == 'accepted')
            require(patch['selection'] == trial['selection'])
            if record and trial['revision'] != patch['revision']:
                # A carried-over basis must match the withdrawn piece's
                # physical sheet, face and rotation exactly.
                require(patch['selection'] == record['withdrawn_patch']['selection'])
            else:
                require(trial['revision'] == patch['revision'])
            sheet = account(zone, patch['selection'], patch['allocation'])
            dest, cut = patch['destination'], patch['allocation']['cut']
            require(dest == footprint(dest[:2], cut, patch['selection']['turn']))
            placement.check(zone, dest, placed)
            placed.append(patch)
            manifest.append(dict(zone=zone['id'], revision=patch['revision'], patch=patch['id'],
                                 trial=trial['id'], sheet=sheet['id'], lot=sheet['lot'],
                                 face=patch['selection']['face'], turn=patch['selection']['turn'],
                                 cut=cut, destination=dest, rule=rule['id']))
        # A lifted piece's paper is spent and its cut stays occupied, even
        # though it no longer covers the artifact.
        for patch in lifted.values():
            require(patch['zone'] == zone['id'])
            account(zone, patch['selection'], patch['allocation'])
        for trial in trials.values():
            account(zone, trial['selection'], trial['allocation'])
        require(placement.coverage(zone, placed)['remaining'] == 0)
    return manifest
