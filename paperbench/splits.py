from .splitting import *  # noqa: F401,F403
from .splitting import create, register_top_level


def split_sheet(db, source_or_body, body=None):
    if body is None:
        return register_top_level(db, source_or_body)
    return create(db, source_or_body, body)


register = register_top_level
register_split = split_sheet
