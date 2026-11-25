"""Physical split of one paper sheet into two independently numbered pages."""

from . import lineage, records
from .errors import Problem
from .validation import identifier, integer

AXIS_ALIASES = {
    'x': 'x', 'at-x': 'x', 'vertical': 'x', 'v': 'x', 'col': 'x', 'column': 'x',
    'y': 'y', 'at-y': 'y', 'horizontal': 'y', 'h': 'y', 'row': 'y',
}
TURN_WORDS = {0: 0, 180: 180, '0': 0, '180': 180, 'same': 0, 'same-direction': 0,
              'same_direction': 0, 'forward': 0, 'normal': 0, 'half': 180,
              'half-turn': 180, 'half_turn': 180, 'halfturn': 180, 'reverse': 180,
              'reversed': 180, 'rotated': 180}
SIDE_KEYS = {
    'x': (('left', 'west', 'first', 'a', 'one', 'page_a', 'sheet_a'),
          ('right', 'east', 'second', 'b', 'two', 'page_b', 'sheet_b')),
    'y': (('top', 'upper', 'above', 'first', 'a', 'one', 'page_a', 'sheet_a'),
          ('bottom', 'lower', 'below', 'second', 'b', 'two', 'page_b', 'sheet_b')),
}


def first_key(data, keys):
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return None


def as_int(value, name):
    if type(value) is not int:
        raise Problem(f'{name} 须为整数')
    return value


def parse_turn(spec):
    if isinstance(spec, bool):
        return 180 if spec else 0
    value = first_key(spec, ('turn', 'rot', 'rotation', 'rotate', 'turn_180', 'turn180',
                             'rotate_180', 'rotate180', 'half', 'is_half',
                             'half_turn', 'halfTurn',
                             'half_circle', 'halfCircle', 'half_turned', 'halfTurned',
                             'semi_turn', 'rotated',
                             'reversed', 'inverted', 'upside_down', 'upsideDown',
                             'flip', 'flipped', 'orientation', 'direction',
                             'facing'))
    if value is None:
        return 0
    if isinstance(value, bool):
        return 180 if value else 0
    if value in TURN_WORDS:
        return TURN_WORDS[value]
    if isinstance(value, str):
        text = value.strip().lower().replace(' ', '-')
        if text in TURN_WORDS:
            return TURN_WORDS[text]
        if text in {'180°', '半圈', '转半圈', '纸面内转半圈'}:
            return 180
        if text in {'0°', '同向', '同方向'}:
            return 0
    raise Problem('窄页相对原页只可同向（0）或在纸面内转半圈（180）', 422)


def part_spec(value, side):
    if isinstance(value, str):
        value = {'id': value}
    if not isinstance(value, dict):
        raise Problem(f'{side} 窄页登记无效')
    child_id = first_key(value, ('id', 'sheet', 'sheet_id', 'number', 'no', 'name'))
    key = identifier(child_id)
    width = first_key(value, ('width', 'w'))
    height = first_key(value, ('height', 'h'))
    size = value.get('size')
    dimensions = value.get('dimensions')
    if isinstance(dimensions, dict):
        width = dimensions.get('width', dimensions.get('w')) if width is None else width
        height = dimensions.get('height', dimensions.get('h')) if height is None else height
    if isinstance(size, list) and len(size) == 2:
        width = size[0] if width is None else width
        height = size[1] if height is None else height
    side_hint = first_key(value, ('side', 'position', 'location', 'edge'))
    return {'id': key, 'turn': parse_turn(value), 'side_hint': side_hint,
            'width': None if width is None else as_int(width, '窄页宽'),
            'height': None if height is None else as_int(height, '窄页高')}


def side_index(hint, axis):
    if hint is None:
        return None
    text = str(hint).strip().lower().replace('_', '-')
    first_words = {'left', 'west', 'first', 'a', 'top', 'upper', 'above', 'start', 'begin'}
    second_words = {'right', 'east', 'second', 'b', 'bottom', 'lower', 'below', 'end'}
    if text in first_words:
        return 0
    if text in second_words:
        return 1
    return None


