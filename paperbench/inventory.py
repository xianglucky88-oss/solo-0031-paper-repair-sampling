from . import lineage, records
from .errors import Problem
from .rectangles import overlaps, rectangle


def lineage_sheets(db, sheet):
    root_id, _, _ = lineage.root_frame(sheet)
    sheets = records.listing(db, 'sheet')
    related = [row for row in sheets if lineage.root_frame(row)[0] == root_id]
    return root_id, related


def root_cut(sheet, cut):
    cut = rectangle(cut)
    return lineage.root_frame(sheet)[0], lineage.map_to_root(sheet, cut)


def lineage_cuts(db, sheet):
    """All reservations on this physical sheet and any split descendants."""
    root_id, related = lineage_sheets(db, sheet)
    result = []
    for other in related:
        for allocation in records.listing(db, 'cut', other['id']):
            rect = allocation['cut']
            root_rect = allocation.get('root_cut') or lineage.map_to_root(other, rect)
            result.append({**allocation, 'sheet': other['id'], 'root_sheet': root_id,
                           'root_cut': root_rect,
                           'view_cut': lineage.map_from_root(sheet, root_rect)})
    return result


def occupancy(db, sheet):
    return lineage_cuts(db, sheet)


def reserve(db, sheet, allocation):
    if sheet.get('state') == 'split' or sheet.get('split'):
        raise Problem('原页编号已分张，不能再从原编号新裁；请使用两张窄页自己的编号', 409)
    cut = rectangle(allocation['cut'])
    if cut[2] > sheet['width'] or cut[3] > sheet['height']:
        raise Problem('裁切坐标超出纸页边界')

    root_id, candidate_root = root_cut(sheet, cut)
    _, related = lineage_sheets(db, sheet)
    existing = []
    for other in related:
        for row in records.listing(db, 'cut', other['id']):
            root_rect = row.get('root_cut') or lineage.map_to_root(other, row['cut'])
            existing.append((other['id'], root_rect, row))

    own_count = len(records.listing(db, 'cut', sheet['id']))
    if own_count >= 512:
        raise Problem('该纸页的裁切记录已达上限', 409)
    if len(existing) >= 4096:
        raise Problem('该实物纸页谱系的裁切记录已达上限', 409)
    for source_id, old_root, row in existing:
        if overlaps(candidate_root, old_root):
            where = '原页' if source_id == root_id else f'谱系纸页 {source_id}'
            raise Problem(f'裁切区与{where}已切取区域重叠（正反面及分张后的同一实物谱系共用占位）', 409)

    allocation['root_sheet'] = root_id
    allocation['root_cut'] = candidate_root
    allocation['original_sheet'] = root_id
    allocation['original_cut'] = candidate_root
    allocation['source_sheet'] = root_id
    allocation['source_cut'] = candidate_root
    return records.put(db, 'cut', allocation['key'], allocation, sheet['id'])
