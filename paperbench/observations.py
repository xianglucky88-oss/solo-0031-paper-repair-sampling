from .errors import Problem
from .validation import fields, integer, text


def accept(observations, value, rule):
    fields(value, 'hour', 'drift', 'lifting', 'note')
    hour = integer(value['hour'], 0, 720, '观察时数')
    remaining = rule['hours'][len(observations):]
    if not remaining or hour != remaining[0]:
        raise Problem('应按规则顺序提交尚未登记的观察时间点', 409)
    if type(value['lifting']) is not bool:
        raise Problem('翘边须为布尔值')
    return {**value, 'hour': hour, 'drift': integer(value['drift'], 0, 1000, '色差 × 10'),
            'note': text(value['note'])}


def disposition(rows, rule):
    if any(row['lifting'] or row['drift'] > rule['drift'] for row in rows):
        return 'failed'
    return 'accepted' if len(rows) == len(rule['hours']) else 'pending'
