"""成组备料子域：承诺与取纸笔数、开裁、回执，以及凭已裁回执贴补。

备料位（slot）状态机：
    committed  备料成组接受，源纸矩形已占位，占一笔取纸笔数（未结算的承诺）
      ├─ start_cut → started  动刀前逐块确认；此时原修订仍可用、纸批仍有效
      │     ├─ receive(cut=true)  → cut      交回已裁回执，永久占位，结算为一笔实裁
      │     └─ receive(cut=false) → returned 未动刀交回，释放占位与笔数
      └─ cancel → cancelled       开裁前可整组撤销，释放占位与笔数

笔数口径：同一实物纸页上，除已交回（returned）外的每条 cut 记录都计一笔；
同一备料位由承诺转为已裁时 cut 键不变，因此始终只占一笔。
"""
from . import inventory, patches, placement, records, sheets
from .errors import Problem
from .outlines import contains
from .rectangles import footprint, overlaps, point_list, rectangle
from .validation import fields, identifier

ACTIVE = ('committed', 'started')
SETTLED = ('cut', 'returned', 'cancelled', 'superseded')


# ---------------------------------------------------------------- 读取与口径

def groups(db, doc_id):
    return records.listing(db, 'prep_group', doc_id)


def _group(db, doc, key):
    group = records.find(db, 'prep_group', key, doc['id'])
    if group is None:
        raise Problem(f'找不到备料组：{key}', 404)
    return group


def _slot(group, key):
    for slot in group['slots']:
        if slot['id'] == key:
            return slot
    raise Problem(f'备料组内找不到备料位：{key}', 404)


def _receipt_used(db, receipt):
    for scope in {row[0] for row in db.execute('SELECT DISTINCT scope FROM records WHERE kind=?', ('prep_group',))}:
        for group in groups(db, scope):
            if any(slot.get('receipt') == receipt for slot in group['slots']):
                return True
    return False


def quota_usage(db, sheet_id):
    """该实物纸页当前占用的取纸笔数：交回的承诺不计，其余每条 cut 一笔。"""
    returned = set()
    for scope in {row[0] for row in db.execute('SELECT DISTINCT scope FROM records WHERE kind=?', ('prep_group',))}:
        for group in groups(db, scope):
            for slot in group['slots']:
                if slot['status'] == 'returned':
                    returned.add(slot['allocation']['key'])
    return sum(1 for row in records.listing(db, 'cut', sheet_id) if row['key'] not in returned)


def _active_destinations(db, doc_id, zone_id, revision, *, exclude_slot=None):
    """该工作单缺口当前修订内，仍占位（未撤销/未交回）的备料位拟贴位置。

    拟贴位置只在同一工作单的同一缺口内互斥；源纸矩形的跨单据互斥由 inventory 保证。
    """
    rects = []
    for group in groups(db, doc_id):
        for slot in group['slots']:
            if slot['zone'] != zone_id or slot['revision'] != revision:
                continue
            if slot['status'] in ACTIVE or slot['status'] == 'cut':
                if exclude_slot is None or slot['id'] != exclude_slot:
                    rects.append(slot['destination'])
    return rects


# ---------------------------------------------------------------- 成组备料

