from . import archive, events, patches, placement, records


def catalog(db):
    return {kind + 's': records.listing(db, kind) for kind in ('document', 'rule', 'lot', 'sheet')}


def board(db, doc):
    key = doc['id']
    zones = records.listing(db, 'zone', key)
    trials = records.listing(db, 'trial', key)

    def sample(trial):
        # Every physical sample stays readable by identity, including after a reopen
        # has moved live coverage to a new revision.
        return {'id': trial['id'], 'trial': trial['id'], 'zone': trial['zone'],
                'revision': trial['revision'], 'selection': trial['selection'],
                'allocation': trial['allocation'], 'cut': trial['allocation']['cut'],
                'status': trial['status'], 'used': bool(trial.get('used')),
                'mounts': trial.get('mounts', [])}

    samples = [sample(t) for t in trials]
    used = [row for row in samples if row['used']]
    for zone in zones:
        zone['patches'] = patches.current(db, doc, zone)
        zone['coverage'] = placement.coverage(zone, zone['patches'])
        zone['trials'] = [t for t in trials if t['zone'] == zone['id'] and t['revision'] == zone['revision']]
        zone['samples'] = [row for row in samples if row['zone'] == zone['id']]
        zone['used_samples'] = [row for row in used if row['zone'] == zone['id']]
    releases = [archive.summary(row) for row in records.listing(db, 'release', key)]
    return {'document': doc, 'version': events.version(db, key), 'zones': zones,
            'samples': samples, 'used_samples': used,
            'ready': bool(zones) and all(z['complete'] for z in zones),
            'releases': sorted(releases, key=lambda v: v['version'])}


def sheet_view(db, sheet):
    return {'sheet': sheet, 'lot': records.get(db, 'lot', sheet['lot']),
            'cuts': records.listing(db, 'cut', sheet['id'])}
