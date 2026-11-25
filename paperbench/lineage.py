"""Coordinate transforms for paper pages created by physical splits."""

from .rectangles import rectangle


def identity(sheet):
    return sheet['id'], [0, 0, sheet['width'], sheet['height']], 0


def root_frame(sheet):
    """Return the root page id, the sheet's frame on it, and accumulated turn."""
    lineage = sheet.get('lineage')
    if not lineage:
        return identity(sheet)
    frame = lineage.get('root_frame') or lineage.get('frame')
    if frame is None:
        # Backwards-tolerant shape for records written by early callers.
        origin = lineage.get('origin') or [0, 0]
        width = lineage.get('width', sheet['width'])
        height = lineage.get('height', sheet['height'])
        frame = [origin[0], origin[1], origin[0] + width, origin[1] + height]
    turn = lineage.get('root_turn', lineage.get('turn', 0))
    return lineage.get('root') or lineage.get('root_sheet') or sheet['id'], list(frame), turn


def map_to_root(sheet, value):
    """Map a rectangle registered in this sheet's top-left coordinates."""
    cut = rectangle(value)
    _, frame, turn = root_frame(sheet)
    x0, y0, x1, y1 = frame
    if turn == 0:
        mapped = [x0 + cut[0], y0 + cut[1], x0 + cut[2], y0 + cut[3]]
    elif turn == 180:
        mapped = [x1 - cut[2], y1 - cut[3], x1 - cut[0], y1 - cut[1]]
    else:
        # Split registrations only preserve face and permit 0/180.  A 90 degree
        # material choice is handled separately by compatibility/footprint.
        raise ValueError('纸页分张转向只能累积为 0 或 180 度')
    return rectangle(mapped)


def map_from_root(sheet, value):
    """Inverse of :func:`map_to_root` for this sheet's local coordinates."""
    rect = rectangle(value)
    _, frame, turn = root_frame(sheet)
    x0, y0, x1, y1 = frame
    if turn == 0:
        mapped = [rect[0] - x0, rect[1] - y0, rect[2] - x0, rect[3] - y0]
    elif turn == 180:
        mapped = [x1 - rect[2], y1 - rect[3], x1 - rect[0], y1 - rect[1]]
    else:
        raise ValueError('纸页分张转向只能累积为 0 或 180 度')
    return rectangle(mapped)


def compose_frame(parent, region, half_turn=0):
    """Find a child region's axis-aligned frame on the ultimate root page."""
    region = rectangle(region)
    root_id, parent_frame, parent_turn = root_frame(parent)
    child_frame = map_to_root(parent, region)
    return root_id, child_frame, (parent_turn + half_turn) % 360
