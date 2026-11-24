from .errors import Problem
from .validation import integer

MAX_COORD = 3000


def point_list(value, length):
    if not isinstance(value, list) or len(value) != length:
        raise Problem(f'坐标须有 {length} 个整数')
    return [integer(x, 0, MAX_COORD, '坐标') for x in value]


def rectangle(value):
    x, y, r, b = point_list(value, 4)
    if x >= r or y >= b:
        raise Problem('矩形须有正的宽和高')
    return [x, y, r, b]


def overlaps(a, b):
    return max(a[0], b[0]) < min(a[2], b[2]) and max(a[1], b[1]) < min(a[3], b[3])


def size(rect):
    return rect[2] - rect[0], rect[3] - rect[1]


def footprint(origin, cut, turn):
    x, y = origin
    w, h = size(cut)
    if turn == 90:
        w, h = h, w
    return rectangle([x, y, x + w, y + h])
