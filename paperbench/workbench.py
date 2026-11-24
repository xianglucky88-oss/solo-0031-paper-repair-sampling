from . import archive, documents, events, patches, placement, records, trials


def catalog(db):
    return {kind + 's': records.listing(db, kind) for kind in ('document', 'rule', 'lot', 'sheet')}


def board(db, doc):
    key = doc['id']
    history = documents.history(doc)
    rule = documents.current_rule(doc)
    zones = records.listing(db, 'zone', key)
    trial_rows = records.listing(db, 'trial', key)
    for zone in zones:
        zone['patches'] = patches.current(db, doc, zone)
        zone['coverage'] = placement.coverage(zone, zone['patches'])
        zone['trials'] = []
        for trial in (t for t in trial_rows if (t['zone'], t['revision']) == (zone['id'], zone['revision'])):
            state = trials.evaluate(db, doc, zone, trial)
            zone['trials'].append({**trial,
                                   'judgment': {k: state[k] for k in
                                                ('reused', 'unmet', 'skipped', 'rejected', 'next',
                                                 'complete', 'continuable', 'eligible', 'authorizing',
                                                 'sample_edge_ok', 'face_fit_ok', 'active',
                                                 'permanently_failed', 'failed_rule')},
                                   'reused_observations': trials.reused_rows(trial, rule, history)})
    releases = [archive.summary(row) for row in records.listing(db, 'release', key)]
    return {'document': doc, 'version': events.version(db, key), 'zones': zones,
            'rules': history, 'rule': rule,
            'ready': bool(zones) and all(z['complete'] for z in zones),
            'releases': sorted(releases, key=lambda v: v['version'])}


def sheet_view(db, sheet):
    return {'sheet': sheet, 'lot': records.get(db, 'lot', sheet['lot']),
            'cuts': records.listing(db, 'cut', sheet['id'])}