def prepare(db, doc, value):
    fields(value, 'id', 'slots')
    key = identifier(value['id'])
    if records.find(db, 'prep_group', key, doc['id']):
        raise Problem('备料组编号已使用', 409)
    raw_slots = value['slots']
    if not isinstance(raw_slots, list) or not raw_slots or len(raw_slots) > 64:
        raise Problem('备料组须含 1–64 个备料位')

    planned = []                 # 先全部校验通过，再统一落库（整组接受或整体失败）
    demand = {}                  # sheet_id -> 本组新增笔数
    sheet_cache = {}

    def sheet_of(sheet_id):
        if sheet_id not in sheet_cache:
            sheet_cache[sheet_id] = sheets.available(db, sheet_id)
        return sheet_cache[sheet_id]

    for item in raw_slots:
        fields(item, 'id', 'zone', 'trial', 'cut', 'origin')
        slot_key = identifier(item['id'])
        if any(slot['id'] == slot_key for slot in planned):
            raise Problem('备料位编号在组内重复', 409)
        zone = records.get(db, 'zone', identifier(item['zone']), doc['id'])
        if zone['complete']:
            raise Problem('该区已完工，须先复开', 409)
        trial = records.get(db, 'trial', identifier(item['trial']), doc['id'])
        if (trial['zone'], trial['revision'], trial['status']) != (zone['id'], zone['revision'], 'accepted'):
            raise Problem('备料位须引用本区当前修订的合格试补', 409)
        selected = trial['selection']
        sheet = sheet_of(selected['sheet'])

        cut = rectangle(item['cut'])
        origin = point_list(item['origin'], 2)
        dest = footprint(origin, cut, selected['turn'])

        # 拟贴位置须落在当前未覆盖的缺口内，且与既有补片及其他备料位互不重叠
        if not contains(zone['outline'], dest):
            raise Problem('备料位拟贴位置超出损坏区轮廓')
        existing_patches = patches.current(db, doc, zone)
        if any(overlaps(dest, patch['destination']) for patch in existing_patches):
            raise Problem('备料位拟贴位置与已贴补片重叠', 409)
        if any(overlaps(dest, other['destination']) for other in planned):
            raise Problem('同组备料位拟贴位置彼此重叠', 409)
        if any(overlaps(dest, other) for other in
               _active_destinations(db, doc['id'], zone['id'], zone['revision'])):
            raise Problem('备料位拟贴位置与既有备料位重叠', 409)

        allocation = dict(key=f'{doc["id"]}:prep:{key}:{slot_key}', document=doc['id'],
                          zone=zone['id'], revision=zone['revision'], kind='prep',
                          group=key, id=slot_key, cut=cut)
        planned.append(dict(id=slot_key, group=key, zone=zone['id'], revision=zone['revision'],
                            trial=trial['id'], selection=selected, origin=origin, cut=cut,
                            destination=dest, allocation=allocation, status='committed'))
        demand[sheet['id']] = demand.get(sheet['id'], 0) + 1

    # 全组未超出每张实物纸页的剩余取纸笔数（未结算承诺与实裁都已计入 quota_usage）
    for sheet_id, extra in demand.items():
        limit = sheet_cache[sheet_id].get('quota', 512)
        if quota_usage(db, sheet_id) + extra > limit:
            raise Problem(f'纸页 {sheet_id} 剩余取纸笔数不足，整组拒绝', 409)

    # 源纸矩形在同一张实物纸上跨工作单、纸面、修订共享，逐个占位
    for slot in planned:
        inventory.reserve(db, sheet_cache[slot['selection']['sheet']], slot['allocation'])

    group = dict(id=key, document=doc['id'], status='committed', slots=planned)
    return records.put(db, 'prep_group', key, group, doc['id'])


# ---------------------------------------------------------------- 撤销与开裁

def cancel(db, doc, value):
    fields(value, 'group')
    group = _group(db, doc, identifier(value['group']))
    if group['status'] not in ACTIVE:
        raise Problem('只可在开裁确认前撤销尚未结算的备料组', 409)
    for slot in group['slots']:
        if slot['status'] in ACTIVE:
            inventory.release(db, slot['allocation'])
            slot['status'] = 'cancelled'
    group['status'] = 'cancelled'
    return records.put(db, 'prep_group', group['id'], group, doc['id'], replace=True)


def start_cut(db, doc, value):
    fields(value, 'group', 'slot')
    group = _group(db, doc, identifier(value['group']))
    slot = _slot(group, identifier(value['slot']))
    if slot['status'] != 'committed':
        raise Problem('只可对已承诺且未开裁的备料位确认开裁', 409)
    # 动刀前：原修订仍须可用、纸批仍须有效
    zone = records.get(db, 'zone', slot['zone'], doc['id'])
    if zone['revision'] != slot['revision'] or zone['complete']:
        raise Problem('原备料修订已不可用，不能开裁', 409)
    sheet = sheets.available(db, slot['selection']['sheet'])  # 纸批停用即抛错
    if not records.find(db, 'cut', slot['allocation']['key'], sheet['id']):
        raise Problem('备料占位已不存在，不能开裁', 409)
    slot['status'] = 'started'
    if all(s['status'] != 'committed' for s in group['slots']):
        group['status'] = 'started'
    return records.put(db, 'prep_group', group['id'], group, doc['id'], replace=True)


