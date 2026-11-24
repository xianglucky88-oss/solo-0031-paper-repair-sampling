import re

from .errors import Problem


def fields(value, *keys):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise Problem('字段必须为：' + ', '.join(keys))
    return value


def integer(value, low, high, name):
    if type(value) is not int or not low <= value <= high:
        raise Problem(f'{name} 须为 {low} 至 {high} 的整数')
    return value


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,39}', value):
        raise Problem('编号须为 1–40 位字母、数字、下划线或连字符，且以字母或数字开头')
    return value


def text(value):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 160 or any(ord(c) < 32 for c in value):
        raise Problem('文本须为 1–160 字且不得含控制字符')
    try:
        value.encode('utf-8')
    except UnicodeError as exc:
        raise Problem('文本不是有效的 Unicode') from exc
    return value.strip()


def choice(value, options, name):
    if value not in options:
        raise Problem(f'{name} 的取值无效')
    return value
