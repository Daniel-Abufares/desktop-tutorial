#!/usr/bin/env python3
"""קליטת קובץ תנועות מיוצא אל היומן המרכזי.

    python3 scripts/ingest.py <source> <path> [--account cal-1234] [--dry-run]

<source> הוא מפתח ב-config/parsers.yaml (otzar-hahayal / onezero / cal ...).
אם אין מיפוי שמור למקור — הסקריפט נעצר עם הסבר, כדי ש-Claude Code יזהה
את המבנה ידנית ויכתוב את המיפוי לפני ההרצה.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from common import (
    SCHEMA,
    UNCLASSIFIED,
    categorize,
    load_categories,
    load_ledger,
    load_parsers,
    parse_date,
    parse_money,
    row_hash,
    save_ledger,
)


def read_raw(path: Path, mapping: dict) -> pd.DataFrame:
    """קורא csv/xlsx לפי המיפוי, כולל דילוג על שורות מטא-דאטה."""
    header_row = int(mapping.get("header_row", 0))

    if path.suffix.lower() in {".xlsx", ".xls", ".xlsm"}:
        return pd.read_excel(
            path,
            sheet_name=mapping.get("sheet", 0),
            header=header_row,
            dtype=str,
        )

    encodings = [mapping["encoding"]] if mapping.get("encoding") else [
        "utf-8-sig",
        "utf-8",
        "cp1255",
    ]
    last_error: Exception | None = None
    for encoding in encodings:
        try:
            # skip_blank_lines=False כדי ש-header_row יתייחס לשורות הפיזיות בקובץ.
            # אקספורטים ישראליים מכילים שורות ריקות בין המטא-דאטה לטבלה, ובלי זה
            # pandas מדלג עליהן לפני החלת header ומזיז את האינדקס.
            return pd.read_csv(
                path,
                header=header_row,
                dtype=str,
                encoding=encoding,
                engine="python",
                skip_blank_lines=False,
            )
        except (UnicodeDecodeError, LookupError) as exc:
            last_error = exc
    raise SystemExit(f"לא ניתן לפענח את הקידוד של {path.name}: {last_error}")


def require_column(df: pd.DataFrame, name: str, role: str) -> str:
    if name in df.columns:
        return name
    stripped = {str(c).strip(): c for c in df.columns}
    if name.strip() in stripped:
        return stripped[name.strip()]
    raise SystemExit(
        f"עמודת ה{role} '{name}' לא נמצאה בקובץ.\n"
        f"עמודות זמינות: {list(df.columns)}\n"
        "עדכן את config/parsers.yaml."
    )


def extract_amount(row, mapping: dict) -> float:
    """מחזיר סכום מנורמל: שלילי = הוצאה, חיובי = הכנסה."""
    if mapping.get("amount_debit_column") or mapping.get("amount_credit_column"):
        debit = parse_money(row.get(mapping.get("amount_debit_column")))
        credit = parse_money(row.get(mapping.get("amount_credit_column")))
        # חובה = כסף שיוצא, זכות = כסף שנכנס
        return credit - abs(debit)

    amount = parse_money(row.get(mapping["amount_column"]))
    if mapping.get("expense_positive"):
        # בקובץ הזה מספר חיובי מייצג הוצאה — הופכים לסכימה האחידה
        return -amount
    return amount


def build_rows(df: pd.DataFrame, source: str, account: str, mapping: dict) -> list[dict]:
    date_col = require_column(df, mapping["date_column"], "תאריך")
    desc_col = require_column(df, mapping["description_column"], "תיאור")

    if mapping.get("amount_column"):
        mapping = {**mapping, "amount_column": require_column(
            df, mapping["amount_column"], "סכום")}
    for key, role in (("amount_debit_column", "חובה"), ("amount_credit_column", "זכות")):
        if mapping.get(key):
            mapping = {**mapping, key: require_column(df, mapping[key], role)}

    categories = load_categories()
    currency = mapping.get("currency", "ILS")
    date_format = mapping.get("date_format")

    rows: list[dict] = []
    for _, raw in df.iterrows():
        description = str(raw.get(desc_col) or "").strip()
        if not description or description.lower() == "nan":
            continue

        date = parse_date(raw.get(date_col), date_format)
        if pd.isna(date):
            continue  # שורות סיכום/כותרת שנשארו בתוך הטבלה

        amount = extract_amount(raw, mapping)
        if amount == 0:
            continue

        date_str = date.strftime("%Y-%m-%d")
        rows.append(
            {
                "date": date_str,
                "source": source,
                "account": account,
                "description": description,
                "amount": round(amount, 2),
                "currency": currency,
                "category": categorize(description, amount, categories),
                "raw_hash": row_hash(date_str, description, amount, source),
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="קליטת קובץ תנועות ליומן המרכזי")
    parser.add_argument("source", help="מפתח מקור ב-config/parsers.yaml")
    parser.add_argument("path", help="נתיב לקובץ המיוצא")
    parser.add_argument("--account", help="שם חשבון (למשל cal-1234)")
    parser.add_argument("--dry-run", action="store_true", help="ניתוח בלי כתיבה")
    args = parser.parse_args()

    path = Path(args.path)
    if not path.exists():
        raise SystemExit(f"הקובץ לא נמצא: {path}")

    parsers = load_parsers()
    mapping = parsers.get(args.source)
    if not mapping:
        raise SystemExit(
            f"אין מיפוי שמור למקור '{args.source}' ב-config/parsers.yaml.\n"
            "יש לזהות את מבנה הקובץ ולכתוב את המיפוי לפני ההרצה "
            "(ראה את סכימת המיפוי בראש parsers.yaml)."
        )
    if not mapping.get("amount_column") and not (
        mapping.get("amount_debit_column") or mapping.get("amount_credit_column")
    ):
        raise SystemExit(
            f"המיפוי של '{args.source}' חייב להגדיר amount_column, "
            "או amount_debit_column/amount_credit_column."
        )

    account = args.account or mapping.get("account") or args.source

    df = read_raw(path, mapping)
    df.columns = [str(c).strip() for c in df.columns]
    rows = build_rows(df, args.source, account, mapping)

    if not rows:
        print(f"[{path.name}] לא נמצאו תנועות תקינות.")
        return 0

    ledger = load_ledger()
    known = set(ledger["raw_hash"].dropna().astype(str))

    fresh, duplicates = [], 0
    seen_in_file = set()
    for row in rows:
        if row["raw_hash"] in known or row["raw_hash"] in seen_in_file:
            duplicates += 1
            continue
        seen_in_file.add(row["raw_hash"])
        fresh.append(row)

    income = sum(r["amount"] for r in fresh if r["amount"] > 0)
    expense = sum(-r["amount"] for r in fresh if r["amount"] < 0)
    unclassified = [r for r in fresh if r["category"] == UNCLASSIFIED]

    print(f"[{path.name}] מקור={args.source} חשבון={account}")
    print(f"  נקראו {len(rows)} תנועות | חדשות: {len(fresh)} | כפילויות שדולגו: {duplicates}")
    print(f"  הכנסות: {income:,.2f} ₪ | הוצאות: {expense:,.2f} ₪")
    if fresh:
        dates = sorted(r["date"] for r in fresh)
        print(f"  טווח תאריכים: {dates[0]} — {dates[-1]}")

    if unclassified:
        print(f"  ⚠ {len(unclassified)} תנועות מעל 300 ₪ ללא קטגוריה — דורשות סיווג:")
        for row in sorted(unclassified, key=lambda r: r["amount"])[:20]:
            print(f"     {row['date']}  {abs(row['amount']):>9,.2f} ₪  {row['description']}")

    if args.dry_run:
        print("  (dry-run — לא נכתב דבר)")
        return 0

    if fresh:
        combined = pd.concat([ledger, pd.DataFrame(fresh)[SCHEMA]], ignore_index=True)
        save_ledger(combined)
        print(f"  ✓ נוספו ל-data/transactions.csv (סה\"כ ביומן: {len(combined)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
