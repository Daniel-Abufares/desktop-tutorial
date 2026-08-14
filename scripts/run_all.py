"""Run the whole pipeline: ingest -> categorise -> report.

    python3 scripts/run_all.py           process inbox/
    python3 scripts/run_all.py --demo    process samples/ instead
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import categorize            # noqa: E402
import ingest                # noqa: E402
import report                # noqa: E402
from common import ensure_dirs   # noqa: E402


def step(n, total, title):
    print(f"\n[{n}/{total}] {title}")
    print("-" * 60)


def main():
    demo = "--demo" in sys.argv
    ensure_dirs()

    if demo:
        step(1, 3, "יצירת נתוני דוגמה")
        import make_samples
        if make_samples.main() != 0:
            return 1
    else:
        step(1, 3, "קליטת קבצים מ-inbox/")
        if ingest.main([]) != 0:
            return 1

    step(2, 3, "סיווג קטגוריות")
    if categorize.main() != 0:
        return 1

    step(3, 3, "הפקת דוחות")
    if report.main(demo=demo) != 0:
        return 1

    print("\nהסתיים.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
