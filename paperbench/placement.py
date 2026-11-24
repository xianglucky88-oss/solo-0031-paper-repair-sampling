from .errors import Problem
from .outlines import area, contains
from .rectangles import footprint, overlaps, size


def check(zone, destination, existing):
    if not contains(zone['outline'], destination):
        raise Problem('补片超出损坏区轮廓')
    if any(overlaps(destination, patch['destination']) for patch in existing):
        raise Problem('贴补位置与当前修订的补片重叠', 409)


def destination(origin, cut, turn, zone, existing):
    rect = footprint(origin, cut, turn)
    check(zone, rect, existing)
    return rect


def coverage(zone, patches):
    target = area(zone['outline'])
    placed = sum(w * h for w, h in (size(p['destination']) for p in patches))
    return {'target': target, 'placed': placed, 'remaining': target - placed}
