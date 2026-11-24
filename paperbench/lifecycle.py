from . import events, patches, placement, records, trials, zones
from .errors import Problem
from .validation import fields, identifier, text


def finish(db, doc, zone, value):
    fields(value)
    if placement.coverage(zone, patches.current(db, doc, zone))['remaining']:
        raise Problem('还有损坏面积未覆盖', 409)
    return records.put(db, 'zone', zone['id'], {**zone, 'complete': True}, doc['id'], replace=True)


def reopen(db, doc, zone, value):
    """Either reopen every patch of the zone, or lift exactly one piece.

    A plain ``reason`` keeps the historical whole-zone reopen: coverage starts
    from zero in a new revision.  Naming one covering patch as well only
    withdraws that piece; the others stay stuck, with their ids, revisions,
    trials and cuts untouched.
    """
    if not isinstance(value, dict) or 'reason' not in value:
        raise Problem('字段必须为：reason，或 reason 与一片补片')
    if set(value) & set(patches.LIFT_KEYS):
        return patches.replace(db, doc, zone, value)
    fields(value, 'reason')
    if not zone['complete']:
        raise Problem('只可复开已完工的损坏区', 409)
    revision = zone['revision'] + 1
    return records.put(db, 'zone', zone['id'], {
        **zone, 'complete': False, 'revision': revision, 'reason': text(value['reason']),
        'epoch': revision, 'replacements': [],
    }, doc['id'], replace=True)


# The replacement is recorded as ``replace``; the other names are accepted
# spellings for the same act of lifting one finished piece.
REPLACE_ACTIONS = {'replace', 'withdraw', 'retract'}
OPERATIONS = {'trial': trials.start, 'observe': trials.observe, 'patch': patches.add,
              'finish': finish, 'reopen': reopen,
              **{action: patches.replace for action in REPLACE_ACTIONS}}

# Reworking a completed zone (reopening it, or lifting one patch out of it)
# is the only work allowed to touch a completed zone.
COMPLETE_ACTIONS = {'reopen', *REPLACE_ACTIONS}


def change(db, doc, action, request):
    if action == 'zone':
        fields(request, 'expected', 'data')
    else:
        fields(request, 'expected', 'zone', 'data')
    expected = request['expected']
    events.guard(db, doc['id'], expected)
    if action == 'zone':
        result = zones.register(db, doc, request['data'])
        zone = result
    else:
        zone = records.get(db, 'zone', identifier(request['zone']), doc['id'])
        if zone['complete'] and action not in COMPLETE_ACTIONS:
            raise Problem('该区已完工，须先复开', 409)
        result = OPERATIONS[action](db, doc, zone, request['data'])
    version = events.append(db, doc['id'], expected, action, {'zone': zone['id'], 'result': result})
    return {'version': version, 'result': result}
