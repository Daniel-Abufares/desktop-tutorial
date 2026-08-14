"""Inspect a raw statement file and propose a parsers.yaml block.

    python3 scripts/detect.py inbox/cal/statement.xlsx

Prints the file structure, a guessed column mapping, and the extreme rows you
need in order to confirm the sign direction. It never writes config itself --
the mapping goes in only after you have looked at it.
"""

from __future__ import annotations

import os
import sys

from common import (die, load_yaml, looks_like_date, normalise_merchant,
                    parse_amount, parse_date, read_rows)

DATE_HINTS = ["תאריך"]
MERCHANT_HINTS = ["בית העסק", "בית עסק", "תיאור", "פרטים", "שם"]
AMOUNT_HINTS = ["סכום", "חיוב"]
DEBIT_HINTS = ["חובה", "משיכה"]
CREDIT_HINTS = ["זכות", "הפקדה", "זיכוי"]


def find_header_row(rows):
    """The header is the first row with a date-ish and an amount-ish label."""
    for i, row in enumerate(rows[:30]):
        joined = " ".join(row)
        if any(h in joined for h in DATE_HINTS) and any(h in joined for h in AMOUNT_HINTS):
            return i
    # Fall back: first row followed by a row whose first cells parse as a date.
    for i, row in enumerate(rows[:30]):
        nxt = rows[i + 1] if i + 1 < len(rows) else []
        if any(looks_like_date(c) for c in nxt[:3]):
            return i
    return 0


def match_column(header, hints):
    for idx, cell in enumerate(header):
        if any(h in cell for h in hints):
            return idx, cell
    return None, None


def main():
    if len(sys.argv) < 2:
        die("שימוש: python3 scripts/detect.py <path-to-file>")
    path = sys.argv[1]
    if not os.path.exists(path):
        die(f"קובץ לא נמצא: {path}")

    rows = read_rows(path)
    if not rows:
        die("הקובץ ריק")

    hdr_idx = find_header_row(rows)
    header = rows[hdr_idx]
    body = [r for r in rows[hdr_idx + 1:] if any(c for c in r)]

    print("=" * 68)
    print(f"קובץ: {path}")
    print(f"שורות בסך הכל: {len(rows)}   שורת כותרת מזוהה: {hdr_idx}")
    print("=" * 68)

    print("\n-- שורות ראשונות כפי שהן --")
    for i, r in enumerate(rows[:min(hdr_idx + 4, len(rows))]):
        mark = "  <== כותרת" if i == hdr_idx else ""
        print(f"  [{i}] {r}{mark}")

    print("\n-- עמודות --")
    for i, cell in enumerate(header):
        sample = next((b[i] for b in body if i < len(b) and b[i]), "")
        print(f"  [{i}] {cell!r:35} דוגמה: {sample!r}")

    d_idx, d_name = match_column(header, DATE_HINTS)
    m_idx, m_name = match_column(header, MERCHANT_HINTS)
    a_idx, a_name = match_column(header, AMOUNT_HINTS)
    debit_idx, debit_name = match_column(header, DEBIT_HINTS)
    credit_idx, credit_name = match_column(header, CREDIT_HINTS)

    print("\n-- מיפוי מוצע --")
    print(f"  date      -> [{d_idx}] {d_name!r}")
    print(f"  merchant  -> [{m_idx}] {m_name!r}")
    if debit_idx is not None and credit_idx is not None:
        print(f"  debit     -> [{debit_idx}] {debit_name!r}")
        print(f"  credit    -> [{credit_idx}] {credit_name!r}")
        print("  amount_sign: two_columns")
    else:
        print(f"  amount    -> [{a_idx}] {a_name!r}")

    if d_idx is None or (a_idx is None and debit_idx is None):
        die("לא הצלחתי לזהות עמודת תאריך או סכום. צריך מיפוי ידני ב-parsers.yaml.")

    # ---- the part that matters: sign direction -------------------------
    parsed = []
    for r in body:
        if d_idx >= len(r):
            continue
        date = parse_date(r[d_idx], [])
        if not date:
            continue
        amt_idx = a_idx if a_idx is not None else debit_idx
        if amt_idx is None or amt_idx >= len(r):
            continue
        amt = parse_amount(r[amt_idx])
        if amt is None:
            continue
        merch = r[m_idx] if m_idx is not None and m_idx < len(r) else ""
        parsed.append((date, merch, amt))

    if not parsed:
        die("לא נמצאה אף שורת תנועה תקינה.")

    negatives = sum(1 for _, _, a in parsed if a < 0)
    positives = sum(1 for _, _, a in parsed if a > 0)

    print("\n" + "=" * 68)
    print("כיול סימן — חובה לאשר לפני עיבוד")
    print("=" * 68)
    print(f"  שורות תקינות: {len(parsed)}   חיוביות: {positives}   שליליות: {negatives}")

    if debit_idx is not None and credit_idx is not None:
        guess = "two_columns"
    elif negatives == 0:
        guess = "expense_positive"
    elif positives == 0:
        guess = "expense_negative"
    else:
        # Mixed signs: the majority direction is almost always the expenses.
        guess = "expense_positive" if positives > negatives else "expense_negative"

    parsed.sort(key=lambda x: abs(x[2]), reverse=True)
    print("\n  שלוש התנועות הגדולות בקובץ:")
    for date, merch, amt in parsed[:3]:
        print(f"    {date}  {merch[:32]:32}  {amt:>12,.2f}")
    print("\n  שלוש הקטנות:")
    for date, merch, amt in parsed[-3:]:
        print(f"    {date}  {merch[:32]:32}  {amt:>12,.2f}")

    print(f"\n  ניחוש: amount_sign: {guess}")
    print("\n  >>> תסתכל על השורות למעלה. קח אחת שאתה בטוח שהיא הוצאה")
    print("      (קנייה בסופר, תדלוק, משיכה). האם הסכום שם חיובי או שלילי?")
    print("      חיובי  -> expense_positive")
    print("      שלילי  -> expense_negative")
    print("      אם הניחוש שגוי, תקן ב-parsers.yaml לפני שממשיכים.\n")

    src = os.path.basename(os.path.dirname(os.path.abspath(path)))
    print("-- בלוק להדבקה ב-config/parsers.yaml --\n")
    print(f"  {src}:")
    print(f"    display_name: \"{src}\"")
    print("    format:")
    print(f"      header_row: {hdr_idx}")
    print("      columns:")
    print(f"        date: [\"{d_name}\"]")
    print(f"        merchant: [\"{m_name}\"]")
    if debit_idx is not None and credit_idx is not None:
        print(f"        amount: []")
        print(f"      debit_column: [\"{debit_name}\"]")
        print(f"      credit_column: [\"{credit_name}\"]")
    else:
        print(f"        amount: [\"{a_name}\"]")
    print(f"      amount_sign: \"{guess}\"")
    print("    calibration:")
    print("      verified: false        # <-- שנה ל-true אחרי שאימתת את הסימן")
    print(f"      sample_row: \"{parsed[0][1][:30]} | {parsed[0][0]} | {parsed[0][2]:,.2f}\"")
    print()


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    main()