def axis_of(data, line=None):
    raw = first_key(data, ('axis', 'line_axis', 'cut_axis', 'direction', 'orientation', 'parallel'))
    if raw is not None:
        if not isinstance(raw, str):
            raise Problem('分线方向无效')
        text = raw.strip().lower().replace('_', '-')
        if text in AXIS_ALIASES:
            return AXIS_ALIASES[text]
        if text in {'parallel-to-left-edge', 'parallel-to-right-edge', 'left-edge', 'right-edge',
                    'parallel-to-y-axis', 'y-axis'}:
            return 'x'
        if text in {'parallel-to-top-edge', 'parallel-to-bottom-edge', 'top-edge', 'bottom-edge',
                    'parallel-to-x-axis', 'x-axis'}:
            return 'y'
        raise Problem('分线须与纸边平行', 422)
    if data.get('x') is not None:
        return 'x'
    if data.get('y') is not None:
        return 'y'
    if isinstance(line, list) and len(line) == 4 and line[0] == line[2]:
        return 'x'
    if isinstance(line, list) and len(line) == 4 and line[1] == line[3]:
        return 'y'
    return 'x'


def line_at(data, axis):
    value = first_key(data, ('at', 'position', 'offset', 'coordinate', 'coord', 'coordinate_at',
                             'line_at', 'cut_at', 'split_at', 'line_position', 'cut_line',
                             'split_line', 'value', 'line', 'x' if axis == 'x' else 'y'))
    if isinstance(value, dict):
        nested_axis = axis_of(value, value)
        if nested_axis != axis:
            axis = nested_axis
        value = first_key(value, ('at', 'position', 'offset', 'coordinate', 'coord', 'value',
                                  'x' if axis == 'x' else 'y'))
    if isinstance(value, list):
        if len(value) == 1:
            value = value[0]
        elif len(value) == 4 and all(type(x) is int for x in value):
            x0, y0, x1, y1 = value
            if axis == 'x' and x0 == x1:
                value = x0
            elif axis == 'y' and y0 == y1:
                value = y0
        elif len(value) == 2 and all(isinstance(p, list) and len(p) == 2 for p in value):
            (x0, y0), (x1, y1) = value
            if x0 == x1:
                axis, value = 'x', x0
            elif y0 == y1:
                axis, value = 'y', y0
    return axis, value


def extract_parts(data, axis):
    left_keys, right_keys = SIDE_KEYS[axis]
    first = first_key(data, left_keys)
    second = first_key(data, right_keys)

    # Flat forms such as left_id/left_turn and rightId/rightRotation.
    if first is None:
        left_id = first_key(data, tuple(k + suffix for k in left_keys[:6]
                                        for suffix in ('_id', '_sheet', '_page', '_number',
                                                      '_sheet_id', '_page_id')) +
                            ('leftId', 'leftSheet', 'leftPage', 'firstId', 'topId'))
        if left_id is not None:
            turn = first_key(data, ('left_turn', 'left_rotation', 'left_rotate',
                                    'left_half_turn', 'leftHalfTurn', 'left_rotated',
                                    'leftRotated', 'leftTurn',
                                    'leftRotation', 'first_turn', 'firstTurn',
                                    'first_rotation', 'firstRotation', 'top_turn', 'topTurn'))
            if turn is None:
                turns = data.get('turns') or data.get('rotations')
                if isinstance(turns, list) and len(turns) == 2:
                    turn = turns[0]
            first = {'id': left_id} if turn is None else {'id': left_id, 'turn': turn}
    if second is None:
        right_id = first_key(data, tuple(k + suffix for k in right_keys[:6]
                                         for suffix in ('_id', '_sheet', '_page', '_number',
                                                       '_sheet_id', '_page_id')) +
                             ('rightId', 'rightSheet', 'rightPage', 'secondId', 'bottomId'))
        if right_id is not None:
            turn = first_key(data, ('right_turn', 'right_rotation', 'right_rotate',
                                    'right_half_turn', 'rightHalfTurn', 'right_rotated',
                                    'rightRotated', 'rightTurn',
                                    'rightRotation', 'second_turn', 'secondTurn',
                                    'second_rotation', 'secondRotation',
                                    'bottom_turn', 'bottomTurn'))
            if turn is None:
                turns = data.get('turns') or data.get('rotations')
                if isinstance(turns, list) and len(turns) == 2:
                    turn = turns[1]
            second = {'id': right_id} if turn is None else {'id': right_id, 'turn': turn}

    if isinstance(first, str):
        turn = first_key(data, ('left_turn', 'left_rotation', 'left_rotate',
                                'left_half_turn', 'leftHalfTurn', 'left_rotated',
                                'leftRotated', 'leftTurn',
                                'leftRotation', 'first_turn', 'firstTurn',
                                'first_rotation', 'firstRotation', 'top_turn', 'topTurn'))
        if turn is not None:
            first = {'id': first, 'turn': turn}
    if isinstance(second, str):
        turn = first_key(data, ('right_turn', 'right_rotation', 'right_rotate',
                                'right_half_turn', 'rightHalfTurn', 'right_rotated',
                                'rightRotated', 'rightTurn',
                                'rightRotation', 'second_turn', 'secondTurn',
                                'second_rotation', 'secondRotation',
                                'bottom_turn', 'bottomTurn'))
        if turn is not None:
            second = {'id': second, 'turn': turn}

    if first is not None and second is not None:
        return part_spec(first, '第一'), part_spec(second, '第二')

    collection = first_key(data, ('parts', 'pages', 'pieces', 'sheets', 'children',
                                  'successors', 'new_sheets', 'narrow_sheets',
                                  'ids', 'sheet_ids', 'page_ids', 'numbers'))
    if collection is not None:
        if not isinstance(collection, list) or len(collection) != 2:
            raise Problem('分张须登记恰好两张窄页')
        turns = first_key(data, ('turns', 'turn', 'rotations', 'rotation', 'half_turns'))
        result = []
        for index, item in enumerate(collection):
            item_turn = turns[index] if isinstance(turns, list) and len(turns) == 2 else None
            if isinstance(item, str):
                item = {'id': item}
                if item_turn is not None:
                    item['turn'] = item_turn
            elif isinstance(item, dict) and item_turn is not None and not any(
                    key in item for key in ('turn', 'rotation', 'half_turn', 'orientation')):
                item = {**item, 'turn': item_turn}
            result.append(part_spec(item, '第一' if index == 0 else '第二'))
        indexes = [side_index(item.get('side_hint'), axis) for item in result]
        if any(index is not None for index in indexes):
            ordered = [None, None]
            for item, index in zip(result, indexes):
                if index is not None:
                    if ordered[index] is not None:
                        raise Problem('两张窄页的方位重复')
                    ordered[index] = item
            for item, index in zip(result, indexes):
                if index is None:
                    target = 0 if ordered[0] is None else 1
                    if ordered[target] is not None:
                        raise Problem('两张窄页的方位重复')
                    ordered[target] = item
            if any(item is None for item in ordered):
                raise Problem('无法确定两张窄页的方位')
            result = ordered
        return result

    # Common explicit ordered wrappers.
    first_value = first_key(data, ('first', 'page1', 'sheet1', 'one'))
    second_value = first_key(data, ('second', 'page2', 'sheet2', 'two'))
    if first_value is not None and second_value is not None:
        return part_spec(first_value, '第一'), part_spec(second_value, '第二')
    raise Problem('分张须给出两张窄页编号及转向')


