from . import inventory, placement, records, sheets, trials
from .errors import Problem
from .rectangles import point_list, rectangle
from .validation import fields, identifier


def current(db, doc, zone):
    return [item for item in records.listing(db, 'patch', doc['id'])
            if (item['zone'], item['revision']) == (zone['id'], zone['revision'])]


def add(db, doc, zone, value):
    fields(value, 'id', 'trial', 'cut', 'origin')
    key = identifier(value['id'])
    if records.find(db, 'patch', key, doc['id']):
        raise Problem('补片编号已使用', 409)
    trial = records.get(db, 'trial', identifier(value['trial']), doc['id'])
    if trial['status'] != 'accepted' or not trials.member(trial, zone):
        raise Problem('补片须引用本区当前修订的合格试补', 409)
    selected = trial['selection']
    sheet = sheets.available(db, selected['sheet'])
    cut = rectangle(value['cut'])
    origin = point_list(value['origin'], 2)
    dest = placement.destination(origin, cut, selected['turn'], zone, current(db, doc, zone))
    allocation = dict(key=f"{doc['id']}:patch:{key}", document=doc['id'], zone=zone['id'],
                      revision=zone['revision'], kind='patch', id=key, cut=cut)
    inventory.reserve(db, sheet, allocation)
    patch = dict(id=key, zone=zone['id'], revision=zone['revision'], zones=[zone['id']],
                 trial=trial['id'], selection=selected, allocation=allocation, destination=dest)
    return records.put(db, 'patch', key, patch, doc['id'])
