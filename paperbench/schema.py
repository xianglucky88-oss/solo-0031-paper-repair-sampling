DDL = '''
CREATE TABLE IF NOT EXISTS records (
    kind TEXT NOT NULL,
    scope TEXT NOT NULL,
    id TEXT NOT NULL,
    body BLOB NOT NULL,
    PRIMARY KEY(kind, scope, id)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS events (
    document TEXT NOT NULL,
    version INTEGER NOT NULL CHECK(version > 0),
    action TEXT NOT NULL,
    body BLOB NOT NULL,
    PRIMARY KEY(document, version)
) WITHOUT ROWID;
'''
