"""把一份已在现场的损坏区按毫米轮廓拆成两个后继区。

拆分只改账：在位补片、补片取纸、试补样片和实物纸页上的裁切都不动。新区沿用原区的
目标纸面与材质厚度、pH 和纤维轴，并各自从第 1 修订开始计算覆盖与完工。原区的编号
停用，不能再作为有效区域接受操作。
"""
from . import measurements, patches, placement, records, trials
from .errors import Problem
from .outlines import area, contains, outline, slabs
from .rectangles import overlaps
from .validation import identifier, text

MAX_ZONES = 64


PARTS_KEYS = ('zones', 'parts', 'children', 'successors', 'pieces', 'segments', 'new_zones',
              'new', 'targets', 'results', 'replacements', 'newzones')
SOURCE_KEYS = ('zone', 'source', 'from', 'origin', 'id', 'parent')


def _looks_like_zone(value):
    return isinstance(value, dict) and 'id' in value and ('outline' in value or 'points' in value)


def _find_parts(scope, request):
    for holder in (scope, request):
        if not isinstance(holder, dict):
            continue
        found = next((holder[key] for key in PARTS_KEYS if key in holder), None)
        if found is not None:
            return found
        if _looks_like_zone(holder.get('first')) and _looks_like_zone(holder.get('second')):
            return [holder['first'], holder['second']]
        loose = [value for key, value in holder.items()
                 if key not in SOURCE_KEYS and key != 'data' and _looks_like_zone(value)]
        if len(loose) == 2:
            return loose
    return None


def payload(request):
    """取出原区编号和两个新区；原区编号与两个新区都可提交在 data 内或顶层。"""
    if not isinstance(request, dict):
        raise Problem('拆区请求须为对象')
    raw = request.get('data', request)
    if isinstance(raw, list):
        scope, parts = {}, raw
    elif isinstance(raw, dict):
        scope, parts = raw, _find_parts(raw, request)
    else:
        raise Problem('拆区须给出两个新区的编号和轮廓')
    source = next((request[key] for key in ('zone', 'source') if request.get(key)), None) \
        or next((scope[key] for key in SOURCE_KEYS if isinstance(scope.get(key), str)), None)
    if not isinstance(source, str) or parts is None:
        raise Problem('拆区须给出原区编号与两个新区的编号和轮廓')
    if isinstance(parts, dict):
        parts = [{'id': key, 'outline': value} for key, value in parts.items()]
    if not isinstance(parts, list):
        raise Problem('拆区须给出两个新区的编号和轮廓')
    return source, parts


ZONE_FIELDS = {'id', 'label', 'outline', 'points', 'stock', 'surface'}


def normalize(parts):
    """接受 {id,label,outline} 对象或 [id, outline] 二元组；新区可带上原区的材质字段。"""
    result = []
    for part in parts:
        if isinstance(part, dict):
            outline_value = part.get('outline', part.get('points'))
            if 'id' not in part or outline_value is None:
                raise Problem('每个新区须有编号和毫米轮廓')
            extra = set(part) - ZONE_FIELDS
            if extra:
                raise Problem('新区字段只能为 id、label、outline、stock、surface')
            result.append({'id': part['id'], 'outline': outline_value, 'label': part.get('label'),
                           'stock': part.get('stock'), 'surface': part.get('surface')})
        elif isinstance(part, (list, tuple)) and len(part) == 2 and isinstance(part[0], str):
            result.append({'id': part[0], 'outline': part[1], 'label': None, 'stock': None, 'surface': None})
        elif isinstance(part, (list, tuple)) and len(part) == 3 and isinstance(part[0], str) \
                and isinstance(part[1], str):
            result.append({'id': part[0], 'label': part[1], 'outline': part[2],
                           'stock': None, 'surface': None})
        else:
            raise Problem('每个新区须有编号和毫米轮廓')
    return result


def partition(old, first, second):
    """新区必须正好分完旧轮廓：无重叠、无缝隙、不越出旧区（含旧凹口）。"""
    xs = sorted({x for points in (old, first, second) for x, _ in points})
    ys = sorted({y for points in (old, first, second) for _, y in points})
    for left, right in zip(xs, xs[1:]):
        for top, bottom in zip(ys, ys[1:]):
            rect = [left, top, right, bottom]
            inside = [contains(points, rect) for points in (old, first, second)]
            if inside[1] and inside[2]:
                raise Problem('两个新损坏区轮廓不能重叠')
            if (inside[1] or inside[2]) and not inside[0]:
                raise Problem('新区轮廓不能超出原区轮廓或填平旧凹口')
            if inside[0] and not (inside[1] or inside[2]):
                raise Problem('两个新区须正好分完原区，不能留下缝隙')
    if area(first) + area(second) != area(old):
        raise Problem('两个新区须正好分完原区，不能留下缝隙')


def _overlaps_other(zones, old, points):
    pieces = list(slabs(points))
    for zone in zones:
        if zone['id'] == old['id'] or not zone.get('active', True):
            continue
        if any(overlaps(a, b) for a in pieces for b in slabs(zone['outline'])):
            return True
    return False


def _lineage(record):
    return list(record.get('lineage') or [])


