import argparse
from pathlib import Path

from . import demo, httpd
from .database import Database


def main():
    parser = argparse.ArgumentParser(description='纸样修复批签台（本机工作站）')
    parser.add_argument('--db', type=Path, default=Path('instance/workbench.sqlite3'))
    parser.add_argument('--port', type=int, default=8031)
    parser.add_argument('--demo', action='store_true', help='仅在空库中载入合成演练数据')
    args = parser.parse_args()
    args.db.parent.mkdir(parents=True, exist_ok=True)
    database = Database(args.db)
    if args.demo:
        demo.load(database)
    with httpd.server(database, args.port) as http:
        print(f'纸样修复批签台 http://127.0.0.1:{http.server_address[1]}', flush=True)
        try:
            http.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
