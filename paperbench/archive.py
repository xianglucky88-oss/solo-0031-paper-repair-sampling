from . import events, patches, records, replay
from .codec import digest
from .errors import Problem
from .validation import fields, integer


def seal(db, doc, body):
    fields(body, 'expected')
    expected = body['expected']
    events.guard(db, doc['id'], expected)
    zones = records.listing(db, 'zone', doc['id'])
    if not zones or not all(z['complete'] for z in zones):
        raise Problem('全部损坏区完工后才可封存', 409)
    existing = records.find(db, 'release', str(expected), doc['id'])
    if existing:
        return summary(existing)
    trials = records.listing(db, 'trial', doc['id'])
    sheets = {}
    for zone in zones:
        zone['patches'] = patches.current(db, doc, zone)
        zone['trials'] = [t for t in trials if (t['zone'], t['revision']) == (zone['id'], zone['revision'])]
        for trial in zone['trials']:
            key = trial['selection']['sheet']
            if key not in sheets:
                sheets[key] = records.get(db, 'sheet', key)
    # Include the immutable ancestor registrations so an offline verifier can
    # resolve narrow-page coordinates back to the original sheet number.
    for key in list(sheets):
        current = sheets[key]
        parent_id = current.get('lineage', {}).get('parent') or current.get('parent')
        while parent_id and parent_id not in sheets:
            parent = records.get(db, 'sheet', parent_id)
            sheets[parent_id] = parent
            parent_id = parent.get('lineage', {}).get('parent') or parent.get('parent')
    inputs = {'document': doc, 'version': expected, 'zones': zones, 'sheets': sheets}
    lineages = {key: sheet['lineage'] for key, sheet in sheets.items() if sheet.get('lineage')}
    if lineages:
        inputs['lineages'] = lineages
        split_records = []
        seen = set()
        for sheet in sheets.values():
            parent_id = sheet.get('lineage', {}).get('parent')
            while parent_id and parent_id not in seen:
                seen.add(parent_id)
                split_record = records.find(db, 'split', parent_id)
                if split_record:
                    split_records.append(split_record)
                parent = records.find(db, 'sheet', parent_id)
                parent_id = parent.get('lineage', {}).get('parent') if parent else None
        if split_records:
            inputs['splits'] = split_records
            inputs['split_map'] = {row['id']: row for row in split_records}
    payload = {'format': 1, 'inputs': inputs, 'manifest': replay.reconstruct(inputs)}
    release = {**payload, 'sha256': digest(payload)}
    records.put(db, 'release', str(expected), release, doc['id'])
    return summary(release)


def verify(release):
    payload = {key: value for key, value in release.items() if key != 'sha256'}
    if release['format'] != 1 or digest(payload) != release['sha256']:
        raise Problem('封存格式或摘要不符', 409)
    rows = replay.reconstruct(release['inputs'])
    if rows != release['manifest']:
        raise Problem('封存清单与复算不符', 409)
    return rows


def load(db, doc, version):
    version = integer(version, 1, 2**53 - 1, '封存版本')
    release = records.get(db, 'release', str(version), doc['id'])
    verify(release)
    return release


def summary(release):
    return {'version': release['inputs']['version'], 'sha256': release['sha256'],
            'patch_count': len(release['manifest'])}