def normalize_request(db, source, body):
    if not isinstance(body, dict):
        raise Problem('分张请求须为 JSON 对象')
    data = body.get('data') if isinstance(body.get('data'), dict) else body
    axis = axis_of(data)
    axis, at = line_at(data, axis)
    first_part, second_part = extract_parts(data, axis)

    width, height = source['width'], source['height']
    if at is None:
        if axis == 'x' and first_part['width'] is not None:
            at = first_part['width']
        elif axis == 'y' and first_part['height'] is not None:
            at = first_part['height']
        elif axis == 'x' and second_part['width'] is not None:
            at = width - second_part['width']
        elif axis == 'y' and second_part['height'] is not None:
            at = height - second_part['height']
    at = integer(at, 1, (width if axis == 'x' else height) - 1, '实际分线位置')

    if axis == 'x':
        regions = ([0, 0, at, height], [at, 0, width, height])
        expected_sizes = ((at, height), (width - at, height))
        side_names = ('left', 'right')
        line = [at, 0, at, height]
    else:
        regions = ([0, 0, width, at], [0, at, width, height])
        expected_sizes = ((width, at), (width, height - at))
        side_names = ('top', 'bottom')
        line = [0, at, width, at]

    parts = []
    for index, (part, region, size, side) in enumerate(zip(
            (first_part, second_part), regions, expected_sizes, side_names)):
        if part['width'] is not None and part['width'] != size[0]:
            raise Problem(f'{side} 窄页登记宽高不能正好分完原幅面', 422)
        if part['height'] is not None and part['height'] != size[1]:
            raise Problem(f'{side} 窄页登记宽高不能正好分完原幅面', 422)
        parts.append({**part, 'side': side, 'region': region,
                      'width': size[0], 'height': size[1]})

    if parts[0]['id'] == parts[1]['id']:
        raise Problem('两张窄页须使用不同编号', 409)
    if any(part['id'] == source['id'] for part in parts):
        raise Problem('窄页不得沿用原页编号', 409)
    for part in parts:
        existing = records.find(db, 'sheet', part['id'])
        if existing is not None and existing.get('parent') != source['id']:
            raise Problem(f'编号已使用：{part["id"]}', 409)

    intent = {'source': source['id'], 'axis': axis, 'at': at,
              'parts': [{'id': p['id'], 'turn': p['turn']} for p in parts]}
    return axis, at, line, parts, intent


