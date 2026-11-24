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
    trials = {trial['id']: trial for trial in records.listing(db, 'trial', doc['id'])}
    sheets = {}
    for zone in zones:
        covering = patches.current(db, doc, zone)
        lifted = patches.withdrawn_patches(db, doc, zone)
        zone['patches'] = covering
        # Lifted pieces no longer cover, but their paper stays cut and their
        # evidence stays in the snapshot so the release can still account for
        # every sample ever drawn from the sheets it names.
        zone['withdrawn'] = lifted
        # Every sample drawn in this epoch stays accounted, whether or not a
        # covering piece still points at it: withdrawn pieces keep their spent
        # paper and the intact pieces keep the trial they were cut from.
        zone['trials'] = [trial for trial in trials.values()
                          if trial['zone'] == zone['id']
                          and trial['revision'] >= patches.epoch(zone)]
        for trial in zone['trials']:
            key = trial['selection']['sheet']
            if key not in sheets:
                sheets[key] = records.get(db, 'sheet', key)
    inputs = {'document': doc, 'version': expected, 'zones': zones, 'sheets': sheets}
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
