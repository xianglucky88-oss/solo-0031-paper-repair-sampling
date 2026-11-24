def compare(old, new):
    # Rectangles can be replaced across revisions; identity is the position and area on the artifact.
    def index(release):
        return {(row['zone'], *row['destination']): row for row in release['manifest']}

    before, after = index(old), index(new)
    changes = []
    for key in sorted(before.keys() | after.keys()):
        a, b = before.get(key), after.get(key)
        if a != b:
            kind = 'added' if a is None else 'removed' if b is None else 'changed'
            changes.append({'kind': kind, 'before': a, 'after': b})
    return changes
