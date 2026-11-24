from . import measurements, records
from .errors import Problem
from .outlines import outline, slabs
from .rectangles import overlaps
from .validation import fields, identifier, text


def register(db, doc, value):
    fields(value, 'id', 'label', 'outline', 'stock', 'surface')
    key = identifier(value['id'])
    points = outline(value['outline'], doc['width'], doc['height'])
    zones = records.listing(db, 'zone', doc['id'])
    if len(zones) >= 64 or any(old['id'] == key for old in zones):
        raise Problem('损坏区编号已使用或数量已达上限', 409)
    pieces = list(slabs(points))
    if any(overlaps(a, b) for old in zones for a in pieces for b in slabs(old['outline'])):
        raise Problem('损坏区轮廓不能重叠')
    zone = {'id': key, 'label': text(value['label']), 'outline': points, 'revision': 1,
            'stock': measurements.stock(value['stock']), 'surface': measurements.surface(value['surface']),
            'complete': False}
    return records.put(db, 'zone', key, zone, doc['id'])
