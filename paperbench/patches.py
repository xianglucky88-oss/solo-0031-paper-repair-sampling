from . import inventory, placement, records, sheets
from .errors import Problem
from .outlines import outline
from .rectangles import point_list, rectangle
from .validation import fields, identifier


def current(db, doc, zone):
    return [item for item in records.listing(db, 'patch', doc['id'])
            if (item['zone'], item['revision']) == (zone['id'], zone['revision'])]


def add(db, doc, zone, value):
    if not isinstance(value, dict) or not {'id', 'trial', 'origin'} <= set(value):
        raise Problem('字段必须为：id、trial、origin，且取料二选一传 cut 或 outline')
    has_cut, has_outline = 'cut' in value, 'outline' in value
    if has_cut == has_outline:
        raise Problem('取料须二选一：矩形补片传 cut，整片补片传 outline')
    key = identifier(value['id'])
    if records.find(db, 'patch', key, doc['id']):
        raise Problem('补片编号已使用', 409)
    trial = records.get(db, 'trial', identifier(value['trial']), doc['id'])
    if (trial['zone'], trial['revision'], trial['status']) != (zone['id'], zone['revision'], 'accepted'):
        raise Problem('补片须引用本区当前修订的合格试补', 409)
    selected = trial['selection']
    sheet = sheets.available(db, selected['sheet'])
    origin = point_list(value['origin'], 2)
    existing = current(db, doc, zone)
    if 'outline' in value:
        fields(value, 'id', 'trial', 'outline', 'origin')
        source_outline = outline(value['outline'], sheet['width'], sheet['height'])
        dest = placement.shape_destination(origin, source_outline, selected['turn'], zone, existing)
        allocation = dict(key=f"{doc['id']}:patch:{key}", document=doc['id'], zone=zone['id'],
                          revision=zone['revision'], kind='patch', id=key, shape=source_outline)
        patch = dict(id=key, zone=zone['id'], revision=zone['revision'], trial=trial['id'],
                     selection=selected, allocation=allocation, destination=dest,
                     origin=origin, shape='outline')
    else:
        fields(value, 'id', 'trial', 'cut', 'origin')
        cut = rectangle(value['cut'])
        dest = placement.destination(origin, cut, selected['turn'], zone, existing)
        allocation = dict(key=f"{doc['id']}:patch:{key}", document=doc['id'], zone=zone['id'],
                          revision=zone['revision'], kind='patch', id=key, shape=cut)
        patch = dict(id=key, zone=zone['id'], revision=zone['revision'], trial=trial['id'],
                     selection=selected, allocation=allocation, destination=dest,
                     origin=origin, shape='rect')
    inventory.reserve(db, sheet, allocation)
    return records.put(db, 'patch', key, patch, doc['id'])
