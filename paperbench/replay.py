from collections import defaultdict

from . import compatibility, observations, placement
from .errors import Problem
from .outlines import as_outline, bbox, placed_outline, shapes_overlap
from .rectangles import footprint, size


def require(condition):
    if not condition:
        raise Problem('封存证据复算不一致', 409)


def allocation_shape(allocation):
    """New records store shape (rect or outline); legacy records store cut rectangle."""
    return as_outline(allocation['shape'] if 'shape' in allocation else allocation['cut'])


def rect_from(shape):
    x0, y0, x1, y1 = bbox(shape)
    return [x0, y0, x1, y1]


def reconstruct(inputs):
    rule = inputs['document']['rule']
    occupied = defaultdict(list)
    manifest = []

    def account(selected, allocation, zone):
        sheet = inputs['sheets'][selected['sheet']]
        shape = allocation_shape(allocation)
        x0, y0, right, bottom = bbox(shape)
        require(0 <= x0 and 0 <= y0 and right <= sheet['width'] and bottom <= sheet['height'])
        require(not any(shapes_overlap(shape, other) for other in occupied[sheet['id']]))
        occupied[sheet['id']].append(shape)
        require(compatibility.evaluate(zone, sheet, selected['face'], selected['turn'], rule)['compatible'])
        return sheet

    require(bool(inputs['zones']))
    for zone in inputs['zones']:
        require(zone['complete'])
        trials = {trial['id']: trial for trial in zone['trials']}
        for trial in trials.values():
            require(trial['zone'] == zone['id'] and trial['revision'] == zone['revision'])
            shape = allocation_shape(trial['allocation'])
            require(len(shape) == 4 and min(size(rect_from(shape))) >= rule['sample_edge'])
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
            shape = allocation_shape(patch['allocation'])
            origin = patch.get('origin', patch['destination'][:2])
            if len(shape) == 4:
                expect_dest = footprint(origin, rect_from(shape), selected['turn'])
            else:
                expect_dest = placed_outline(shape, origin, selected['turn'])
            require(patch['destination'] == expect_dest)
            placement.check(zone, patch['destination'], placed)
            placed.append(patch)
            manifest_cut = rect_from(shape) if len(shape) == 4 else shape
            manifest.append(dict(zone=zone['id'], revision=zone['revision'], patch=patch['id'],
                                 trial=trial['id'], sheet=sheet['id'], lot=sheet['lot'], face=selected['face'],
                                 turn=selected['turn'], cut=manifest_cut, destination=patch['destination'],
                                 rule=rule['id']))
        require(placement.coverage(zone, placed)['remaining'] == 0)
    return manifest
