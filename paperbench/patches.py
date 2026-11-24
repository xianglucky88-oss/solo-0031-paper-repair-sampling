from . import inventory, placement, records, sheets
from .errors import Problem
from .rectangles import footprint, point_list, rectangle
from .validation import fields, identifier, text

# Field names a restorer may use to name the one patch being lifted.  The
# replacement is always recorded as ``replace``; ``reopen`` accepts the same
# payload so a restorer can rework a completed zone without reopening all of it.
LIFT_KEYS = ('patch', 'id', 'patch_id', 'withdrawn')


def epoch(zone):
    """First revision whose patches can still cover the artifact.

    A whole-zone reopen moves this forward, so every older piece drops out.
    Zones recorded before per-patch replacement existed carry no ``epoch``;
    for them any whole-zone reopen left no patch above the current revision,
    so the current revision is the correct floor.
    """
    if 'epoch' in zone:
        return zone['epoch']
    return zone['revision'] if zone['revision'] > 1 and not zone.get('replacements') else 1


def replacements(zone):
    return zone.get('replacements', [])


def rework(zone):
    """The replacement record opened for the current revision, if any."""
    return next((record for record in reversed(replacements(zone))
                 if record['revision'] == zone['revision']), None)


def withdrawn_ids(zone):
    return {record['withdrawn'] for record in replacements(zone)}


def listed(db, doc, zone_id):
    return [item for item in records.listing(db, 'patch', doc['id']) if item['zone'] == zone_id]


def epoch_patches(db, doc, zone):
    """Every piece from the current epoch, withdrawn ones included."""
    return [patch for patch in listed(db, doc, zone['id']) if patch['revision'] >= epoch(zone)]


def withdrawn_patches(db, doc, zone):
    """Pieces lifted from the artifact whose paper stays cut away."""
    dropped = withdrawn_ids(zone)
    return [patch for patch in epoch_patches(db, doc, zone) if patch['id'] in dropped]


def current(db, doc, zone):
    """Patches still stuck to the artifact.

    A replacement withdraws exactly one patch; all the others keep covering
    with their original id, revision, trial and cut.
    """
    dropped = withdrawn_ids(zone)
    return [patch for patch in epoch_patches(db, doc, zone) if patch['id'] not in dropped]


def parse(value):
    if not isinstance(value, dict):
        raise Problem('字段必须为：patch, reason')
    keys = set(value) & set(LIFT_KEYS)
    if len(keys) != 1 or set(value) != keys | {'reason'}:
        raise Problem('字段必须为：patch, reason')
    return identifier(value[next(iter(keys))]), text(value['reason'])


def replace(db, doc, zone, value):
    """Open a new revision that lifts exactly one patch from a completed zone.

    The other patches keep covering, with their ids, revisions, trials and
    actual cuts untouched.  The lifted piece's paper stays consumed.
    """
    key, reason = parse(value)
    if not zone['complete']:
        raise Problem('只可在已完工的区域记录上换片', 409)
    active = current(db, doc, zone)
    lifted = next((patch for patch in active if patch['id'] == key), None)
    if lifted is None:
        raise Problem('该补片不在本区当前完工覆盖中', 409)
    revision = zone['revision'] + 1
    record = {
        'revision': revision, 'mode': 'replace', 'from': zone['revision'], 'reason': reason,
        'withdrawn': key, 'withdrawn_patch': lifted,
        'retained': sorted(patch['id'] for patch in active if patch['id'] != key),
    }
    return records.put(db, 'zone', zone['id'], {
        **zone, 'revision': revision, 'complete': False, 'reason': reason,
        'epoch': epoch(zone), 'replacements': [*replacements(zone), record],
    }, doc['id'], replace=True)


def trial_allowed(trial, zone, record):
    """Whether a trial may back the piece put back into this revision."""
    if trial['status'] != 'accepted' or trial['zone'] != zone['id']:
        return False
    if trial['revision'] == zone['revision']:
        return True
    # An old accepted result may be carried over only on the very same physical
    # sheet, face and rotation.  Any other sheet, face or angle needs a trial
    # observed to its last time point inside this rework revision; an old
    # result may not be grafted onto a different candidate.
    return bool(record) and trial['selection'] == record['withdrawn_patch']['selection']


def add(db, doc, zone, value):
    fields(value, 'id', 'trial', 'cut', 'origin')
    key = identifier(value['id'])
    if records.find(db, 'patch', key, doc['id']):
        raise Problem('补片编号已使用', 409)
    trial = records.get(db, 'trial', identifier(value['trial']), doc['id'])
    record = rework(zone)
    if record and any(patch['revision'] == zone['revision'] for patch in listed(db, doc, zone['id'])):
        raise Problem('本修订的换片位已经补回', 409)
    if not trial_allowed(trial, zone, record):
        if record:
            raise Problem('换片须沿用被撤片的合格试补，或使用本次返工中已合格的试补', 409)
        raise Problem('补片须引用本区当前修订的合格试补', 409)
    selected = trial['selection']
    # A retired lot still explains pieces already stuck down, but it may not
    # be drawn from for this new piece.
    sheet = sheets.available(db, selected['sheet'])
    cut = rectangle(value['cut'])
    origin = point_list(value['origin'], 2)
    existing = current(db, doc, zone)
    dest = footprint(origin, cut, selected['turn'])
    if record:
        # The fresh piece must refit exactly the lifted piece's position and
        # extent and must not eat into any retained patch.
        if dest != record['withdrawn_patch']['destination']:
            raise Problem('换片须恰好补回被撤片的原位置和范围', 422)
        placement.check(zone, dest, existing)
    else:
        dest = placement.destination(origin, cut, selected['turn'], zone, existing)
    allocation = dict(key=f"{doc['id']}:patch:{key}", document=doc['id'], zone=zone['id'],
                      revision=zone['revision'], kind='patch', id=key, cut=cut)
    # The global sheet map still holds the lifted piece's cut, so a new cut
    # cannot borrow it, the other face, or another artifact's position.
    inventory.reserve(db, sheet, allocation)
    patch = dict(id=key, zone=zone['id'], revision=zone['revision'], trial=trial['id'],
                 selection=selected, allocation=allocation, destination=dest)
    return records.put(db, 'patch', key, patch, doc['id'])
