from . import records
from .errors import Problem
from .outlines import as_outline, bbox, shapes_overlap


def stored_shape(row):
    """Footprint of a cut record: new records store shape, legacy records store a cut rectangle."""
    return as_outline(row['shape'] if 'shape' in row else row['cut'])


def reserve(db, sheet, allocation):
    shape = as_outline(allocation['shape'])
    _, _, right, bottom = bbox(shape)
    if right > sheet['width'] or bottom > sheet['height']:
        raise Problem('裁切坐标超出纸页边界')
    existing = records.listing(db, 'cut', sheet['id'])
    if len(existing) >= 512:
        raise Problem('该纸页的裁切记录已达上限', 409)
    if any(shapes_overlap(shape, stored_shape(row)) for row in existing):
        raise Problem('裁切区与已切取区域重叠（正反面共用同一张纸）', 409)
    stored = dict(allocation)
    stored['shape'] = shape
    return records.put(db, 'cut', allocation['key'], stored, sheet['id'])
