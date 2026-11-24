from .errors import Problem
from .outlines import area, as_outline, contains, placed_outline, shapes_overlap
from .rectangles import footprint


def check(zone, destination, existing):
    piece = as_outline(destination)
    if not contains(zone['outline'], piece):
        raise Problem('补片超出损坏区轮廓')
    if any(shapes_overlap(piece, as_outline(patch['destination'])) for patch in existing):
        raise Problem('贴补位置与当前修订的补片重叠', 409)


def destination(origin, cut, turn, zone, existing):
    rect = footprint(origin, cut, turn)
    check(zone, rect, existing)
    return rect


def shape_destination(origin, source_outline, turn, zone, existing):
    placed = placed_outline(source_outline, origin, turn)
    check(zone, placed, existing)
    return placed


def footprint_area(destination):
    return area(as_outline(destination))


def coverage(zone, patches):
    target = area(zone['outline'])
    placed = sum(footprint_area(p['destination']) for p in patches)
    return {'target': target, 'placed': placed, 'remaining': target - placed}
