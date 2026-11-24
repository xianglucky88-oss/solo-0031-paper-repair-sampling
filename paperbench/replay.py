from collections import defaultdict

from . import compatibility, observations, placement
from .errors import Problem
from .rectangles import footprint, overlaps, size


def require(condition):
    if not condition:
        raise Problem('封存证据复算不一致', 409)


def _clock(rows, rule, status):
    """Recompute the trial's observation verdict from its frozen rows."""
    seen = []
    for row in rows:
        require(observations.disposition(seen, rule) == 'pending')
        seen.append(observations.accept(seen, row, rule))
    require(observations.disposition(seen, rule) == status)


def reconstruct(inputs):
    rule = inputs['document']['rule']
    occupied = defaultdict(list)
    pasted = set()
    manifest = []

    def account(selected, allocation, zone):
        sheet = inputs['sheets'][selected['sheet']]
        cut = allocation['cut']
        require(0 <= cut[0] < cut[2] <= sheet['width'] and 0 <= cut[1] < cut[3] <= sheet['height'])
        require(not any(overlaps(cut, other) for other in occupied[sheet['id']]))
        occupied[sheet['id']].append(cut)
        require(compatibility.evaluate(zone, sheet, selected['face'], selected['turn'], rule)['compatible'])
        return sheet

    require(bool(inputs['zones']))
    for zone in inputs['zones']:
        require(zone['complete'])
        trials = {trial['id']: trial for trial in zone['trials']}
        for trial in trials.values():
            require(trial['zone'] == zone['id'] and trial['revision'] == zone['revision'])
            cut = trial['allocation']['cut']
            require(min(size(cut)) >= rule['sample_edge'])
            _clock(trial['rows'], rule, trial['status'])
            account(trial['selection'], trial['allocation'], zone)
        placed = []
        for patch in zone['patches']:
            require(patch['trial'] in trials)
            trial = trials[patch['trial']]
            selected = patch['selection']
            require(trial['status'] == 'accepted' and selected == trial['selection'])
            require(patch['zone'] == zone['id'] and patch['revision'] == zone['revision'])
            if patch.get('whole'):
                # The piece on the artifact is the trial's own cut, pasted whole, so
                # the sheet's one reservation is already accounted for by the trial.
                # One physical sample may appear as only one placed piece.
                require(patch['trial'] not in pasted)
                pasted.add(patch['trial'])
                require(patch['allocation'] == trial['allocation'])
                origin = patch.get('origin')
                require(isinstance(origin, list) and len(origin) == 2)
                cut = trial['allocation']['cut']
                dest = footprint(origin, cut, selected['turn'])
                require(patch['destination'] == dest)
                if 'mounts' in trial:
                    require(trial.get('used') is True)
                    require([mount for mount in trial['mounts'] if mount['patch'] == patch['id']]
                            == [{'patch': patch['id'], 'revision': zone['revision'],
                                 'origin': origin, 'destination': dest}])
                sheet = inputs['sheets'][selected['sheet']]
                placement.check(zone, dest, placed)
                placed.append(patch)
                manifest.append(dict(zone=zone['id'], revision=zone['revision'], patch=patch['id'],
                                     trial=trial['id'], sheet=sheet['id'], lot=sheet['lot'],
                                     face=selected['face'], turn=selected['turn'], cut=cut,
                                     destination=dest, rule=rule['id'], whole=True, origin=origin))
                continue
            sheet = account(selected, patch['allocation'], zone)
            dest, cut = patch['destination'], patch['allocation']['cut']
            require(dest == footprint(dest[:2], cut, selected['turn']))
            placement.check(zone, dest, placed)
            placed.append(patch)
            manifest.append(dict(zone=zone['id'], revision=zone['revision'], patch=patch['id'],
                                 trial=trial['id'], sheet=sheet['id'], lot=sheet['lot'], face=selected['face'],
                                 turn=selected['turn'], cut=cut, destination=dest, rule=rule['id']))
        require(placement.coverage(zone, placed)['remaining'] == 0)
    return manifest
