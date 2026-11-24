from . import records
from .validation import fields, identifier, text


def register(db, value):
    fields(value, 'id', 'label')
    key, label = identifier(value['id']), text(value['label'])
    old = records.find(db, 'lot', key)
    if old and old['label'] == label:
        return old
    return records.put(db, 'lot', key, {'id': key, 'label': label, 'active': True})


def retire(db, value):
    fields(value, 'id', 'reason')
    key = identifier(value['id'])
    lot = records.get(db, 'lot', key)
    if not lot['active']:
        return lot
    return records.put(db, 'lot', key, {**lot, 'active': False, 'reason': text(value['reason'])}, replace=True)