def child_sheet(source, part):
    root_id, frame, root_turn = lineage.compose_frame(source, part['region'], part['turn'])
    parent_lineage = source.get('lineage') or {}
    if root_turn == 180:
        matrix = [[-1, 0, frame[2]], [0, -1, frame[3]]]
    else:
        matrix = [[1, 0, frame[0]], [0, 1, frame[1]]]
    info = {
        'root': root_id,
        'root_sheet': root_id,
        'parent': source['id'],
        'parent_sheet': source['id'],
        'depth': parent_lineage.get('depth', 0) + 1,
        'side': part['side'],
        'axis': None,
        'at': None,
        'region': part['region'],
        'frame': frame,
        'root_frame': frame,
        'root_rect': frame,
        'turn': root_turn,
        'root_turn': root_turn,
        'half_turn': part['turn'],
        'split_turn': part['turn'],
        'transform': {'turn': root_turn, 'matrix': matrix,
                      'point_matrix': matrix,
                      'note': 'x_prime=a*x+c; y_prime=d*y+e，矩形两角变换后重新排序'},
    }
    return {
        'id': part['id'], 'lot': source['lot'],
        'width': part['width'], 'height': part['height'],
        'stock': source['stock'], 'faces': source['faces'],
        'state': 'active', 'parent': source['id'], 'root': root_id,
        'provenance': info, 'lineage': info,
    }


def create(db, source, body):
    if isinstance(source, str):
        source = records.get(db, 'sheet', identifier(source))
    axis, at, line, parts, intent = normalize_request(db, source, body)

    existing = records.find(db, 'split', source['id'])
    if source.get('state') == 'split' or source.get('split') or existing:
        if existing and existing.get('intent') == intent:
            return enrich(existing, [records.get(db, 'sheet', sid) for sid in existing['sheets']], source)
        raise Problem('该纸页已分张；原编号不再接受新裁，也不能换线重分', 409)

    lot = records.get(db, 'lot', source['lot'])
    if not lot['active']:
        raise Problem('纸样批次已停用，不能登记分张新页', 409)

    children = []
    for part in parts:
        child = child_sheet(source, part)
        child['lineage']['axis'] = axis
        child['lineage']['at'] = at
        records.put(db, 'sheet', child['id'], child)
        children.append(child)

    record = {
        'id': source['id'],
        'kind': 'sheet_split',
        'sheet': source['id'],
        'source_sheet': source['id'],
        'original_sheet': source.get('root') or source['id'],
        'root_sheet': source.get('root') or source['id'],
        'parent_sheet': source.get('parent') or source['id'],
        'axis': axis,
        'at': at,
        'line': line,
        'line_rect': line,
        'sheets': [child['id'] for child in children],
        'parts': [{k: v for k, v in part.items()} for part in parts],
        'intent': intent,
    }
    for side, child, part in zip(('first', 'second'), children, parts):
        record[side] = child['id']
        record[part['side']] = child['id']
    records.put(db, 'split', source['id'], record)

    marked = {**source, 'state': 'split', 'split': {
        'id': source['id'], 'axis': axis, 'at': at, 'line': line,
        'sheets': record['sheets'], 'left': record.get('left'),
        'right': record.get('right'), 'top': record.get('top'),
        'bottom': record.get('bottom')}}
    records.put(db, 'sheet', source['id'], marked, replace=True)
    return enrich(record, children, marked)


def enrich(record, children, source):
    result = {**record, 'source': source, 'source_sheet_record': source,
              'sheet_ids': record['sheets'], 'children': children,
              'sheets': children, 'pages': children, 'child_sheets': children,
              'part_sheets': children}
    for child in children:
        side = child['lineage']['side']
        result[side] = child
        result[child['id']] = child
    return result


def register_top_level(db, body):
    if not isinstance(body, dict):
        raise Problem('分张请求须为 JSON 对象')
    data = body.get('data') if isinstance(body.get('data'), dict) else body
    source_id = first_key(data, ('sheet', 'sheet_id', 'sheetId', 'source', 'source_id',
                                'source_sheet', 'sourceSheet', 'original', 'original_id',
                                'original_sheet', 'originalSheet', 'parent', 'parent_id',
                                'parent_sheet', 'parentSheet'))
    if source_id is None:
        candidate = first_key(data, ('id', 'sheet_id', 'number'))
        if isinstance(candidate, str) and records.find(db, 'sheet', candidate):
            source_id = candidate
    source = records.get(db, 'sheet', identifier(source_id))
    return create(db, source, body)


split = create
divide = create
