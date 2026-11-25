from collections import defaultdict

from . import compatibility, lineage, observations, placement
from .errors import Problem
from .rectangles import footprint, overlaps, size


def require(condition):
    if not condition:
        raise Problem('封存证据复算不一致', 409)


def reconstruct(inputs):
    rule = inputs['document']['rule']
    occupied = defaultdict(list)
    manifest = []

    def account(selected, allocation, zone):
        sheet = inputs['sheets'][selected['sheet']]
        cut = allocation['cut']
        require(0 <= cut[0] < cut[2] <= sheet['width'] and 0 <= cut[1] < cut[3] <= sheet['height'])
        root_id, root_cut = lineage.root_frame(sheet)[0], lineage.map_to_root(sheet, cut)
        if allocation.get('root_cut') is not None:
            require(allocation.get('root_cut') == root_cut)
            require(allocation.get('root_sheet', root_id) == root_id)
        if allocation.get('original_cut') is not None:
            require(allocation.get('original_cut') == root_cut)
            require(allocation.get('original_sheet', root_id) == root_id)
        require(not any(overlaps(root_cut, other) for other in occupied[root_id]))
        occupied[root_id].append(root_cut)
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
            account(trial['selection'], trial['allocation'], zone)
            rows = []
            for row in trial['rows']:
                require(observations.disposition(rows, rule) == 'pending')
                rows.append(observations.accept(rows, row, rule))
            require(observations.disposition(rows, rule) == trial['status'])
        placed = []
        for patch in zone['patches']:
            trial = trials[patch['trial']]
            selected = patch['selection']
            require(trial['status'] == 'accepted' and selected == trial['selection'])
            require(patch['zone'] == zone['id'] and patch['revision'] == zone['revision'])
            sheet = account(selected, patch['allocation'], zone)
            dest, cut = patch['destination'], patch['allocation']['cut']
            require(dest == footprint(dest[:2], cut, selected['turn']))
            placement.check(zone, dest, placed)
            placed.append(patch)
            row = dict(zone=zone['id'], revision=zone['revision'], patch=patch['id'],
                        trial=trial['id'], sheet=sheet['id'], lot=sheet['lot'], face=selected['face'],
                        turn=selected['turn'], cut=cut, destination=dest, rule=rule['id'])
            if sheet.get('lineage'):
                original_cut = lineage.map_to_root(sheet, cut)
                root_id = lineage.root_frame(sheet)[0]
                row.update({
                    'lineage': sheet['lineage'],
                    'root_sheet': root_id,
                    'original_sheet': root_id,
                    'source_sheet': root_id,
                    'legacy_sheet': root_id,
                    'root_cut': original_cut,
                    'root_rect': original_cut,
                    'original_cut': original_cut,
                    'original_rect': original_cut,
                    'origin_cut': original_cut,
                    'original_position': original_cut,
                    'root_position': original_cut,
                    'rebased_cut': original_cut,
                    'physical_cut': original_cut,
                    'source_cut': original_cut,
                    'original': {'sheet': root_id, 'cut': original_cut},
                    'source': {'sheet': root_id, 'cut': original_cut},
                })
            manifest.append(row)
        require(placement.coverage(zone, placed)['remaining'] == 0)
    return manifest
