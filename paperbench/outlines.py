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
        raise Problem('轮廓超出藏品页边界')
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


def contains(points, rect):
    x, y, r, b = rect
    covered = sum((min(r, s) - max(x, u)) * (min(b, t) - max(y, v))
                  for u, v, s, t in slabs(points) if overlaps(rect, [u, v, s, t]))
    return covered == (r - x) * (b - y)
