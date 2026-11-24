from pathlib import Path

from . import codec, routes


def requests():
    return codec.decode((Path(__file__).resolve().parent.parent / 'examples' / 'bench.json').read_bytes())


def load(database):
    with database.transaction(write=True) as db:
        if db.execute('SELECT 1 FROM records LIMIT 1').fetchone():
            return
        for path, body in requests():
            routes.dispatch(db, 'POST', path.split('/'), body)
