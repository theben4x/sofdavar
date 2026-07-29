"""הרצת שרת הפיתוח.

    python run.py            # http://127.0.0.1:5000
    python run.py --port 8000
"""

from __future__ import annotations

import argparse

from app import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="סוף דבר — שרת פיתוח")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    create_app().run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
