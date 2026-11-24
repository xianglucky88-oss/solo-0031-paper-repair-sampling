from .codec import decode, encode
from .errors import Problem
from .validation import integer


def version(db, doc):
    return db.execute('SELECT coalesce(max(version), 0) FROM events WHERE document=?', (doc,)).fetchone()[0]


def guard(db, doc, expected):
    integer(expected, 0, 2**53 - 1, '版本')
    if version(db, doc) != expected:
        raise Problem('工作版本已变更，请重新核对后再提交', 409)


def append(db, doc, expected, action, facts):
    db.execute('INSERT INTO events VALUES (?,?,?,?)', (doc, expected + 1, action, encode(facts)))
    return expected + 1


def history(db, doc):
    return [dict(version=v, action=a, facts=decode(b)) for v, a, b in db.execute(
        'SELECT version, action, body FROM events WHERE document=? ORDER BY version', (doc,)
    )]
