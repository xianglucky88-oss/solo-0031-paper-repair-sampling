from itertools import combinations, pairwise

from .errors import Problem
from .rectangles import point_list, overlaps


def edges(points):
    return list(pairwise([*points, points[0]]))


def outline(value, width, height):
    if not isinstance(value, list) or not 4 <= len(value) <= 32:
        raise Problem('轮廓须有 4–32 个顶点，无需重复首点')
    points = [point_list(p, 2) for p in value]
    if any(x > width or y > height for x, y in points):
        raise Problem('轮廓超出纸页边界')
    segments = edges(points)
    axes = []
    for (x, y), (r, b) in segments:
        if (x == r) == (y == b):
            raise Problem('轮廓边须为非零长度的水平或垂直线')
        axes.append(x == r)
    if any(a == b for a, b in pairwise([*axes, axes[0]])):
        raise Problem('轮廓不能有连续共线边')
    for i, j in combinations(range(len(segments)), 2):
        if j - i in (1, len(segments) - 1):
            continue
        (x, y), (r, b) = segments[i]
        (u, v), (s, t) = segments[j]
        if max(min(x, r), min(u, s)) <= min(max(x, r), max(u, s)) and \
           max(min(y, b), min(v, t)) <= min(max(y, b), max(v, t)):
            raise Problem('轮廓不能自交或自触')
    return points


def as_outline(shape):
    """Normalize a stored footprint to a polygon outline (rectangles get four corners)."""
    if not isinstance(shape, list):
        raise Problem('占位形状须为矩形或轮廓顶点列表')
    if shape and isinstance(shape[0], int):
        x, y, r, b = shape
        return [[x, y], [r, y], [r, b], [x, b]]
    return shape


def bbox(points):
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    return [min(xs), min(ys), max(xs), max(ys)]


def slabs(points):
    """Partition an orthogonal outline into non-overlapping horizontal rectangles."""
    ys = sorted({y for _, y in points})
    vertical = [(x, min(y, b), max(y, b)) for (x, y), (r, b) in edges(points) if x == r]
    for top, bottom in pairwise(ys):
        xs = sorted(x for x, start, stop in vertical if start <= top < stop)
        for left, right in zip(xs[::2], xs[1::2]):
            yield [left, top, right, bottom]


def area(points):
    return sum((r - x) * (b - y) for x, y, r, b in slabs(points))


def contains(points, shape):
    """True when the whole shape (rect [l,t,r,b] or outline) lies inside the outline."""
    return overlap_area(points, shape) == area(as_outline(shape))


def overlap_area(a, b):
    """Positive-area intersection of two orthogonal polygons; edge-only contact counts as zero."""
    left, right = as_outline(a), as_outline(b)
    return sum((min(r2, r1) - max(x2, x1)) * (min(b2, b1) - max(y2, y1))
               for x1, y1, r1, b1 in slabs(left)
               for x2, y2, r2, b2 in slabs(right)
               if overlaps([x1, y1, r1, b1], [x2, y2, r2, b2]))


def shapes_overlap(a, b):
    return overlap_area(a, b) > 0


def rotated_outline(points, turn):
    """Rotate an outline in place (90 is clockwise); 0 returns an equal copy."""
    if turn == 0:
        return [point[:] for point in points]
    if turn != 90:
        raise Problem('旋转角只支持 0 或 90 度')
    x0, y0, x1, y1 = bbox(points)
    height = y1 - y0
    return [[x0 + (height - 1) - (y - y0), y0 + (x - x0)] for x, y in points]


def placed_outline(points, origin, turn):
    """Rotate around the source bounding box, then pin the rotated bbox to origin (its top-left)."""
    rotated = rotated_outline(points, turn)
    x0, y0, _, _ = bbox(rotated)
    ox, oy = origin
    return [[x - x0 + ox, y - y0 + oy] for x, y in rotated]
