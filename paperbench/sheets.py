from . import measurements, records
from .errors import Problem
from .rectangles import MAX_COORD
from .validation import fields, identifier, integer


def register(db, value):
    fields(value, 'id', 'lot', 'width', 'height', 'stock', 'faces')
    key, lot = identifier(value['id']), identifier(value['lot'])
    if not records.get(db, 'lot', lot)['active']:
        raise Problem('纸样批次已停用', 409)
    faces = fields(value['faces'], 'front', 'back')
    return records.put(db, 'sheet', key, {
        'id': key, 'lot': lot, 'width': integer(value['width'], 1, MAX_COORD, '纸页宽'),
        'height': integer(value['height'], 1, MAX_COORD, '纸页高'),
        'stock': measurements.stock(value['stock']),
        'faces': {face: measurements.surface(measurement) for face, measurement in faces.items()},
    })


def available(db, key):
    sheet = records.get(db, 'sheet', identifier(key))
    if not records.get(db, 'lot', sheet['lot'])['active']:
        raise Problem('纸样批次已停用', 409)
    return sheet
