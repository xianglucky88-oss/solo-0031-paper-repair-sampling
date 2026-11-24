from .errors import Problem
from .validation import fields, integer, text


def accept(observations, value, rule, expected=None):
    fields(value, 'hour', 'drift', 'lifting', 'note')
    hour = integer(value['hour'], 0, 720, '观察时数')
    if expected is None:
        remaining = rule['hours'][len(observations):]
        expected = remaining[0] if remaining else None
    if expected is None or hour != expected:
        raise Problem('应按规范顺序提交尚未登记的观察时间点', 409)
    if type(value['lifting']) is not bool:
        raise Problem('翘边须为布尔值')
    return {**value, 'hour': hour, 'drift': integer(value['drift'], 0, 1000, '色差 × 10'),
            'note': text(value['note'])}


def passes(row, rule):
    return not row['lifting'] and row['drift'] <= rule['drift']


def assess(rows, rule):
    """Judge recorded observations against one rule without rewriting them.

    An observation may be carried over only when it was actually recorded at a
    time point the rule requires and its result meets this rule's threshold.
    A required time point that the recorded sequence already passed by can no
    longer be observed, so it cannot be carried over either.
    """
    by_hour = {row['hour']: row for row in rows}
    last = rows[-1]['hour'] if rows else None
    reused, rejected, unmet = [], [], []
    for hour in rule['hours']:
        row = by_hour.get(hour)
        if row is None:
            unmet.append(hour)
        elif passes(row, rule):
            reused.append(hour)
        else:
            rejected.append(hour)
    skipped = [hour for hour in unmet if last is not None and hour < last]
    open_hours = [hour for hour in unmet if not skipped]
    return {'reused': reused, 'rejected': rejected, 'unmet': unmet, 'skipped': skipped,
            'complete': not rejected and not unmet,
            'continuable': not rejected and not skipped and bool(open_hours),
            'next': open_hours[0] if not rejected and not skipped and open_hours else None,
            'failed': bool(rejected)}


def status(rows, rule):
    state = assess(rows, rule)
    if state['failed']:
        return 'failed'
    return 'accepted' if state['complete'] else 'pending'


def rank(history, rule_id):
    for index, entry in enumerate(history):
        if entry['rule']['id'] == rule_id:
            return index
    raise Problem('规范不在该藏品的修订记录中', 409)


def judgment(trial, rule, history):
    """Whether a trial can still authorise a patch under ``rule``.

    A failure judged under a rule stays binding for that rule and every later
    one, so relaxing a threshold in a newer rule cannot restore eligibility.
    A time point skipped by the recorded sequence blocks further observation.
    Only an actually recorded time point whose result meets the threshold is
    reused; the observation itself is never rewritten.
    """
    state = assess(trial['rows'], rule)
    failed = trial.get('failed_rule')
    if failed is None and (trial.get('failed') or trial.get('status') == 'failed'):
        failed = trial.get('rule') or history[0]['rule']['id']
    state['failed_rule'] = failed
    state['permanently_failed'] = failed is not None and rank(history, failed) <= rank(history, rule['id'])
    state['eligible'] = state['complete'] and not state['permanently_failed']
    state['continuable'] = state['continuable'] and not state['permanently_failed']
    if state['permanently_failed']:
        state['next'] = None
    return state
