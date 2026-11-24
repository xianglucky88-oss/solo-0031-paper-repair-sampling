from . import archive, events, patches, placement, records, trials


def catalog(db):
    return {kind + 's': records.listing(db, kind) for kind in ('document', 'rule', 'lot', 'sheet')}


def active(zone):
    return zone.get('active', True)


def board(db, doc):
    key = doc['id']
    zones = records.listing(db, 'zone', key)
    trial_rows = records.listing(db, 'trial', key)
    for zone in zones:
        zone['patches'] = patches.current(db, doc, zone)
        zone['coverage'] = placement.coverage(zone, zone['patches'])
        zone['trials'] = [t for t in trial_rows if trials.member(t, zone)]
    live = [zone for zone in zones if active(zone)]
    releases = [archive.summary(row) for row in records.listing(db, 'release', key)]
    return {'document': doc, 'version': events.version(db, key), 'zones': zones,
            'ready': bool(live) and all(z['complete'] for z in live),
            'releases': sorted(releases, key=lambda v: v['version'])}


def sheet_view(db, sheet):
    return {'sheet': sheet, 'lot': records.get(db, 'lot', sheet['lot']),
            'cuts': records.listing(db, 'cut', sheet['id'])}
