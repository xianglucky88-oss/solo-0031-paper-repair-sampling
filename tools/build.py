"""Bounded syntax and local-asset contract check; no installs or generated files."""
from html.parser import HTMLParser
from pathlib import Path
import re
import shutil
import subprocess

from paperbench.demo import requests

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / 'web'


class Assets(HTMLParser):
    def handle_starttag(self, tag, raw):
        attr = dict(raw)
        if tag in ('script', 'link'):
            url = attr.get('src' if tag == 'script' else 'href', '')
            if not url.startswith('/') or not (WEB / url.lstrip('/')).is_file():
                raise SystemExit(f'页面资源未找到：{url}')


def main():
    python = sorted((ROOT / 'paperbench').glob('*.py')) + sorted((ROOT / 'tools').glob('*.py'))
    for path in python:
        compile(path.read_text(), str(path), 'exec')
    modules = sorted((WEB / 'js').glob('*.js'))
    node = shutil.which('node')
    if not node:
        raise SystemExit('构建检查需要 Node.js；运行工作台本身不需要 Node.js')
    for path in modules:
        code = path.read_text()
        subprocess.run([node, '--input-type=module', '--check'], input=code, text=True, check=True)
        for entry in re.findall(r"from\s+['\"]([^'\"]+)['\"]", code):
            if not entry.startswith('./') or not (path.parent / entry).is_file():
                raise SystemExit(f'模块引用无效：{path.name}: {entry}')
    Assets().feed((WEB / 'index.html').read_text())
    print(f'构建通过：{len(python)} Python，{len(modules)} ES modules，{len(requests())} 条样例请求')


if __name__ == '__main__':
    main()
