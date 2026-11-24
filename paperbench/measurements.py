from .validation import choice, fields, identifier, integer


def surface(value):
    fields(value, 'condition', 'lab')
    lab = value['lab']
    fields(lab, 'l', 'a', 'b')
    return {'condition': identifier(value['condition']), 'lab': {
        'l': integer(lab['l'], 0, 1000, 'L* × 10'),
        'a': integer(lab['a'], -1280, 1270, 'a* × 10'),
        'b': integer(lab['b'], -1280, 1270, 'b* × 10'),
    }}


def stock(value):
    fields(value, 'thickness', 'ph', 'grain')
    return {'thickness': integer(value['thickness'], 1, 3000, '厚度 μm'),
            'ph': integer(value['ph'], 0, 140, 'pH × 10'),
            'grain': choice(value['grain'], ('x', 'y'), '纤维轴')}


def color_distance_squared(a, b):
    return sum((a['lab'][key] - b['lab'][key]) ** 2 for key in ('l', 'a', 'b'))
