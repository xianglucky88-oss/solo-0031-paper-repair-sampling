from . import records
from .errors import Problem
from .validation import fields, identifier, integer

# 色差判定结论：同条件合格 / 换算保证合格 / 明确超限 / 依据冲突 / 证据不足 / 条件不可比
PASS = 'pass'
FAIL = 'fail'
CONFLICT = 'conflict'
INCONCLUSIVE = 'inconclusive'
INCOMPARABLE = 'incomparable'

LAB_KEYS = ('l', 'a', 'b')
LAB_LIMITS = {'l': (0, 1000), 'a': (-1280, 1270), 'b': (-1280, 1270)}
VERDICTS = (PASS, FAIL, CONFLICT, INCONCLUSIVE, INCOMPARABLE)


def component(name, axis):
    fields(name, 'low', 'high')
    low_bound, high_bound = LAB_LIMITS[axis]
    low = integer(name['low'], low_bound, high_bound, f'{axis} 量程下限')
    high = integer(name['high'], low_bound, high_bound, f'{axis} 量程上限')
    if low > high:
        raise Problem('来源测值量程的下限不得高于上限')
    return {'low': low, 'high': high}


def register(db, value):
    fields(value, 'id', 'version', 'source_condition', 'target_condition', 'ranges', 'deltas',
           'max_error', 'effective_at')
    key = identifier(value['id'])
    version = integer(value['version'], 1, 2 ** 53 - 1, '交接单版本')
    fields(value['ranges'], *LAB_KEYS)
    fields(value['deltas'], *LAB_KEYS)
    ranges = {axis: component(value['ranges'][axis], axis) for axis in LAB_KEYS}
    deltas = {axis: integer(value['deltas'][axis], -2000, 2000, f'{axis} 分量增减量') for axis in LAB_KEYS}
    handover = {
        'id': key,
        'version': version,
        'source_condition': identifier(value['source_condition']),
        'target_condition': identifier(value['target_condition']),
        'ranges': ranges,
        'deltas': deltas,
        'max_error': integer(value['max_error'], 0, 1500, '换算最大误差'),
        'effective_at': integer(value['effective_at'], 0, 2 ** 53 - 1, '生效现场版本'),
    }
    if handover['source_condition'] == handover['target_condition']:
        raise Problem('交接单仅用于不同测量条件之间的换算')
    return records.put(db, 'handover', f'{key}:{version}', handover)


def all_handovers(db):
    return records.listing(db, 'handover')


def _covers(handover, lab):
    # 来源测值各分量须落在适用闭区间内（含边界）。
    return all(handover['ranges'][axis]['low'] <= lab[axis] <= handover['ranges'][axis]['high']
               for axis in LAB_KEYS)


def applicable(handovers, source_condition, target_condition, lab, opened_at):
    # 同编号新版生效后旧版仅对过去的开样有意义：按开样时点选当时有效版本。
    latest = {}
    for handover in handovers:
        if handover['source_condition'] != source_condition or \
           handover['target_condition'] != target_condition or \
           handover['effective_at'] > opened_at or not _covers(handover, lab):
            continue
        old = latest.get(handover['id'])
        if old is None or handover['version'] > old['version']:
            latest[handover['id']] = handover
    return sorted(latest.values(), key=lambda item: (item['id'], item['version']))


def convert(handover, lab):
    return {axis: lab[axis] + handover['deltas'][axis] for axis in LAB_KEYS}


def converted_distance(handover, lab, target):
    mapped = convert(handover, lab)
    return sum((mapped[axis] - target['lab'][axis]) ** 2 for axis in LAB_KEYS) ** 0.5


def evaluate_handover(handover, lab, target, color_gap):
    distance = converted_distance(handover, lab, target)
    # 换算色差与实际色差之间的最大可能相差 max_error：
    # 最坏情况仍不超限才足以保证合格；最好情况仍超限则明确超限；其余无法确认。
    if distance + handover['max_error'] <= color_gap:
        verdict = PASS
    elif distance - handover['max_error'] > color_gap:
        verdict = FAIL
    else:
        verdict = INCONCLUSIVE
    return {'id': handover['id'], 'version': handover['version'],
            'effective_at': handover['effective_at'], 'max_error': handover['max_error'],
            'ranges': handover['ranges'], 'deltas': handover['deltas'],
            'converted_distance': distance, 'verdict': verdict}


def aggregate(items):
    if not items:
        return INCONCLUSIVE
    verdicts = {item['verdict'] for item in items}
    if PASS in verdicts and FAIL in verdicts:
        return CONFLICT
    if verdicts == {PASS}:
        return PASS
    if verdicts == {FAIL}:
        return FAIL
    return INCONCLUSIVE
