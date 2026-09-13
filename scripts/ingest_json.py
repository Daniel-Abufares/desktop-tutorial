#!/usr/bin/env python3
"""קליטת תנועות מנורמלות (JSON) אל היומן המרכזי — נקודת נחיתה גנרית לכל
מקור אוטומטי (אגרגטור בנקאות פתוחה, API של בנק, או ייצוא ממערכת אחרת).

    python3 scripts/ingest_json.py <path.json> [--dry-run]
    cat records.json | python3 scripts/ingest_json.py -

הקלט: מערך רשומות בסכימה שבשליטתנו (לא הפורמט הגולמי של ה-API — את המיפוי
מהקונקטור לסכימה הזו עושה Claude Code בזמן הסנכרון, אחרי אימות כיוון הסימן):

    [{"date": "2026-08-01",          # YYYY-MM-DD
      "description": "שופרסל דיל",
      "amount": -123.45,             # שלילי = הוצאה, חיובי = הכנסה (כבר מנורמל!)
      "account": "onezero",
      "source": "onezero",           # מפתח דדופ — עקבי עם מסלול ה-CSV של אותו מקור
      "currency": "ILS",             # אופציונלי
      "category_hint": "מזון"}]      # אופציונלי — קטגוריה מהקונקטור, גיבוי בלבד

סדר הסיווג: מילות המפתח של categories.yaml קודמות (בשליטת המשתמש); אם אין
התאמה — category_hint; אם גם הוא ריק — כללי ברירת המחדל של הסכום.

חשוב: source חייב להיות זהה לזה של מסלול ה-CSV של אותו מקור, כדי ש-raw_hash
ידדפ תנועות שמגיעות משני הצינורות.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from common import (
    SCHEMA,
    UNCLASSIFIED,
    categorize,
    load_categories,
    load_ledger,
    row_hash,
    save_ledger,
)

REQUIRED = ("date", "description", "amount", "account", "source")


def normalize(records: list[dict]) -> tuple[list[dict], list[str]]:
    categories = load_categories()
    rows, errors = [], []
    for i, rec in enumerate(records):
        missing = [k for k in REQUIRED if rec.get(k) in (None, "")]
        if missing:
            errors.append(f"רשומה {i}: חסרים שדות {missing}")
            continue
        try:
            amount = round(float(rec["amount"]), 2)
        except (TypeError, ValueError):
            errors.append(f"רשומה {i}: amount לא מספרי ({rec['amount']!r})")
            continue
        date = str(rec["date"])[:10]
        if pd.isna(pd.to_datetime(date, format="%Y-%m-%d", errors="coerce")):
            errors.append(f"רשומה {i}: תאריך לא תקין ({rec['date']!r})")
            continue
        if amount == 0:
            continue

        description = str(rec["description"]).strip()
        category = categorize(description, amount, categories)
        hint = str(rec.get("category_hint") or "").strip()
        if category in (UNCLASSIFIED, "אחר") and hint:
            category = hint

        rows.append(
            {
                "date": date,
                "source": str(rec["source"]),
                "account": str(rec["account"]),
                "description": description,
                "amount": amount,
                "currency": str(rec.get("currency") or "ILS"),
                "category": category,
                "raw_hash": row_hash(date, description, amount, str(rec["source"])),
            }
        )
    return rows, errors


def main() -> int:
    parser = argparse.ArgumentParser(description="קליטת תנועות מנורמלות מ-JSON")
    parser.add_argument("path", help="קובץ JSON, או - לקריאה מ-stdin")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    raw = sys.stdin.read() if args.path == "-" else Path(args.path).read_text(encoding="utf-8")
    try:
        records = json.loads(raw)
    except ValueError as exc:
        raise SystemExit(f"JSON לא תקין: {exc}")
    if not isinstance(records, list):
        raise SystemExit("הקלט חייב להיות מערך רשומות.")

    rows, errors = normalize(records)
    for err in errors:
        print(f"  ✗ {err}", file=sys.stderr)

    ledger = load_ledger()
    known = set(ledger["raw_hash"].dropna().astype(str))
    fresh, duplicates, seen = [], 0, set()
    for row in rows:
        if row["raw_hash"] in known or row["raw_hash"] in seen:
            duplicates += 1
            continue
        seen.add(row["raw_hash"])
        fresh.append(row)

    income = sum(r["amount"] for r in fresh if r["amount"] > 0)
    expense = sum(-r["amount"] for r in fresh if r["amount"] < 0)
    unclassified = [r for r in fresh if r["category"] == UNCLASSIFIED]

    print(f"נקראו {len(records)} רשומות | תקינות: {len(rows)} | שגויות: {len(errors)}")
    print(f"חדשות: {len(fresh)} | כפילויות שדולגו: {duplicates}")
    print(f"הכנסות: {income:,.2f} ₪ | הוצאות: {expense:,.2f} ₪")
    if unclassified:
        print(f"⚠ {len(unclassified)} תנועות מעל 300 ₪ ללא קטגוריה — דורשות סיווג:")
        for row in sorted(unclassified, key=lambda r: r["amount"])[:20]:
            print(f"   {row['date']}  {abs(row['amount']):>9,.2f} ₪  {row['description']}")

    if args.dry_run:
        print("(dry-run — לא נכתב דבר)")
        return 0
    if fresh:
        combined = pd.concat([ledger, pd.DataFrame(fresh)[SCHEMA]], ignore_index=True)
        save_ledger(combined)
        print(f"✓ נוספו ל-data/transactions.csv (סה\"כ ביומן: {len(combined)})")
    return 1 if errors and not fresh else 0


if __name__ == "__main__":
    sys.exit(main())
