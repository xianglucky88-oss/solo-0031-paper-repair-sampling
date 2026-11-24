from . import records
from .errors import Problem
from .rectangles import MAX_COORD
from .validation import fields, identifier, integer, text


def history(doc):
    """Rules in force over this document's live versions, oldest first."""
    rows = doc.get('rule_history')
    return rows if rows else [{'rule': doc['rule'], 'from': 0}]


def current_rule(doc):
    return history(doc)[-1]['rule']


def register(db, value):
    fields(value, 'id', 'title', 'width', 'height', 'rule')
    key = identifier(value['id'])
    rule = records.get(db, 'rule', identifier(value['rule']))
    return records.put(db, 'document', key, {
        'id': key, 'title': text(value['title']), 'rule': rule,
        'rule_history': [{'rule': rule, 'from': 0}],
        'width': integer(value['width'], 1, MAX_COORD, '藏品页宽'),
        'height': integer(value['height'], 1, MAX_COORD, '藏品页高'),
    })


def adopt(db, doc, value, version):
    """Switch the live document to a registered rule at ``version``.

    Earlier rules and every earlier switch remain in the record; only the rule
    in force from this live version onward changes.  Nothing already cut,
    observed or patched is rewritten.
    """
    fields(value, 'rule')
    rule = records.get(db, 'rule', identifier(value['rule']))
    rows = history(doc)
    if rows[-1]['rule']['id'] == rule['id']:
        raise Problem('该规范已是当前规范', 409)
    if any(entry['rule']['id'] == rule['id'] for entry in rows):
        raise Problem('该规范已在本藏品适用过，不能重复采用', 409)
    updated = {**doc, 'rule': rule, 'rule_history': [*rows, {'rule': rule, 'from': version}]}
    records.put(db, 'document', doc['id'], updated, replace=True)
    return {'rule': rule['id'], 'from': version, 'previous': rows[-1]['rule']['id']}
