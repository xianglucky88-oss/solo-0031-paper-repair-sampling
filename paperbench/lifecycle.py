from . import events, patches, placement, records, trials, zones
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
              'mount': patches.mount, 'whole': patches.whole, 'place': patches.place,
              'finish': finish, 'reopen': reopen}


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
        if zone['complete'] and action != 'reopen':
            raise Problem('该区已完工，须先复开', 409)
        result = OPERATIONS[action](db, doc, zone, request['data'])
    version = events.append(db, doc['id'], expected, action, {'zone': zone['id'], 'result': result})
    return {'version': version, 'result': result}
