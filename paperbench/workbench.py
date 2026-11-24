from . import archive, events, patches, placement, records


def catalog(db):
    return {kind + 's': records.listing(db, kind)
            for kind in ('document', 'rule', 'lot', 'sheet', 'handover')}


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
            'ready': bool(zones) and all(z['complete'] for z in zones),
            'releases': sorted(releases, key=lambda v: v['version'])}


def sheet_view(db, sheet):
    return {'sheet': sheet, 'lot': records.get(db, 'lot', sheet['lot']),
            'cuts': records.listing(db, 'cut', sheet['id'])}
