from .codec import encode


def key_of(row):
    # Identity is the position and geometry on the artifact; outlines must be hashable too.
    return row['zone'], encode(row['destination']).decode()


def compare(old, new):
    # Pieces can be replaced across revisions; identity is the position and area on the artifact.
    before = {key_of(row): row for row in old['manifest']}
    after = {key_of(row): row for row in new['manifest']}
    changes = []
    for key in sorted(before.keys() | after.keys()):
        a, b = before.get(key), after.get(key)
        if a != b:
            kind = 'added' if a is None else 'removed' if b is None else 'changed'
            changes.append({'kind': kind, 'before': a, 'after': b})
    return changes
