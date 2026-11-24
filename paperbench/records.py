from .codec import decode, encode
from .errors import Problem


def find(db, kind, key, scope=''):
    row = db.execute('SELECT body FROM records WHERE kind=? AND scope=? AND id=?', (kind, scope, key)).fetchone()
    return decode(row[0]) if row else None


def get(db, kind, key, scope=''):
    body = find(db, kind, key, scope)
    if body is None:
        raise Problem(f'找不到记录：{key}', 404)
    return body


def listing(db, kind, scope=''):
    return [decode(row[0]) for row in db.execute(
        'SELECT body FROM records WHERE kind=? AND scope=? ORDER BY id', (kind, scope)
    )]


def put(db, kind, key, body, scope='', *, replace=False):
    old = find(db, kind, key, scope)
    if old is not None:
        if replace:
            db.execute('UPDATE records SET body=? WHERE kind=? AND scope=? AND id=?',
                       (encode(body), kind, scope, key))
        elif old != body:
            raise Problem(f'编号已使用：{key}', 409)
    else:
        db.execute('INSERT INTO records VALUES (?,?,?,?)', (kind, scope, key, encode(body)))
    return body
