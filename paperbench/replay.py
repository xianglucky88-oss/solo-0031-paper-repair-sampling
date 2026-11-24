from collections import defaultdict

from . import compatibility, handovers, observations, placement
from .errors import Problem
from .rectangles import footprint, overlaps, size


def require(condition):
    if not condition:
        raise Problem('封存证据复算不一致', 409)


def _check_cut(sheet, cut, occupied):
    require(0 <= cut[0] < cut[2] <= sheet['width'] and 0 <= cut[1] < cut[3] <= sheet['height'])
    require(not any(overlaps(cut, other) for other in occupied[sheet['id']]))
    occupied[sheet['id']].append(cut)


def _material_ok(zone, sheet, selected, rule):
    return compatibility.evaluate(zone, sheet, selected['face'], selected['turn'], rule)['compatible']


def reconstruct_v1(inputs):
    """旧版封存：仅同条件 Lab 直接比较，无交接单证据。"""
    rule = inputs['document']['rule']
    occupied = defaultdict(list)
    manifest = []

    def account(selected, allocation, zone):
        sheet = inputs['sheets'][selected['sheet']]
        cut = allocation['cut']
        _check_cut(sheet, cut, occupied)
        require(_material_ok(zone, sheet, selected, rule))
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
            manifest.append(dict(zone=zone['id'], revision=zone['revision'], patch=patch['id'],
                                 trial=trial['id'], sheet=sheet['id'], lot=sheet['lot'], face=selected['face'],
                                 turn=selected['turn'], cut=cut, destination=dest, rule=rule['id']))
        require(placement.coverage(zone, placed)['remaining'] == 0)
    return manifest


def _verify_basis(trial, zone, sheets, handover_map, rule):
    """接手人仅凭签件独立复算开样时实际适用的交接单，并与签件采用依据逐项核对。"""
    selected = trial['selection']
    sheet = sheets[selected['sheet']]
    candidate = sheet['faces'][selected['face']]
    target = zone['surface']
    # 特性上线前开立的同条件试补没有 color_basis：按同条件直接比较兜底。
    if 'color_basis' not in trial:
        require(candidate['condition'] == target['condition'])
        require(compatibility.evaluate(zone, sheet, selected['face'], selected['turn'], rule)['compatible'])
        return
    recorded = trial['color_basis']
    require(isinstance(recorded, dict) and recorded['basis'] in ('same_condition', 'handover'))
    if candidate['condition'] == target['condition']:
        require(recorded['basis'] == 'same_condition' and recorded['verdict'] in handovers.VERDICTS)
        expected = compatibility.color_verdict(zone, candidate, rule, (), 0)
        require(recorded == expected and recorded['verdict'] == handovers.PASS)
        return
    require(recorded['basis'] == 'handover')
    # 漏列任何一份当时适用的交接单都必须拒绝：以签件内全部交接单重算适用集。
    applicable = handovers.applicable(list(handover_map.values()), candidate['condition'],
                                      target['condition'], candidate['lab'], trial['opened_at'])
    require(len(applicable) == len(recorded['bases']))
    expected_items = [handovers.evaluate_handover(item, candidate['lab'], target, rule['color_gap'])
                      for item in applicable]
    # 签件须完整保留各单的发布事实和量程，按编号版本排序后逐项核对。
    recorded_items = sorted(recorded['bases'], key=lambda item: (item['id'], item['version']))
    for expected, item in zip(expected_items, recorded_items):
        source = handover_map[(item['id'], item['version'])]
        require(item['ranges'] == source['ranges'] and item['deltas'] == source['deltas']
                and item['max_error'] == source['max_error']
                and item['effective_at'] == source['effective_at'])
        require(item == expected)
    require(recorded['verdict'] == handovers.aggregate(expected_items))
    require(recorded['verdict'] == handovers.PASS)


def reconstruct_v2(inputs):
    rule = inputs['document']['rule']
    handover_map = {(item['id'], item['version']): item for item in inputs['handovers']}
    # 同编号在签件中只保留各版本，互不覆盖；重复登记须幂等。
    require(len(handover_map) == len(inputs['handovers']))
    occupied = defaultdict(list)
    manifest = []

    def account(trial, allocation, zone):
        sheet = inputs['sheets'][trial['selection']['sheet']]
        cut = allocation['cut']
        _check_cut(sheet, cut, occupied)
        _verify_basis(trial, zone, inputs['sheets'], handover_map, rule)
        return sheet

    require(bool(inputs['zones']))
    for zone in inputs['zones']:
        require(zone['complete'])
        trials = {trial['id']: trial for trial in zone['trials']}
        for trial in trials.values():
            require(trial['zone'] == zone['id'] and trial['revision'] == zone['revision'])
            cut = trial['allocation']['cut']
            require(min(size(cut)) >= rule['sample_edge'])
            account(trial, trial['allocation'], zone)
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
            sheet = account(trial, patch['allocation'], zone)
            dest, cut = patch['destination'], patch['allocation']['cut']
            require(dest == footprint(dest[:2], cut, selected['turn']))
            placement.check(zone, dest, placed)
            placed.append(patch)
            manifest.append(dict(zone=zone['id'], revision=zone['revision'], patch=patch['id'],
                                 trial=trial['id'], sheet=sheet['id'], lot=sheet['lot'], face=selected['face'],
                                 turn=selected['turn'], cut=cut, destination=dest, rule=rule['id']))
        require(placement.coverage(zone, placed)['remaining'] == 0)
    return manifest


def reconstruct(inputs):
    return reconstruct_v2(inputs) if inputs.get('format', 1) == 2 else reconstruct_v1(inputs)