def split(db, doc, request):
    source, parts = payload(request)
    old = records.get(db, 'zone', identifier(source), doc['id'])
    if not old.get('active', True):
        raise Problem('该区已拆分，不能再作为有效区域操作', 409)
    if len(parts) != 2:
        raise Problem('拆区须正好提交两个新区的编号和轮廓')
    existing = records.listing(db, 'zone', doc['id'])
    live = [zone for zone in existing if zone.get('active', True)]
    if len(live) - 1 + 2 > MAX_ZONES:
        raise Problem('损坏区数量已达上限', 409)

    used, prepared = {zone['id'] for zone in existing}, []
    for index, part in enumerate(normalize(parts)):
        key = identifier(part['id'])
        if key in used:
            raise Problem('损坏区编号已使用或数量已达上限', 409)
        used.add(key)
        points = outline(part['outline'], doc['width'], doc['height'])
        if area(points) <= 0:
            raise Problem('新区轮廓须围出面积')
        if part['stock'] is not None and measurements.stock(part['stock']) != old['stock']:
            raise Problem('新区纸面与材性须沿用原区')
        if part['surface'] is not None and measurements.surface(part['surface']) != old['surface']:
            raise Problem('新区纸面与材性须沿用原区')
        prepared.append({'id': key, 'label': text(part['label']) if part['label'] is not None else old['label'],
                         'outline': points, 'part': index})
    partition(old['outline'], prepared[0]['outline'], prepared[1]['outline'])
    for spec in prepared:
        if _overlaps_other(existing, old, spec['outline']):
            raise Problem('损坏区轮廓不能重叠')

    current = patches.current(db, doc, old)
    owner = {}
    for patch in current:
        inside = [index for index, spec in enumerate(prepared)
                  if contains(spec['outline'], patch['destination'])]
        if len(inside) != 1:
            raise Problem('新界线切过在位补片，整次拆区拒绝')
        owner[patch['id']] = inside[0]

    before = placement.coverage(old, current)
    zones, basin = [], []
    for index, spec in enumerate(prepared):
        assigned = [patch for patch in current if owner[patch['id']] == index]
        measured = placement.coverage(spec, assigned)
        if measured['remaining'] < 0:
            raise Problem('补片面积超出新区轮廓')
        basin.append(measured)
        zones.append({
            'id': spec['id'], 'label': spec['label'], 'outline': spec['outline'], 'revision': 1,
            'stock': old['stock'], 'surface': old['surface'],
            'complete': measured['remaining'] == 0, 'active': True,
            'origin': {'zone': old['id'], 'revision': old['revision'], 'label': old['label'],
                       'outline': old['outline'], 'part': spec['part']},
        })
    if sum(item['placed'] for item in basin) != before['placed']:
        raise Problem('拆区后补片覆盖不能增减')

    trial_rows = records.listing(db, 'trial', doc['id'])
    current_trials = [trial for trial in trial_rows
                      if old['id'] in trials.zones_of(trial) and trial['revision'] == old['revision']]
    memberships, homes = {}, {}
    for trial in current_trials:
        # The trial sample and observations apply to the whole original region, whose paper and
        # material the successors inherit, so the trial stays usable in both successors and is
        # still recorded once (one cut, one observation history). Keep an earlier sibling in the
        # membership list but let the home be one of the new successors so the signed release
        # still files it under a live zone.
        sibling = [zone for zone in trials.zones_of(trial) if zone != old['id']]
        successors = [zone['id'] for zone in zones]
        memberships[trial['id']] = list(dict.fromkeys([*sibling, *successors]))
        homes[trial['id']] = successors[0]

    for patch in current:
        index = owner[patch['id']]
        records.put(db, 'patch', patch['id'], {
            **patch, 'zone': zones[index]['id'], 'revision': 1, 'zones': [zones[index]['id']],
            'origin': {'zone': old['id'], 'revision': old['revision']},
            'lineage': _lineage(patch) + [old['id']],
        }, doc['id'], replace=True)
    for trial in current_trials:
        records.put(db, 'trial', trial['id'], {
            **trial, 'zone': homes[trial['id']], 'revision': 1, 'zones': memberships[trial['id']],
            'origin': {'zone': old['id'], 'revision': old['revision']},
            'lineage': _lineage(trial) + [old['id']],
        }, doc['id'], replace=True)
    for zone in zones:
        records.put(db, 'zone', zone['id'], zone, doc['id'])
    records.put(db, 'zone', old['id'], {**old, 'active': False,
               'split_into': [zone['id'] for zone in zones]}, doc['id'], replace=True)

    receipt = {
        'source': {'id': old['id'], 'label': old['label'], 'revision': old['revision'],
                   'outline': old['outline']},
        'zones': zones,
        'patches': [{'id': patch['id'], 'zone': zones[owner[patch['id']]]['id'],
                     'trial': patch['trial'], 'cut': patch['allocation']['cut'],
                     'destination': patch['destination']} for patch in current],
        'trials': [{'id': trial['id'], 'zones': memberships[trial['id']],
                    'cut': trial['allocation']['cut']} for trial in current_trials],
    }
    records.put(db, 'split', f"{old['id']}@{old['revision']}", receipt, doc['id'])
    return receipt
