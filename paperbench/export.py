import csv
from io import StringIO

CSV_FIELDS = ('zone', 'revision', 'patch', 'trial', 'sheet', 'lot', 'face', 'turn', 'cut', 'destination', 'rule')


def flat(shape):
    # A rectangle is four flat ints; an outline is a list of [x, y] vertices.
    if shape and isinstance(shape[0], int):
        return shape
    return [coord for point in shape for coord in point]


def cutting_csv(rows):
    output = StringIO(newline='')
    writer = csv.DictWriter(output, CSV_FIELDS, lineterminator='\n')
    writer.writeheader()
    for row in rows:
        writer.writerow({**row, **{key: ' '.join(map(str, flat(row[key]))) for key in ('cut', 'destination')}})
    return output.getvalue().encode('utf-8')
