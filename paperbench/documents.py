from . import records
from .rectangles import MAX_COORD
from .validation import fields, identifier, integer, text


def register(db, value):
    fields(value, 'id', 'title', 'width', 'height', 'rule')
    key = identifier(value['id'])
    rule = records.get(db, 'rule', identifier(value['rule']))
    return records.put(db, 'document', key, {
        'id': key, 'title': text(value['title']), 'rule': rule,
        'width': integer(value['width'], 1, MAX_COORD, '藏品页宽'),
        'height': integer(value['height'], 1, MAX_COORD, '藏品页高'),
    })
