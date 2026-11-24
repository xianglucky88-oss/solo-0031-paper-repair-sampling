import csv
from io import StringIO

CSV_FIELDS = ('zone', 'revision', 'patch', 'trial', 'sheet', 'lot', 'face', 'turn', 'cut', 'destination', 'rule')


def cutting_csv(rows):
    output = StringIO(newline='')
    writer = csv.DictWriter(output, CSV_FIELDS, lineterminator='\n')
    writer.writeheader()
    for row in rows:
        writer.writerow({**row, **{key: ' '.join(map(str, row[key])) for key in ('cut', 'destination')}})
    return output.getvalue().encode('utf-8')
