from collections import defaultdict

from . import compatibility, documents, observations, placement
from .errors import Problem
from .rectangles import footprint, overlaps, size


def require(condition):
    if not condition:
        raise Problem('封存证据复算不一致', 409)


def legacy(inputs):
    """Recompute a release sealed before rules could be switched mid-work.

    Those inputs carry one rule and trials without a starting rule, so the
    original replay applies unchanged and the sealed bytes stay reproducible.
    """
    rule = inputs['document']['rule']
    occupied = defaultdict(list)
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
            account(trial['selection'], trial['allocation'], zone)
            rows = []
            for row in trial['rows']:
                payload = {key: row[key] for key in ('hour', 'drift', 'lifting', 'note')}
                require(observations.status(rows, rule) == 'pending')
                rows.append(observations.accept(rows, payload, rule))
            require(observations.status(rows, rule) == trial['status'])
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


def reconstruct(inputs):
    if 'rule_history' not in inputs['document']:
        return legacy(inputs)
    doc = inputs['document']
    history = documents.history(doc)
    order = [entry['rule']['id'] for entry in history]
    occupied = defaultdict(list)
    manifest = []

    def rank(rule_id):
        require(rule_id in order)
        return order.index(rule_id)

    def rule_of(rule_id):
        return history[rank(rule_id)]['rule']

    def account(selected, allocation, zone, rule):
        sheet = inputs['sheets'][selected['sheet']]
        cut = allocation['cut']
        require(0 <= cut[0] < cut[2] <= sheet['width'] and 0 <= cut[1] < cut[3] <= sheet['height'])
        require(not any(overlaps(cut, other) for other in occupied[sheet['id']]))
        occupied[sheet['id']].append(cut)
        require(compatibility.evaluate(zone, sheet, selected['face'], selected['turn'], rule)['compatible'])
        return sheet

    def audit(trial):
        started = trial.get('rule') or order[0]
        rows, failed_rule = [], None
        for row in trial['rows']:
            applied = row.get('rule') or started
            require(rank(applied) >= rank(started))
            rule = rule_of(applied)
            payload = {key: row[key] for key in ('hour', 'drift', 'lifting', 'note')}
            expected = observations.assess(rows, rule)['next']
            rows.append(observations.accept(rows, payload, rule, expected=expected))
            if failed_rule is None and observations.status(rows, rule) == 'failed':
                failed_rule = applied
        last_rule = trial['rows'][-1].get('rule', started) if trial['rows'] else started
        require(rank(last_rule) >= rank(started))
        require(observations.status(rows, rule_of(last_rule)) == trial['status'])
        if trial.get('failed_rule') is not None:
            require(trial['failed_rule'] == failed_rule)
        if trial.get('failed'):
            require(failed_rule is not None)
        if failed_rule is not None:
            require(trial.get('status') == 'failed')
        require(min(size(trial['allocation']['cut'])) >= rule_of(started)['sample_edge'])
        return {'rows': rows, 'failed_rule': failed_rule, 'failed': bool(failed_rule), 'started': started}

    require(bool(inputs['zones']))
    for zone in inputs['zones']:
        require(zone['complete'])
        audits = {trial['id']: audit(trial) for trial in zone['trials']}
        starts = {trial['id']: rule_of(audits[trial['id']]['started']) for trial in zone['trials']}
        for trial in zone['trials']:
            require(trial['zone'] == zone['id'] and trial['revision'] == zone['revision'])
            account(trial['selection'], trial['allocation'], zone, starts[trial['id']])
        placed = []
        for patch in zone['patches']:
            trial = next(t for t in zone['trials'] if t['id'] == patch['trial'])
            record = audits[trial['id']]
            used = patch.get('rule') or record['started']
            require(rank(used) >= rank(record['started']))
            rule = rule_of(used)
            if record['failed_rule']:
                require(rank(used) < rank(record['failed_rule']))
            require(observations.judgment({**trial, **record}, rule, history)['eligible'])
            require(min(size(trial['allocation']['cut'])) >= rule['sample_edge'])
            require(patch.get('reused_observations', []) ==
                    [row for row in trial['rows'] if row['hour'] in rule['hours']
                     and row.get('rule', record['started']) != used])
            selected = patch['selection']
            require(selected == trial['selection'])
            require(patch['zone'] == zone['id'] and patch['revision'] == zone['revision'])
            sheet = account(selected, patch['allocation'], zone, rule)
            dest, cut = patch['destination'], patch['allocation']['cut']
            require(dest == footprint(dest[:2], cut, selected['turn']))
            placement.check(zone, dest, placed)
            placed.append(patch)
            manifest.append(dict(zone=zone['id'], revision=zone['revision'], patch=patch['id'],
                                 trial=trial['id'], sheet=sheet['id'], lot=sheet['lot'], face=selected['face'],
                                 turn=selected['turn'], cut=cut, destination=dest, rule=used,
                                 reused=[{key: row[key] for key in ('hour', 'drift', 'lifting', 'note', 'rule')
                                          if key in row}
                                         for row in patch['reused_observations']]))
        require(placement.coverage(zone, placed)['remaining'] == 0)
    return manifest