def receive(db, doc, value):
    fields(value, 'group', 'slot', 'receipt', 'cut')
    group = _group(db, doc, identifier(value['group']))
    slot = _slot(group, identifier(value['slot']))
    receipt = identifier(value['receipt'])
    if type(value['cut']) is not bool:
        raise Problem('回执须标明是否已动刀裁切')
    # 重送同一份回执只认一次：已按相同结论结算过则幂等返回，不再重复占位或结算
    if slot['status'] in SETTLED:
        if slot.get('receipt') == receipt and slot['status'] in ('cut', 'returned'):
            return group
        raise Problem('该备料位已结算，重送、改动回执或换编号再次结算都须拒绝', 409)
    if slot['status'] != 'started':
        raise Problem('只有已确认开裁的备料位可登记回执', 409)
    if _receipt_used(db, receipt):
        raise Problem('回执编号已用于结算，每个备料位只结算一次', 409)

    if value['cut']:
        # 已裁：永久占据原取纸位置，cut 键不变，仍只占一笔；回执随占位一并留痕
        slot['status'] = 'cut'
        slot['allocation'] = {**slot['allocation'], 'receipt': receipt}
    else:
        # 未动刀交回：在那之前仍占位，登记后释放占位与笔数
        inventory.release(db, slot['allocation'])
        slot['status'] = 'returned'
    slot['receipt'] = receipt
    if all(s['status'] in SETTLED for s in group['slots']):
        group['status'] = 'settled'
    elif all(s['status'] != 'committed' for s in group['slots']):
        group['status'] = 'started'
    return records.put(db, 'prep_group', group['id'], group, doc['id'], replace=True)


# ---------------------------------------------------------------- 凭回执贴补

def prepatch(db, doc, zone, value):
    fields(value, 'id', 'group', 'slot', 'trial', 'cut', 'origin')
    key = identifier(value['id'])
    if records.find(db, 'patch', key, doc['id']):
        raise Problem('补片编号已使用', 409)
    group = _group(db, doc, identifier(value['group']))
    slot = _slot(group, identifier(value['slot']))
    if slot['status'] != 'cut':
        raise Problem('只有已登记已裁回执的备料位可贴补', 409)

    # 重新核对：备料修订、试补资格、纸批及原定缺口位置
    if slot['zone'] != zone['id'] or slot['revision'] != zone['revision']:
        raise Problem('备料修订与当前缺口修订不符，须重新核对', 409)
    trial = records.get(db, 'trial', identifier(value['trial']), doc['id'])
    if (trial['zone'], trial['revision'], trial['status']) != (zone['id'], zone['revision'], 'accepted'):
        raise Problem('试补在当前修订不再合格，不能贴补', 409)
    if trial['id'] != slot['trial']:
        raise Problem('贴补须沿用备料位登记的合格试补', 409)
    selected = slot['selection']
    sheet = records.get(db, 'sheet', selected['sheet'])  # 纸批停用后仍可登记贴补
    cut = rectangle(value['cut'])
    origin = point_list(value['origin'], 2)
    if cut != slot['cut'] or origin != slot['origin']:
        raise Problem('贴补须使用备料位原定的取纸矩形与缺口位置', 409)
    dest = footprint(origin, cut, selected['turn'])
    if dest != slot['destination']:
        raise Problem('贴放矩形与备料位拟贴位置不一致', 409)

    # 已裁 cut 行永久存在；核对它确实按备料位置裁下
    cut_row = records.get(db, 'cut', slot['allocation']['key'], sheet['id'])
    if cut_row['cut'] != cut:
        raise Problem('已裁回执的取纸矩形与备料位置不符', 409)

    existing = patches.current(db, doc, zone)
    placement.check(zone, dest, existing)
    # 不与其他仍占位的备料位重叠（本备料位自身除外）
    if any(overlaps(dest, other) for other in
           _active_destinations(db, doc['id'], zone['id'], zone['revision'], exclude_slot=slot['id'])):
        raise Problem('贴放位置与其他备料位冲突', 409)

    allocation = dict(slot['allocation'], receipt=slot['receipt'])
    patch = dict(id=key, kind='prepatch', zone=zone['id'], revision=zone['revision'],
                 trial=trial['id'], selection=selected, allocation=allocation,
                 destination=dest, group=group['id'], slot=slot['id'], receipt=slot['receipt'])
    slot['patch'] = key
    records.put(db, 'prep_group', group['id'], group, doc['id'], replace=True)
    return records.put(db, 'patch', key, patch, doc['id'])
