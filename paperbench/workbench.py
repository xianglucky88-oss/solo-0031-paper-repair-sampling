from . import archive, events, patches, placement, prep, records


def catalog(db):
    return {kind + 's': records.listing(db, kind) for kind in ('document', 'rule', 'lot', 'sheet')}


def board(db, doc):
    key = doc['id']
    zones = records.listing(db, 'zone', key)
    trials = records.listing(db, 'trial', key)
    for zone in zones:
        zone['patches'] = patches.current(db, doc, zone)
        zone['coverage'] = placement.coverage(zone, zone['patches'])
        zone['trials'] = [t for t in trials if t['zone'] == zone['id'] and t['revision'] == zone['revision']]
    releases = [archive.summary(row) for row in records.listing(db, 'release', key)]
    return {'document': doc, 'version': events.version(db, key), 'zones': zones,
            'prep_groups': prep.groups(db, key),
            'ready': bool(zones) and all(z['complete'] for z in zones),
            'releases': sorted(releases, key=lambda v: v['version'])}


def sheet_view(db, sheet):
    usage = prep.quota_usage(db, sheet['id'])
    return {'sheet': sheet, 'lot': records.get(db, 'lot', sheet['lot']),
            'quota_used': usage, 'quota_remaining': sheet.get('quota', 512) - usage,
            'cuts': records.listing(db, 'cut', sheet['id'])}
