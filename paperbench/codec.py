import hashlib
import json


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(encode(value)).hexdigest()


def decode(raw):
    def object_pairs(pairs):
        obj = dict(pairs)
        if len(obj) != len(pairs):
            raise ValueError('duplicate JSON key')
        return obj

    def invalid(value):
        raise ValueError(f'invalid JSON value: {value}')

    return json.loads(raw.decode('utf-8'), object_pairs_hook=object_pairs, parse_constant=invalid)
