from . import (archive, comparison, compatibility, documents, events, export,
               lifecycle, lineage, materials, records, rules, sheets, splitting,
               workbench)
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
        case 'GET', ['sheets', sheet] | ['sheet', sheet]:
            return workbench.sheet_view(db, records.get(db, 'sheet', identifier(sheet)))
        case 'POST', ['sheets', source, action] if action in {
                'split', 'splits', 'sheet-split', 'sheet-splits', 'split-sheet',
                'split_sheet', 'divide', 'divides', 'division', 'divisions'}:
            return splitting.create(db, records.get(db, 'sheet', identifier(source)), body)
        case 'POST', ['sheet', source, action] if action in {
                'split', 'splits', 'sheet-split', 'sheet-splits', 'divide', 'division', 'divisions'}:
            return splitting.create(db, records.get(db, 'sheet', identifier(source)), body)
        case 'POST', ['sheets', 'split', source] | ['split', source] | ['splits', source]:
            return splitting.create(db, records.get(db, 'sheet', identifier(source)), body)
        case 'POST', ['sheets', source, 'actions', action] if action in {'split', 'divide'}:
            return splitting.create(db, records.get(db, 'sheet', identifier(source)), body)
        case 'POST', ['sheets', source] if isinstance(body, dict) and body.get('action') in {'split', 'divide'}:
            return splitting.create(db, records.get(db, 'sheet', identifier(source)), body)
        case 'POST', ['sheets', 'split'] | ['split'] | ['splits'] | ['sheet-splits'] | ['sheet_splits'] \
                    | ['split-sheet'] | ['split_sheet'] | ['divide'] | ['divides'] | ['divide-sheet'] \
                    | ['divide_sheet'] | ['divisions'] | ['sheet-divide']:
            return splitting.register_top_level(db, body)
        case 'POST', ['sheets', key, action] if action in {
                'map', 'origin', 'original', 'root', 'resolve', 'locate', 'rebase',
                'coordinate', 'coordinates', 'to-root', 'to_original', 'to-original'}:
            sheet = records.get(db, 'sheet', identifier(key))
            cut = body.get('cut', body.get('rect', body.get('rectangle'))) if isinstance(body, dict) else None
            original = lineage.map_to_root(sheet, cut)
            root_sheet = lineage.root_frame(sheet)[0]
            return {'sheet': sheet['id'], 'cut': cut, 'lineage': sheet.get('lineage'),
                    'root_sheet': root_sheet, 'original_sheet': root_sheet,
                    'root_cut': original, 'original_cut': original}
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
        case 'POST', [action] if action == 'zone' or action in lifecycle.OPERATIONS:
            return lifecycle.change(db, doc, action, body)
        case 'POST', ['releases']:
            return archive.seal(db, doc, body)
        case 'GET', ['releases', version, *mode] if mode in ([], ['replay'], ['csv']):
            release = archive.load(db, doc, version_token(version))
            if mode == ['replay']:
                mappings = [{'sheet': row.get('original_sheet', row['sheet']),
                             'narrow_sheet': row['sheet'],
                             'cut': row['cut'],
                             'original_sheet': row.get('original_sheet', row['sheet']),
                             'original_cut': row.get('original_cut', row['cut'])}
                            for row in release['manifest']]
                return {'consistent': True, **archive.summary(release),
                        'manifest': release['manifest'], 'rows': release['manifest'],
                        'items': release['manifest'], 'mappings': mappings,
                        'origins': mappings, 'coordinates': mappings,
                        'original_coordinates': mappings}
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
