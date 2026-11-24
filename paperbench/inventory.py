from . import records
from .errors import Problem
from .rectangles import overlaps, rectangle


def reserve(db, sheet, allocation):
    cut = rectangle(allocation['cut'])
    if cut[2] > sheet['width'] or cut[3] > sheet['height']:
        raise Problem('裁切坐标超出纸页边界')
    existing = records.listing(db, 'cut', sheet['id'])
    if len(existing) >= 512:
        raise Problem('该纸页的裁切记录已达上限', 409)
    if any(overlaps(cut, row['cut']) for row in existing):
        raise Problem('裁切区与已切取区域重叠（正反面共用同一张纸）', 409)
    return records.put(db, 'cut', allocation['key'], allocation, sheet['id'])
