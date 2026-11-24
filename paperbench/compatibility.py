from . import handovers
from .measurements import color_distance_squared
from .validation import choice, fields, identifier


def selection(value):
    fields(value, 'sheet', 'face', 'turn')
    turn = value['turn']
    if type(turn) is not int:
        turn = None
    return {'sheet': identifier(value['sheet']), 'face': choice(value['face'], ('front', 'back'), '纸面'),
            'turn': choice(turn, (0, 90), '旋转角')}


def color_verdict(zone, candidate, rule, handover_list, opened_at):
    target = zone['surface']
    if candidate['condition'] == target['condition']:
        # 同条件照常直接比较，不使用交接单。
        distance = color_distance_squared(candidate, target) ** 0.5
        return {'basis': 'same_condition', 'verdict': handovers.PASS if distance <= rule['color_gap']
                else handovers.FAIL, 'distance': distance, 'bases': []}
    items = [handovers.evaluate_handover(handover, candidate['lab'], target, rule['color_gap'])
             for handover in handovers.applicable(handover_list, candidate['condition'],
                                                  target['condition'], candidate['lab'], opened_at)]
    verdict = handovers.INCOMPARABLE if not items else handovers.aggregate(items)
    return {'basis': 'handover', 'verdict': verdict, 'bases': items}


def evaluate(zone, sheet, face, turn, rule, handover_list=(), opened_at=0):
    candidate = sheet['faces'][face]
    grain = sheet['stock']['grain']
    if turn == 90:
        grain = 'y' if grain == 'x' else 'x'
    thickness = abs(sheet['stock']['thickness'] - zone['stock']['thickness'])
    ph = abs(sheet['stock']['ph'] - zone['stock']['ph'])
    comparable = candidate['condition'] == zone['surface']['condition']
    color = color_verdict(zone, candidate, rule, handover_list, opened_at)
    checks = {'thickness': thickness <= rule['thickness_gap'], 'ph': ph <= rule['ph_gap'],
              'grain': grain == zone['stock']['grain'], 'condition': comparable,
              'color': color['verdict'] == handovers.PASS}
    # 同条件直接比较；异条件凭当时适用的交接单保证色差，厚度、pH 与纤维仍须满足。
    return {'compatible': checks['thickness'] and checks['ph'] and checks['grain'] and checks['color'],
            'checks': checks, 'thickness_gap': thickness, 'ph_gap': ph, 'grain': grain,
            'color_result': color}
