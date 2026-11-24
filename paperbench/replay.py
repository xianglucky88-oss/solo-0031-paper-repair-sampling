from collections import defaultdict

from . import compatibility, observations, placement, prep
from .errors import Problem
from .rectangles import footprint, overlaps, size


def require(condition):
    if not condition:
        raise Problem('封存证据复算不一致', 409)


def reconstruct(inputs):
    rule = inputs['document']['rule']
    occupied = defaultdict(list)
    held_keys = set()
    quota_used = defaultdict(int)
    manifest = []

    def account(selected, allocation, zone):
        sheet = inputs['sheets'][selected['sheet']]
        cut = allocation['cut']
        require(0 <= cut[0] < cut[2] <= sheet['width'] and 0 <= cut[1] < cut[3] <= sheet['height'])
        require(not any(overlaps(cut, other) for other in occupied[sheet['id']]))
        occupied[sheet['id']].append(cut)
        held_keys.add(allocation['key'])
        quota_used[sheet['id']] += 1
        require(quota_used[sheet['id']] <= sheet.get('quota', 512))
        require(compatibility.evaluate(zone, sheet, selected['face'], selected['turn'], rule)['compatible'])
        return sheet

    zones_by_id = {zone['id']: zone for zone in inputs['zones']}
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

    # 备料组：核对状态机、笔数口径、占位与回执；交回/撤销的承诺不占纸、不计笔数
    prep_receipts = set()
    prepatches = []
    for group in inputs.get('prep_groups', []):
        require(group['document'] == inputs['document']['id'])
        statuses = [slot['status'] for slot in group['slots']]
        require(all(status in (*prep.ACTIVE, *prep.SETTLED) for status in statuses))
        for slot in group['slots']:
            require(slot['group'] == group['id'])
            zone = zones_by_id.get(slot['zone'])
            require(zone is not None and slot['revision'] <= zone['revision'])
            trials_here = {t['id']: t for t in zone['trials']}
            trial = trials_here.get(slot['trial'])
            require(trial is not None and trial['status'] == 'accepted'
                    and trial['selection'] == slot['selection'])
            if slot['status'] in (*prep.ACTIVE, 'cut'):
                # 承诺/开裁/已裁都占位且各占一笔；同一备料位转已裁时键不变，故只占一笔
                account(slot['selection'], slot['allocation'], zone)
                require(slot['cut'] == slot['allocation']['cut'])
                require(slot['destination'] == footprint(slot['origin'], slot['cut'],
                                                          slot['selection']['turn']))
            else:
                # 已撤销、未动刀交回或因复开被取代：源纸占位必须已释放
                require(slot['status'] in ('cancelled', 'returned', 'superseded'))
                require(slot['allocation']['key'] not in held_keys)
            if slot['status'] in prep.SETTLED:
                if slot['status'] in ('cut', 'returned', 'cancelled'):
                    require(slot.get('receipt') or slot['status'] == 'cancelled')
                if slot.get('receipt'):
                    require(slot['receipt'] not in prep_receipts)
                    prep_receipts.add(slot['receipt'])
                if slot['status'] == 'cut':
                    require(slot['allocation'].get('receipt') == slot['receipt'])
            if slot.get('patch'):
                require(slot['status'] == 'cut')
                prepatches.append((group, slot))

    all_patches = [patch for zone in inputs['zones'] for patch in zone['patches']]
    prepatch_by_id = {slot.get('patch'): (group, slot) for group, slot in prepatches}
    placed = []
    for zone in inputs['zones']:
        trials = {trial['id']: trial for trial in zone['trials']}
        for patch in zone['patches']:
            selected = patch['selection']
            require(patch['zone'] == zone['id'] and patch['revision'] == zone['revision'])
            dest, cut = patch['destination'], patch['allocation']['cut']
            require(dest == footprint(dest[:2], cut, selected['turn']))
            placement.check(zone, dest, placed)
            placed.append(patch)
            if patch.get('kind') == 'prepatch':
                # 备料贴补：必须关联一笔已裁回执，且一笔已裁回执只登记一片补片
                require(patch.get('receipt') and patch['receipt'] in prep_receipts)
                require(sum(1 for p in all_patches if p.get('receipt') == patch['receipt']) == 1)
                group, slot = prepatch_by_id.get(patch['id'], (None, None))
                require(slot is not None and slot['receipt'] == patch['receipt'])
                require(slot['allocation']['key'] == patch['allocation']['key'])
                require(patch['trial'] == slot['trial'])
                sheet = inputs['sheets'][selected['sheet']]
            else:
                trial = trials[patch['trial']]
                require(trial['status'] == 'accepted' and selected == trial['selection'])
                sheet = account(selected, patch['allocation'], zone)
            manifest.append(dict(zone=zone['id'], revision=zone['revision'], patch=patch['id'],
                                 trial=patch['trial'], sheet=sheet['id'], lot=sheet['lot'],
                                 face=selected['face'], turn=selected['turn'], cut=cut,
                                 destination=dest, rule=rule['id'],
                                 kind=patch.get('kind', 'patch'),
                                 receipt=patch.get('receipt', '')))
        require(placement.coverage(zone, placed)['remaining'] == 0)
    return manifest
