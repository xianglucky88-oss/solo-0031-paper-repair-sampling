from . import compatibility, inventory, observations, records, sheets
from .errors import Problem
from .rectangles import rectangle, size
from .validation import fields, identifier


def start(db, doc, zone, value):
    fields(value, 'id', 'selection', 'cut')
    key = identifier(value['id'])
    if records.find(db, 'trial', key, doc['id']):
        raise Problem('试补编号已使用', 409)
    selected = compatibility.selection(value['selection'])
    sheet = sheets.available(db, selected['sheet'])
    check = compatibility.evaluate(zone, sheet, selected['face'], selected['turn'], doc['rule'])
    if not check['compatible']:
        raise Problem('所选纸面或旋转未通过适配评估')
    cut = rectangle(value['cut'])
    if min(size(cut)) < doc['rule']['sample_edge']:
        raise Problem('试补样片边长不足')
    allocation = dict(key=f"{doc['id']}:trial:{key}", document=doc['id'], zone=zone['id'],
                      revision=zone['revision'], kind='trial', id=key, cut=cut)
    inventory.reserve(db, sheet, allocation)
    trial = dict(id=key, zone=zone['id'], revision=zone['revision'], selection=selected,
                 allocation=allocation, rows=[], status='pending')
    return records.put(db, 'trial', key, trial, doc['id'])


def observe(db, doc, zone, value):
    fields(value, 'id', 'observation')
    trial = records.get(db, 'trial', identifier(value['id']), doc['id'])
    if (trial['zone'], trial['revision'], trial['status']) != (zone['id'], zone['revision'], 'pending'):
        raise Problem('只可续记当前修订中未判定的试补', 409)
    rows = [*trial['rows'], observations.accept(trial['rows'], value['observation'], doc['rule'])]
    status = observations.disposition(rows, doc['rule'])
    return records.put(db, 'trial', trial['id'], {**trial, 'rows': rows, 'status': status},
                       doc['id'], replace=True)
