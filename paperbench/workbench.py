from . import archive, events, inventory, patches, placement, records


def catalog(db):
    splits = records.listing(db, 'split')
    return {'documents': records.listing(db, 'document'),
            'rules': records.listing(db, 'rule'),
            'lots': records.listing(db, 'lot'),
            'sheets': records.listing(db, 'sheet'),
            'splits': splits,
            'sheet_splits': splits}


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
    division = records.find(db, 'split', sheet['id'])
    own_cuts = records.listing(db, 'cut', sheet['id'])
    physical_cuts = inventory.lineage_cuts(db, sheet)
    inherited_cuts = [row for row in physical_cuts if row['sheet'] != sheet['id']]
    return {'sheet': sheet, 'lot': records.get(db, 'lot', sheet['lot']),
            'cuts': own_cuts, 'own_cuts': own_cuts,
            'direct_cuts': own_cuts,
            'physical_cuts': physical_cuts,
            'global_cuts': physical_cuts,
            'all_cuts': physical_cuts,
            'occupancy': physical_cuts,
            'inherited_cuts': inherited_cuts,
            'lineage_cuts': physical_cuts,
            'division': division,
            'split': division}
