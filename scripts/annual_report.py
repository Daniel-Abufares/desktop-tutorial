#!/usr/bin/env python3
"""דוח שנתי: מגמה חודשית, פילוח קטגוריות שנתי, והשוואה לשנה קודמת.

    python3 scripts/annual_report.py [--year YYYY] [--all]

ברירת מחדל: השנה האחרונה שקיימת ביומן. זול לחשב — מומלץ להריץ מחדש
בסוף כל עדכון חודשי.
"""

from __future__ import annotations

import argparse
import sys

import pandas as pd

from common import REPORTS_DIR, load_ledger, month_key
from render import bars, card, esc, money, page, table, tiles, trend


def year_slice(ledger: pd.DataFrame, year: str) -> pd.DataFrame:
    return ledger[ledger["year"] == year]


def totals(df: pd.DataFrame) -> tuple[float, float, float]:
    income = float(df[df["amount"] > 0]["amount"].sum())
    expense = float(-df[df["amount"] < 0]["amount"].sum())
    return income, expense, income - expense


def build_year(ledger: pd.DataFrame, year: str) -> dict:
    df = year_slice(ledger, year)
    income, expense, net = totals(df)

    previous = str(int(year) - 1)
    prev_df = year_slice(ledger, previous)
    has_previous = not prev_df.empty

    months = []
    for month in sorted(df["month"].unique()):
        month_df = df[df["month"] == month]
        m_income, m_expense, _ = totals(month_df)
        months.append((month, m_income, m_expense))

    by_category = (
        df[df["amount"] < 0].groupby("category")["amount"].sum().abs().sort_values(ascending=False)
    )
    by_account = (
        df[df["amount"] < 0].groupby("account")["amount"].sum().abs().sort_values(ascending=False)
    )

    active_months = len(months)
    note = f"ממוצע חודשי: {money(expense / active_months)}" if active_months else ""

    body = [
        f"<h1>דוח שנתי — {esc(year)}</h1>",
        f'<p class="sub">{len(df)} תנועות · {active_months} חודשים פעילים</p>',
        tiles(
            [
                ("הכנסות", money(income), "pos", ""),
                ("הוצאות", money(expense), "neg", note),
                ("נטו", money(net), "pos" if net >= 0 else "neg", ""),
            ]
        ),
    ]

    if has_previous:
        p_income, p_expense, p_net = totals(prev_df)
        rows = []
        # rising_is_good: בהכנסות ובנטו עלייה היא חיובית, בהוצאות עלייה היא שלילית.
        for label, now, before, rising_is_good in (
            ("הכנסות", income, p_income, True),
            ("הוצאות", expense, p_expense, False),
            ("נטו", net, p_net, True),
        ):
            delta = (now - before) / abs(before) * 100 if before else 0.0
            if not before:
                change = "—"
            elif abs(delta) < 0.5:
                change = '<span class="flag">≈ ללא שינוי</span>'
            else:
                arrow = "▲" if delta > 0 else "▼"
                improved = (delta > 0) == rising_is_good
                change = (
                    f'<span class="flag {"down" if improved else "up"}">'
                    f"{arrow} {abs(delta):.0f}%</span>"
                )
            rows.append([esc(label), money(now), money(before), change])
        body.append(
            card(
                f"השוואה ל-{previous}",
                table([" ", year, previous, "שינוי"], rows),
            )
        )

    body.append(card("מגמה חודשית", trend(months)))
    body.append(
        card(
            "פילוח קטגוריות שנתי",
            bars([(str(k), float(v)) for k, v in by_category.items()]),
        )
    )
    body.append(
        card(
            "הוצאות לפי חשבון/כרטיס",
            bars([(str(k), float(v)) for k, v in by_account.items()]),
        )
    )

    out_dir = REPORTS_DIR / "annual" / year
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "annual-report.html"
    path.write_text(page(f"דוח שנתי {year}", "\n".join(body)), encoding="utf-8")

    return {"year": year, "income": income, "expense": expense, "net": net, "path": path}


def main() -> int:
    parser = argparse.ArgumentParser(description="בניית דוח שנתי")
    parser.add_argument("--year", help="YYYY (ברירת מחדל: השנה האחרונה ביומן)")
    parser.add_argument("--all", action="store_true", help="בנה מחדש את כל השנים")
    args = parser.parse_args()

    ledger = load_ledger()
    if ledger.empty:
        print("data/transactions.csv ריק — אין מה לבנות.")
        return 0

    ledger["amount"] = pd.to_numeric(ledger["amount"], errors="coerce").fillna(0.0)
    ledger["month"] = month_key(ledger["date"])
    ledger = ledger[ledger["month"].notna()].copy()
    ledger["year"] = ledger["month"].str[:4]

    years = sorted(ledger["year"].unique())
    targets = years if args.all else [args.year or years[-1]]

    for year in targets:
        if year not in years:
            print(f"אין תנועות לשנת {year}.")
            continue
        result = build_year(ledger, year)
        print(
            f"✓ {year}: הכנסות {money(result['income'])} | "
            f"הוצאות {money(result['expense'])} | נטו {money(result['net'])}"
        )
        print(f"  {result['path'].relative_to(REPORTS_DIR.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
