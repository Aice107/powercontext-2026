"""Run TaskHub: python -m app --db taskhub.sqlite3 --port 8011."""

from __future__ import annotations

import argparse

from .api import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the TaskHub demo service")
    parser.add_argument("--db", default="taskhub.sqlite3")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8011)
    parser.add_argument("--no-seed", action="store_true")
    args = parser.parse_args()
    app = create_app(args.db, seed=not args.no_seed)
    app.run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
