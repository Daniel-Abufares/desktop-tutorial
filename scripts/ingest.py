"""Parse everything in inbox/ into data/transactions.csv, deduplicated.

Refuses to touch a source whose calibration is not verified -- a wrong sign
direction silently inverts the whole report, so it is better to stop.
"""

from __future__ import annotations

import glob
import os
import sys

from common import (DATA_DIR, INBOX_DIR, TRANSACTIONS_CSV, die, load_yaml,
                    normalise_merchant, parse_amount, parse_date, read_rows,
                    txn_id, write_transactions)

SUPPORTED = (".xlsx", ".xlsm", ".csv", ".txt", ".tsv")


def resolve_column(header, candidates):
    """Find the index of the first header cell matching any candidate name."""
    if not candidates:
        return None
    for cand in candidates:
        for idx, cell in enumerate(header):
            if cell.strip() == cand:
                return idx
    for cand in candidates:                      # fall back to substring
        for idx, cell in enumerate(header):
            if cand in cell:
                return idx
    return None


def find_header_row(rows, fmt):
    if fmt.get("header_row") is not None:
        return fmt["header_row"]
    date_names = fmt["columns"].get("date") or []
    for i, row in enumerate(rows[:30]):
        joined = " ".join(row)
        if any(n in joined for n in date_names):
            return i
    return 0


def pick_account(source_key, source_cfg, path, rows):
    """Decide which card a file belongs to."""
    accounts = source_cfg.get("accounts") or []
    if len(accounts) == 1:
        return accounts[0]

    fname = os.path.basename(path)
    blob = " ".join(" ".join(r) for r in rows[:15])

    for acct in accounts:
        match = acct.get("match") or {}
        for frag in match.get("filename_contains") or []:
            if str(frag) in fname:
                return acct
        for frag in match.get("content_contains") or []:
            if str(frag) in blob:
                return acct

    die(f"לא הצלחתי לקבוע לאיזה כרטיס שייך הקובץ {fname!r} במקור {source_key!r}.\n"
        f"  הוסף filename_contains לחשבון המתאים ב-config/parsers.yaml.")


def apply_sign(amount, mode):
    """Convert a raw amount to the internal convention (expense negative)."""
    if amount is None:
        return None
    if mode == "expense_positive":
        return -amount
    if mode == "expense_negative":
        return amount
    raise ValueError(f"unknown amount_sign: {mode}")


def parse_file(path, source_key, source_cfg):
    rows = read_rows(path)
    if not rows:
        return []

    fmt = source_cfg["format"]
    cols = fmt["columns"]
    acct = pick_account(source_key, source_cfg, path, rows)

    hdr_idx = find_header_row(rows, fmt)
    header = rows[hdr_idx]
    body = rows[hdr_idx + 1:]

    d_idx = resolve_column(header, cols.get("date"))
    m_idx = resolve_column(header, cols.get("merchant"))
    a_idx = resolve_column(header, cols.get("amount"))
    cur_idx = resolve_column(header, cols.get("currency"))
    note_idx = resolve_column(header, cols.get("notes"))

    sign_mode = fmt.get("amount_sign")
    debit_idx = credit_idx = None
    if sign_mode == "two_columns":
        debit_idx = resolve_column(header, fmt.get("debit_column"))
        credit_idx = resolve_column(header, fmt.get("credit_column"))
        if debit_idx is None and credit_idx is None:
            die(f"{path}: amount_sign=two_columns אבל לא נמצאו עמודות חובה/זכות.")
    elif a_idx is None:
        die(f"{path}: לא נמצאה עמודת סכום. בדוק את columns.amount ב-parsers.yaml.")

    if d_idx is None:
        die(f"{path}: לא נמצאה עמודת תאריך. בדוק את columns.date ב-parsers.yaml.")

    skip_frags = fmt.get("skip_rows_containing") or []
    date_formats = fmt.get("date_formats") or []
    out = []

    for row in body:
        if not any(c for c in row):
            continue
        joined = " ".join(row)
        if any(frag and frag in joined for frag in skip_frags):
            continue
        if d_idx >= len(row):
            continue

        date = parse_date(row[d_idx], date_formats)
        if not date:
            continue                              # footers, blanks, sub-headers

        if sign_mode == "two_columns":
            debit = parse_amount(row[debit_idx]) if debit_idx is not None and debit_idx < len(row) else None
            credit = parse_amount(row[credit_idx]) if credit_idx is not None and credit_idx < len(row) else None
            if debit:
                amount = -abs(debit)
            elif credit:
                amount = abs(credit)
            else:
                continue
        else:
            raw = parse_amount(row[a_idx]) if a_idx < len(row) else None
            if raw is None:
                continue
            amount = apply_sign(raw, sign_mode)

        if amount == 0:
            continue

        merchant = row[m_idx] if m_idx is not None and m_idx < len(row) else ""
        merchant = merchant or "(ללא שם)"
        norm = normalise_merchant(merchant)

        out.append({
            "txn_id": txn_id(date, amount, norm, acct["id"]),
            "date": date,
            "account": acct["id"],
            "account_label": acct.get("label", acct["id"]),
            "merchant": merchant,
            "merchant_norm": norm,
            "amount": round(amount, 2),
            "currency": (row[cur_idx] if cur_idx is not None and cur_idx < len(row) else "") or "ILS",
            "category": "",
            "notes": (row[note_idx] if note_idx is not None and note_idx < len(row) else ""),
            "source_file": os.path.relpath(path, os.path.dirname(INBOX_DIR)),
        })

    return out


def main(argv):
    parsers = load_yaml("parsers.yaml")
    sources = parsers.get("sources") or {}

    all_rows = []
    seen = set()
    dupes = 0
    per_source = {}

    found_any = False
    for source_key, source_cfg in sources.items():
        src_dir = os.path.join(INBOX_DIR, source_key)
        if not os.path.isdir(src_dir):
            continue
        files = [p for p in sorted(glob.glob(os.path.join(src_dir, "*")))
                 if os.path.splitext(p)[1].lower() in SUPPORTED]
        if not files:
            continue
        found_any = True

        calib = source_cfg.get("calibration") or {}
        if not calib.get("verified"):
            die(f"המקור {source_key!r} לא מכויל.\n"
                f"  יש בו {len(files)} קבצים, אבל calibration.verified=false.\n"
                f"  הרץ:  python3 scripts/detect.py {files[0]}\n"
                f"  אמת את כיוון הסימן, ואז סמן verified: true ב-config/parsers.yaml.")

        for path in files:
            rows = parse_file(path, source_key, source_cfg)
            kept = 0
            for r in rows:
                if r["txn_id"] in seen:
                    dupes += 1
                    continue
                seen.add(r["txn_id"])
                all_rows.append(r)
                kept += 1
            per_source[source_key] = per_source.get(source_key, 0) + kept
            print(f"  {os.path.relpath(path, INBOX_DIR):45} {kept:5} תנועות")

    if not found_any:
        print("\n  לא נמצאו קבצים ב-inbox/. שים דפי אשראי/בנק בתוך inbox/<מקור>/ והרץ שוב.")
        return 1

    write_transactions(all_rows)

    print(f"\n  סה\"כ {len(all_rows)} תנועות  ({dupes} כפילויות הוסרו)")
    for k, v in per_source.items():
        print(f"    {k:10} {v}")
    print(f"  נכתב ל-{os.path.relpath(TRANSACTIONS_CSV, os.path.dirname(DATA_DIR))}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    sys.exit(main(sys.argv[1:]))
