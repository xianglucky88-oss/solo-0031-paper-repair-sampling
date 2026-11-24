from . import events, patches, placement, records, splits, trials, zones
from .errors import Problem
from .validation import fields, identifier, text


def finish(db, doc, zone, value):
    fields(value)
    if placement.coverage(zone, patches.current(db, doc, zone))['remaining']:
        raise Problem('还有损坏面积未覆盖', 409)
    return records.put(db, 'zone', zone['id'], {**zone, 'complete': True}, doc['id'], replace=True)


def reopen(db, doc, zone, value):
    fields(value, 'reason')
    if not zone['complete']:
        raise Problem('只可复开已完工的损坏区', 409)
    return records.put(db, 'zone', zone['id'], {**zone, 'complete': False,
                       'revision': zone['revision'] + 1, 'reason': text(value['reason'])},
                       doc['id'], replace=True)


OPERATIONS = {'trial': trials.start, 'observe': trials.observe, 'patch': patches.add,
              'finish': finish, 'reopen': reopen}


def active(zone):
    return zone.get('active', True)


def change(db, doc, action, request):
    if action == 'split':
        if not isinstance(request, dict) or 'expected' not in request or 'data' not in request:
            raise Problem('拆区须提交现场版本和两个新区的编号与轮廓')
    elif action == 'zone':
        fields(request, 'expected', 'data')
    else:
        fields(request, 'expected', 'zone', 'data')
    expected = request['expected']
    events.guard(db, doc['id'], expected)
    if action == 'zone':
        result = zones.register(db, doc, request['data'])
        zone = result
        facts = {'zone': zone['id'], 'result': result}
    elif action == 'split':
        result = splits.split(db, doc, request)
        facts = {'zones': [zone['id'] for zone in result['zones']], 'result': result}
    else:
        zone = records.get(db, 'zone', identifier(request['zone']), doc['id'])
        if not active(zone):
            raise Problem('该区已拆分，不能再作为有效区域操作', 409)
        if zone['complete'] and action != 'reopen':
            raise Problem('该区已完工，须先复开', 409)
        result = OPERATIONS[action](db, doc, zone, request['data'])
        facts = {'zone': zone['id'], 'result': result}
    version = events.append(db, doc['id'], expected, action, facts)
    return {'version': version, 'result': result}
