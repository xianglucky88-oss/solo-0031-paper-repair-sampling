from . import events, inventory, patches, placement, prep, records, trials, zones
from .errors import Problem
from .validation import fields, identifier, text

# 不绑定单一损坏区、按整组操作的备料动作，请求体不含 zone
PREP_ACTIONS = {'prepare': prep.prepare, 'cancel': prep.cancel,
                'start_cut': prep.start_cut, 'receive': prep.receive}


def finish(db, doc, zone, value):
    fields(value)
    if placement.coverage(zone, patches.current(db, doc, zone))['remaining']:
        raise Problem('还有损坏面积未覆盖', 409)
    return records.put(db, 'zone', zone['id'], {**zone, 'complete': True}, doc['id'], replace=True)


def reopen(db, doc, zone, value):
    fields(value, 'reason')
    if not zone['complete']:
        raise Problem('只可复开已完工的损坏区', 409)
    # 复开令原修订失效：未结算（已承诺/已开裁）的备料位不能再开裁，释放其占位与笔数；
    # 已裁料永久占位，未动刀交回与撤销本就不占位。
    for group in prep.groups(db, doc['id']):
        changed = False
        for slot in group['slots']:
            if slot['zone'] == zone['id'] and slot['revision'] == zone['revision'] \
                    and slot['status'] in prep.ACTIVE:
                inventory.release(db, slot['allocation'])
                slot['status'] = 'superseded'
                changed = True
        if changed:
            if all(s['status'] in (*prep.SETTLED, 'superseded') for s in group['slots']):
                group['status'] = 'settled'
            records.put(db, 'prep_group', group['id'], group, doc['id'], replace=True)
    return records.put(db, 'zone', zone['id'], {**zone, 'complete': False,
                       'revision': zone['revision'] + 1, 'reason': text(value['reason'])},
                       doc['id'], replace=True)


OPERATIONS = {'trial': trials.start, 'observe': trials.observe, 'patch': patches.add,
              'prepatch': prep.prepatch, 'finish': finish, 'reopen': reopen}


def change(db, doc, action, request):
    if action == 'zone':
        fields(request, 'expected', 'data')
    elif action in PREP_ACTIONS:
        fields(request, 'expected', 'data')
    else:
        fields(request, 'expected', 'zone', 'data')
    expected = request['expected']
    events.guard(db, doc['id'], expected)
    if action == 'zone':
        result = zones.register(db, doc, request['data'])
        facts = {'zone': result['id'], 'result': result}
    elif action in PREP_ACTIONS:
        result = PREP_ACTIONS[action](db, doc, request['data'])
        facts = {'group': result['id'], 'result': result}
    else:
        zone = records.get(db, 'zone', identifier(request['zone']), doc['id'])
        if zone['complete'] and action != 'reopen':
            raise Problem('该区已完工，须先复开', 409)
        result = OPERATIONS[action](db, doc, zone, request['data'])
        facts = {'zone': zone['id'], 'result': result}
    version = events.append(db, doc['id'], expected, action, facts)
    return {'version': version, 'result': result}
