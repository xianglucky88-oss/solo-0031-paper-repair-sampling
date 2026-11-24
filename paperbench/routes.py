from . import (archive, comparison, compatibility, documents, events, export,
               lifecycle, materials, records, rules, sheets, workbench)
from .errors import Problem
from .validation import fields, identifier

REGISTRATION = {'rules': rules.register, 'documents': documents.register,
                'lots': materials.register, 'sheets': sheets.register, 'retire': materials.retire}


def version_token(value):
    if not value.isascii() or not value.isdecimal() or len(value) > 16:
        raise Problem('封存版本无效')
    return int(value)


def dispatch(db, method, path, body):
    match method, path:
        case 'GET', ['catalog']:
            return workbench.catalog(db)
        case 'GET', ['sheets', sheet]:
            return workbench.sheet_view(db, records.get(db, 'sheet', identifier(sheet)))
        case 'POST', [kind] if kind in REGISTRATION:
            return REGISTRATION[kind](db, body)
        case _, ['documents', key, *tail]:
            doc = records.get(db, 'document', identifier(key))
            return document_route(db, doc, method, tail, body)
        case _:
            raise Problem('没有此接口', 404)


def document_route(db, doc, method, tail, body):
    match method, tail:
        case 'GET', []:
            return workbench.board(db, doc)
        case 'GET', ['events']:
            return events.history(db, doc['id'])
        case 'POST', ['preview']:
            fields(body, 'zone', 'selection')
            zone = records.get(db, 'zone', identifier(body['zone']), doc['id'])
            selected = compatibility.selection(body['selection'])
            sheet = sheets.available(db, selected['sheet'])
            return compatibility.evaluate(zone, sheet, selected['face'], selected['turn'], doc['rule'])
        case 'POST', [action] if action == 'zone' or action in lifecycle.OPERATIONS or action in lifecycle.PREP_ACTIONS:
            return lifecycle.change(db, doc, action, body)
        case 'POST', ['releases']:
            return archive.seal(db, doc, body)
        case 'GET', ['releases', version, *mode] if mode in ([], ['replay'], ['csv']):
            release = archive.load(db, doc, version_token(version))
            if mode == ['replay']:
                return {'consistent': True, **archive.summary(release)}
            if mode == ['csv']:
                return export.cutting_csv(release['manifest'])
            return release
        case 'GET', ['compare', old, new]:
            a, b = version_token(old), version_token(new)
            if a >= b:
                raise Problem('请选择早版与晚版')
            return {'from': a, 'to': b, 'changes': comparison.compare(archive.load(db, doc, a), archive.load(db, doc, b))}
        case _:
            raise Problem('没有此接口', 404)
