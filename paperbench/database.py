from contextlib import contextmanager
import sqlite3

from .schema import DDL


class Database:
    def __init__(self, path):
        self.path = path
        with self.transaction(write=True) as db:
            for statement in DDL.split(';'):
                if statement.strip():
                    db.execute(statement)

    @contextmanager
    def transaction(self, write=False):
        db = sqlite3.connect(self.path, isolation_level=None, timeout=5)
        try:
            db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()
