from . import compatibility, inventory, placement, records, sheets
from .errors import Problem
from .rectangles import point_list, rectangle
from .validation import identifier

# A whole-sample payload names the trial and where the sample is pasted.  A
# client may also echo the trial's own cut, face and turn; none changes which
# piece is consumed, which is always the trial's single original cut.
MOUNT_FIELDS = {'id', 'trial', 'origin', 'cut', 'whole', 'selection'}


def current(db, doc, zone):
    return [item for item in records.listing(db, 'patch', doc['id'])
            if (item['zone'], item['revision']) == (zone['id'], zone['revision'])]


def mounted(db, doc, trial):
    """Placed pieces that are this physical sample itself, across all revisions."""
    return [item for item in records.listing(db, 'patch', doc['id'])
            if item.get('whole') and item['trial'] == trial['id']]


def _mount(db, doc, zone, key, trial, origin, cut=None):
    """Paste the trial's own cut, whole, at ``origin``; take no new stock.

    The sample's paper face, turn and cut all come from the trial.  If the
    client echoes a cut it must be exactly the one knife taken when the trial
    was opened, because the sheet knows only that cut and no second reservation
    is made.  The one physical sample may appear on the artifact only once,
    even at another free spot.
    """
    if (trial['zone'], trial['revision'], trial['status']) != (zone['id'], zone['revision'], 'accepted'):
        raise Problem('整块贴用须引用本区当前修订、观察合格的试补', 409)
    if trial.get('used') or mounted(db, doc, trial):
        raise Problem('该实物试样已整块贴用，不能重复登记', 409)
    original = trial['allocation']['cut']
    if cut is not None and cut != original:
        raise Problem('整块贴用只认当初取样的一刀，不能另报取纸', 422)
    selected = trial['selection']
    # The lot must still allow new patch work.
    sheets.available(db, selected['sheet'])
    dest = placement.destination(origin, original, selected['turn'], zone, current(db, doc, zone))
    patch = dict(id=key, zone=zone['id'], revision=zone['revision'], trial=trial['id'],
                 selection=selected, allocation=trial['allocation'], destination=dest,
                 origin=origin, whole=True)
    records.put(db, 'patch', key, patch, doc['id'])
    # Mark the one original cut as pasted and record the use on the sample itself,
    # so both stay visible after a reopen moves live coverage to a new revision.
    records.put(db, 'cut', trial['allocation']['key'], {**trial['allocation'], 'whole_patch': key},
                selected['sheet'], replace=True)
    usage = {'patch': key, 'revision': zone['revision'], 'origin': origin, 'destination': dest}
    records.put(db, 'trial', trial['id'], {**trial, 'used': True,
                                           'mounts': [*trial.get('mounts', []), usage]},
                doc['id'], replace=True)
    return patch


def mount(db, doc, zone, value):
    """Register where the observed sample itself is pasted; its cut is inherited."""
    keys = set(value) if isinstance(value, dict) else set()
    if not {'id', 'trial', 'origin'} <= keys or keys - MOUNT_FIELDS:
        raise Problem('整块贴用字段必须为：id、trial、origin，可回填 cut、selection 或 whole')
    key = identifier(value['id'])
    if records.find(db, 'patch', key, doc['id']):
        raise Problem('补片编号已使用', 409)
    trial = records.get(db, 'trial', identifier(value['trial']), doc['id'])
    origin = point_list(value['origin'], 2)
    if 'selection' in keys and compatibility.selection(value['selection']) != trial['selection']:
        raise Problem('整块贴用的纸面和转向须与试补一致', 422)
    cut = rectangle(value['cut']) if 'cut' in keys else None
    return _mount(db, doc, zone, key, trial, origin, cut)


def _fresh(db, doc, zone, key, trial, cut, origin):
    """Reserve a new rectangular cut from an accepted trial and place it."""
    if (trial['zone'], trial['revision'], trial['status']) != (zone['id'], zone['revision'], 'accepted'):
        raise Problem('补片须引用本区当前修订的合格试补', 409)
    selected = trial['selection']
    sheet = sheets.available(db, selected['sheet'])
    dest = placement.destination(origin, cut, selected['turn'], zone, current(db, doc, zone))
    allocation = dict(key=f"{doc['id']}:patch:{key}", document=doc['id'], zone=zone['id'],
                      revision=zone['revision'], kind='patch', id=key, cut=cut)
    inventory.reserve(db, sheet, allocation)
    patch = dict(id=key, zone=zone['id'], revision=zone['revision'], trial=trial['id'],
                 selection=selected, allocation=allocation, destination=dest)
    return records.put(db, 'patch', key, patch, doc['id'])


def add(db, doc, zone, value):
    """Place a piece derived from an accepted trial.

    Without ``cut`` the observed sample itself is pasted whole.  With a ``cut``
    that names a new rectangle a fresh piece is cut as before; a ``cut`` equal
    to the trial's own or an explicit ``whole`` flag means the sample itself is
    pasted whole, because that stock position is already reserved by the trial.
    """
    if not isinstance(value, dict) or 'cut' not in value:
        return mount(db, doc, zone, value)
    keys = set(value)
    if not {'id', 'trial', 'cut', 'origin'} <= keys or keys - {'id', 'trial', 'cut', 'origin', 'whole', 'selection'}:
        raise Problem('字段必须为：id、trial、cut、origin')
    key = identifier(value['id'])
    if records.find(db, 'patch', key, doc['id']):
        raise Problem('补片编号已使用', 409)
    trial = records.get(db, 'trial', identifier(value['trial']), doc['id'])
    if 'selection' in keys and compatibility.selection(value['selection']) != trial['selection']:
        raise Problem('补片的纸面和转向须与试补一致', 422)
    cut = rectangle(value['cut'])
    origin = point_list(value['origin'], 2)
    if value.get('whole') or cut == trial['allocation']['cut']:
        return _mount(db, doc, zone, key, trial, origin, cut)
    return _fresh(db, doc, zone, key, trial, cut, origin)


# Readable aliases for the whole-sample action; all take the same payload.
whole = mount
place = mount
