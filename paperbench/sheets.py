from . import lineage, measurements, records, splitting
from .errors import Problem
from .rectangles import MAX_COORD
from .validation import fields, identifier, integer

def split_sheet(db, source_or_body, body=None):
    if body is None:
        return splitting.register_top_level(db, source_or_body)
    return splitting.create(db, source_or_body, body)


split = split_sheet
map_to_original = lineage.map_to_root
to_original = lineage.map_to_root
original_rect = lineage.map_to_root


def register(db, value):
    if isinstance(value, dict) and (
            value.get('action') in {'split', 'divide'} or
            value.get('split_from') or value.get('source_sheet') or
            value.get('original_sheet') or
            ((value.get('left') is not None or value.get('top') is not None)
             and (value.get('right') is not None or value.get('bottom') is not None))):
        payload = dict(value)
        for key in ('split_from', 'source_sheet', 'original_sheet', 'parent_sheet'):
            payload.setdefault('sheet', value.get(key))
        if payload.get('sheet') is None and isinstance(value.get('id'), str) and records.find(db, 'sheet', value['id']):
            return splitting.create(db, value['id'], payload)
        return splitting.register_top_level(db, payload)

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
    if sheet.get('state') == 'split' or sheet.get('split'):
        raise Problem('原页已分张，不能再从原编号新裁；请选择两张窄页编号', 409)
    if not records.get(db, 'lot', sheet['lot'])['active']:
        raise Problem('纸样批次已停用', 409)
    return sheet
