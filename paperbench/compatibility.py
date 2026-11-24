from .measurements import color_distance_squared
from .validation import choice, fields, identifier


def selection(value):
    fields(value, 'sheet', 'face', 'turn')
    turn = value['turn']
    if type(turn) is not int:
        turn = None
    return {'sheet': identifier(value['sheet']), 'face': choice(value['face'], ('front', 'back'), '纸面'),
            'turn': choice(turn, (0, 90), '旋转角')}


def evaluate(zone, sheet, face, turn, rule):
    candidate = sheet['faces'][face]
    grain = sheet['stock']['grain']
    if turn == 90:
        grain = 'y' if grain == 'x' else 'x'
    thickness = abs(sheet['stock']['thickness'] - zone['stock']['thickness'])
    ph = abs(sheet['stock']['ph'] - zone['stock']['ph'])
    comparable = candidate['condition'] == zone['surface']['condition']
    distance = color_distance_squared(candidate, zone['surface']) if comparable else None
    checks = {'thickness': thickness <= rule['thickness_gap'], 'ph': ph <= rule['ph_gap'],
              'grain': grain == zone['stock']['grain'], 'condition': comparable,
              'color': None if distance is None else distance <= rule['color_gap'] ** 2}
    return {'compatible': all(checks.values()), 'checks': checks, 'thickness_gap': thickness,
            'ph_gap': ph, 'color_distance_squared': distance, 'grain': grain}
