from .codec import encode


def key_of(row):
    # Identity is the physical position on the artifact, not the damage-zone label, so that a
    # split shows the zone reassignment as a change while the sheet and cut stay put.
    return encode(row['destination']).decode()


def compare(old, new):
    before = {key_of(row): row for row in old['manifest']}
    after = {key_of(row): row for row in new['manifest']}
    changes = []
    for key in sorted(before.keys() | after.keys()):
        a, b = before.get(key), after.get(key)
        if a != b:
            kind = 'added' if a is None else 'removed' if b is None else 'changed'
            changes.append({'kind': kind, 'before': a, 'after': b})
    return changes
