from . import records
from .errors import Problem
from .validation import fields, identifier, integer


def register(db, body):
    fields(body, 'id', 'thickness_gap', 'ph_gap', 'color_gap', 'hours', 'drift', 'sample_edge')
    rules = {**body, 'id': identifier(body['id'])}
    for key, low, high in (('thickness_gap', 0, 3000), ('ph_gap', 0, 140), ('color_gap', 0, 1500),
                           ('drift', 0, 1000), ('sample_edge', 1, 100)):
        rules[key] = integer(body[key], low, high, key)
    hours = body['hours']
    if not isinstance(hours, list) or not 2 <= len(hours) <= 8:
        raise Problem('规则须有 2–8 个观察时间点')
    for hour in hours:
        integer(hour, 0, 720, '观察时数')
    if hours[0] != 0 or hours != sorted(set(hours)):
        raise Problem('观察时间须从 0 开始并严格递增')
    return records.put(db, 'rule', rules['id'], rules)
