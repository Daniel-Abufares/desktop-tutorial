"""Generate synthetic transactions so the dashboard can be seen working.

These are invented numbers, not anyone's real spending. Used by
`run_all.py --demo` only.
"""

from __future__ import annotations

import os
import random
import sys
from datetime import date, timedelta

from common import normalise_merchant, txn_id, write_transactions

SEED = 20260814

ACCOUNTS = [
    ("cal-4471", "כאל ‏4471"),
    ("max-8823", "מקס ‏8823"),
    ("bank-main", "עו\"ש"),
]

# merchant, low, high, rough charges per month
MERCHANTS = [
    ("שופרסל דיל", 90, 420, 5),
    ("רמי לוי", 120, 380, 2),
    ("ארומה תל אביב", 18, 62, 6),
    ("wolt", 55, 140, 4),
    ("פז יעלים", 180, 340, 3),
    ("סלופארק", 8, 40, 5),
    ("כביש 6", 22, 95, 2),
    ("סופר פארם", 35, 190, 2),
    ("hot טלוויזיה ואינטרנט", 219, 219, 1),
    ("פרטנר סלולר", 89, 89, 1),
    ("חברת החשמל", 210, 460, 1),
    ("netflix.com", 54, 54, 1),
    ("spotify", 21, 21, 1),
    ("castro", 120, 480, 1),
    ("aliexpress", 30, 210, 2),
    ("ביט העברה", 50, 300, 3),
    ("איקאה נתניה", 200, 900, 1),
]


def main():
    rng = random.Random(SEED)
    today = date(2026, 8, 14)
    start = date(2026, 1, 1)

    rows = []
    d = start
    while d <= today:
        month_start = d
        for merch, lo, hi, freq in MERCHANTS:
            n = max(0, int(rng.gauss(freq, freq * 0.35)))
            for _ in range(n):
                day = month_start + timedelta(days=rng.randint(0, 27))
                if day > today:
                    continue
                amt = -round(rng.uniform(lo, hi), 2)
                acct, label = rng.choice(ACCOUNTS)
                norm = normalise_merchant(merch)
                rows.append({
                    "txn_id": txn_id(day.isoformat(), amt, norm, acct),
                    "date": day.isoformat(), "account": acct, "account_label": label,
                    "merchant": merch, "merchant_norm": norm, "amount": amt,
                    "currency": "ILS", "category": "", "notes": "",
                    "source_file": "samples/synthetic",
                })

        # salary
        pay = month_start.replace(day=min(10, 28))
        if pay <= today:
            amt = round(rng.uniform(11800, 12600), 2)
            norm = normalise_merchant("העברת משכורת")
            rows.append({
                "txn_id": txn_id(pay.isoformat(), amt, norm, "bank-main"),
                "date": pay.isoformat(), "account": "bank-main", "account_label": "עו\"ש",
                "merchant": "העברת משכורת", "merchant_norm": norm, "amount": amt,
                "currency": "ILS", "category": "", "notes": "",
                "source_file": "samples/synthetic",
            })

        d = (month_start.replace(day=28) + timedelta(days=7)).replace(day=1)

    # plant a couple of detectable anomalies in the latest month
    norm = normalise_merchant("מלון ים המלח")
    for offset in (0, 2):                       # same amount twice -> double charge
        day = date(2026, 8, 3 + offset)
        rows.append({
            "txn_id": txn_id(day.isoformat(), -2450.0, norm, "cal-4471"),
            "date": day.isoformat(), "account": "cal-4471", "account_label": "כאל ‏4471",
            "merchant": "מלון ים המלח", "merchant_norm": norm, "amount": -2450.0,
            "currency": "ILS", "category": "", "notes": "", "source_file": "samples/synthetic",
        })

    # dedupe identical ids, then write
    seen, out = set(), []
    for r in rows:
        if r["txn_id"] in seen:
            continue
        seen.add(r["txn_id"])
        out.append(r)

    write_transactions(out)
    print(f"  נוצרו {len(out)} תנועות דוגמה ({start} עד {today})")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    sys.exit(main())
