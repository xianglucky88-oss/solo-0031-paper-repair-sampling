from . import archive, events, patches, placement, records


def catalog(db):
    return {kind + 's': records.listing(db, kind) for kind in ('document', 'rule', 'lot', 'sheet')}


def zone_view(db, doc, zone, trials):
    covering = patches.current(db, doc, zone)
    lifted = patches.withdrawn_patches(db, doc, zone)
    zone['patches'] = covering
    zone['withdrawn'] = lifted
    zone['coverage'] = placement.coverage(zone, covering)
    rework = patches.rework(zone)
    zone['rework'] = rework
    holders = {}
    for patch in [*covering, *lifted]:
        holders.setdefault(patch['trial'], []).append(patch['id'])
    shown = []
    for trial in trials:
        if trial['zone'] != zone['id']:
            continue
        if trial['revision'] != zone['revision'] and trial['id'] not in holders:
            continue
        # A basis carried over from the withdrawn piece may back the refit only
        # on the same sheet, face and rotation; anything else needs a fresh one.
        trial['usable'] = patches.trial_allowed(trial, zone, rework)
        trial['backs'] = holders.get(trial['id'], [])
        shown.append(trial)
    zone['trials'] = shown
    return zone


def board(db, doc):
    key = doc['id']
    zones = records.listing(db, 'zone', key)
    trials = records.listing(db, 'trial', key)
    for zone in zones:
        zone_view(db, doc, zone, trials)
    releases = [archive.summary(row) for row in records.listing(db, 'release', key)]
    return {'document': doc, 'version': events.version(db, key), 'zones': zones,
            'ready': bool(zones) and all(z['complete'] for z in zones),
            'releases': sorted(releases, key=lambda v: v['version'])}


def sheet_view(db, sheet):
    return {'sheet': sheet, 'lot': records.get(db, 'lot', sheet['lot']),
            'cuts': records.listing(db, 'cut', sheet['id'])}
