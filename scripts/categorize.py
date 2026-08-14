"""Assign a category to every transaction, in place."""

from __future__ import annotations

import os
import sys
from collections import Counter

from common import (TRANSACTIONS_CSV, load_yaml, read_transactions,
                    write_transactions)

# Below this, an unknown merchant is not worth asking the user about.
LARGE_UNKNOWN = 500.0


def build_rules(cfg):
    rules = []
    for cat in cfg.get("categories") or []:
        name = cat["name"]
        for kw in cat.get("keywords") or []:
            rules.append((str(kw).lower(), name))
    return rules


def classify(row, rules, fallback):
    hay = f"{row.get('merchant_norm','')} {row.get('merchant','')} {row.get('notes','')}".lower()
    for kw, name in rules:
        if kw in hay:
            return name
    # An unmatched credit is almost always income of some kind.
    if row["amount"] > 0:
        return "הכנסה"
    return fallback


def main(path=None):
    cfg = load_yaml("categories.yaml")
    rules = build_rules(cfg)
    fallback = cfg.get("fallback", "לא מסווג")

    rows = read_transactions(path)
    if not rows:
        print("  אין תנועות לסווג.")
        return 1

    for r in rows:
        r["category"] = classify(r, rules, fallback)

    write_transactions(rows, path)

    counts = Counter(r["category"] for r in rows)
    print(f"  סווגו {len(rows)} תנועות ל-{len(counts)} קטגוריות")

    unknown = [r for r in rows if r["category"] == fallback]
    if unknown:
        pct = 100.0 * len(unknown) / len(rows)
        print(f"  לא מסווג: {len(unknown)} ({pct:.1f}%)")

        big = {}
        for r in unknown:
            if abs(r["amount"]) >= LARGE_UNKNOWN:
                big[r["merchant"]] = big.get(r["merchant"], 0) + abs(r["amount"])
        if big:
            print("\n  בתי עסק גדולים שלא זוהו — שווה להוסיף ל-config/categories.yaml:")
            for merch, total in sorted(big.items(), key=lambda x: -x[1])[:10]:
                print(f"    {merch[:40]:40} {total:>12,.0f} ₪")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    sys.exit(main())
