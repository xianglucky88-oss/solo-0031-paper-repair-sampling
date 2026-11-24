from . import (compatibility, documents, inventory, observations, records, sheets)
from .errors import Problem
from .rectangles import rectangle, size
from .validation import fields, identifier


def start(db, doc, zone, value):
    fields(value, 'id', 'selection', 'cut')
    key = identifier(value['id'])
    if records.find(db, 'trial', key, doc['id']):
        raise Problem('试补编号已使用', 409)
    rule = documents.current_rule(doc)
    selected = compatibility.selection(value['selection'])
    sheet = sheets.available(db, selected['sheet'])
    check = compatibility.evaluate(zone, sheet, selected['face'], selected['turn'], rule)
    if not check['compatible']:
        raise Problem('所选纸面或旋转未通过适配评估')
    cut = rectangle(value['cut'])
    if min(size(cut)) < rule['sample_edge']:
        raise Problem('试补样片边长不足')
    allocation = dict(key=f"{doc['id']}:trial:{key}", document=doc['id'], zone=zone['id'],
                      revision=zone['revision'], kind='trial', id=key, cut=cut)
    inventory.reserve(db, sheet, allocation)
    trial = dict(id=key, zone=zone['id'], revision=zone['revision'], selection=selected,
                 allocation=allocation, rule=rule['id'], rows=[], status='pending', failed=False)
    return records.put(db, 'trial', key, trial, doc['id'])


def observe(db, doc, zone, value):
    fields(value, 'id', 'observation')
    trial = records.get(db, 'trial', identifier(value['id']), doc['id'])
    if (trial['zone'], trial['revision']) != (zone['id'], zone['revision']):
        raise Problem('只可续记本区当前修订的试补', 409)
    if trial.get('failed') or trial.get('status') == 'failed':
        raise Problem('该试补已按当时适用的规范判定不合格，须另开试补', 409)
    rule = documents.current_rule(doc)
    state = observations.judgment(trial, rule, documents.history(doc))
    if not state['continuable']:
        raise Problem('该试补不能按当前规范继续观察，须另开试补', 409)
    row = observations.accept(trial['rows'], value['observation'], rule, expected=state['next'])
    rows = [*trial['rows'], {**row, 'rule': rule['id']}]
    status = observations.status(rows, rule)
    failed = status == 'failed'
    return records.put(db, 'trial', trial['id'],
                       {**trial, 'rows': rows, 'status': status, 'failed': failed,
                        'failed_rule': rule['id'] if failed else trial.get('failed_rule')},
                       doc['id'], replace=True)


def evaluate(db, doc, zone, trial):
    """Assess a trial for use under the document's current rule, read-only."""
    rule = documents.current_rule(doc)
    state = observations.judgment(trial, rule, documents.history(doc))
    state['sample_edge_ok'] = min(size(trial['allocation']['cut'])) >= rule['sample_edge']
    sheet = records.get(db, 'sheet', trial['selection']['sheet'])
    state['active'] = records.get(db, 'lot', sheet['lot'])['active']
    state['face_fit_ok'] = compatibility.evaluate(zone, sheet, trial['selection']['face'],
                                                  trial['selection']['turn'], rule)['compatible']
    state['authorizing'] = (state['eligible'] and state['sample_edge_ok']
                            and state['face_fit_ok'] and state['active'])
    state['rule'] = rule['id']
    return state


def authorize(db, doc, zone, trial):
    """Confirm a trial may authorise a patch under the document's current rule.

    The physical cut actually made must meet the new rule's minimum sample
    size, the selected face must pass its paper fit, and the recorded
    observations must cover every time point it requires without a skipped
    hour or an earlier failure.  The cut and its stock reservation are never
    released by a switch.
    """
    state = evaluate(db, doc, zone, trial)
    if not state['active']:
        raise Problem('纸样批次已停用', 409)
    if not state['eligible']:
        raise Problem('该试补未通过当前规范，不能授权补片', 409)
    if not state['sample_edge_ok']:
        raise Problem('该试补样片边长不满足当前规范', 409)
    if not state['face_fit_ok']:
        raise Problem('该试补选面未通过当前规范的纸面适配', 409)
    return state


def start_rule(trial, history):
    return trial.get('rule') or history[0]['rule']['id']


def reused_rows(trial, rule, history):
    """Observations recorded under an earlier rule that this rule relies on.

    Rows from before rules were tracked carry no rule of their own; they count
    as recorded under the trial's starting rule.
    """
    began = start_rule(trial, history)
    return [row for row in trial['rows'] if row['hour'] in rule['hours']
            and row.get('rule', began) != rule['id']]
