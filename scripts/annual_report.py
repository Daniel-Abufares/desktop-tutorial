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

from common import REPORTS_DIR, load_ledger, month_he, month_key
from render import card, chart_card, esc, head, money, money_html, page, table, tiles, trend

NAV_MONTHS = 6
ACCENT_INCOME = "#1baf7a"
ACCENT_EXPENSE = "#eb6834"
ACCENT_NET = "#2a78d6"


def year_slice(ledger: pd.DataFrame, year: str) -> pd.DataFrame:
    return ledger[ledger["year"] == year]


def totals(df: pd.DataFrame) -> tuple[float, float, float]:
    income = float(df[df["amount"] > 0]["amount"].sum())
    expense = float(-df[df["amount"] < 0]["amount"].sum())
    return income, expense, income - expense


def nav_for(year: str, all_months: list[str], all_years: list[str]) -> list[tuple[str, str, bool]]:
    recent = all_months[-NAV_MONTHS:]
    links = [
        (f"{month_he(m, with_year=False)} {m[2:4]}", f"../../{m}/dashboard.html", False)
        for m in recent
    ]
    if all_years:
        links.append(("|", "", False))
        for other in all_years[-2:]:
            links.append(
                (f"שנתי {other}", f"../{other}/annual-report.html", other == year)
            )
    return links


def build_year(ledger: pd.DataFrame, year: str, all_months: list[str], all_years: list[str]) -> dict:
    df = year_slice(ledger, year)
    income, expense, net = totals(df)

    previous = str(int(year) - 1)
    prev_df = year_slice(ledger, previous)
    has_previous = not prev_df.empty

    months = []
    for month in sorted(df["month"].unique()):
        month_df = df[df["month"] == month]
        m_income, m_expense, _ = totals(month_df)
        months.append((month_he(month, with_year=False), m_income, m_expense))

    by_category = [
        (str(k), float(v))
        for k, v in df[df["amount"] < 0]
        .groupby("category")["amount"]
        .sum()
        .abs()
        .sort_values(ascending=False)
        .items()
    ]
    by_account = [
        (str(k), float(v))
        for k, v in df[df["amount"] < 0]
        .groupby("account")["amount"]
        .sum()
        .abs()
        .sort_values(ascending=False)
        .items()
    ]

    active_months = len(months)
    body = [
        head(
            f"דוח שנתי — {year}",
            f"{len(df)} תנועות · {active_months} חודשים פעילים",
        ),
        tiles(
            [
                {
                    "label": "הכנסות",
                    "amount": income,
                    "cls": "pos",
                    "accent": ACCENT_INCOME,
                    "note": f"ממוצע חודשי: {money_html(income / active_months)}"
                    if active_months
                    else "",
                },
                {
                    "label": "הוצאות",
                    "amount": expense,
                    "cls": "neg",
                    "accent": ACCENT_EXPENSE,
                    "note": f"ממוצע חודשי: {money_html(expense / active_months)}"
                    if active_months
                    else "",
                },
                {
                    "label": "נטו",
                    "amount": net,
                    "cls": "pos" if net >= 0 else "neg",
                    "accent": ACCENT_NET,
                    "note": f"ממוצע חודשי: {money_html(net / active_months)}"
                    if active_months
                    else "",
                },
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
            rows.append([esc(label), money_html(now), money_html(before), change])
        body.append(card(f"השוואה ל-{previous}", table([" ", year, previous, "שינוי"], rows)))

    body.append(card("מגמה חודשית", trend(months)))
    body.append(chart_card("פילוח קטגוריות שנתי", by_category, unit="הוצאה"))
    body.append(chart_card("הוצאות לפי חשבון/כרטיס", by_account, unit="הוצאה"))

    out_dir = REPORTS_DIR / "annual" / year
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "annual-report.html"
    path.write_text(
        page(f"דוח שנתי {year}", "\n".join(body), nav_for(year, all_months, all_years)),
        encoding="utf-8",
    )

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

    all_months = sorted(ledger["month"].unique())
    years = sorted(ledger["year"].unique())
    targets = years if args.all else [args.year or years[-1]]

    for year in targets:
        if year not in years:
            print(f"אין תנועות לשנת {year}.")
            continue
        result = build_year(ledger, year, all_months, years)
        print(
            f"✓ {year}: הכנסות {money(result['income'])} | "
            f"הוצאות {money(result['expense'])} | נטו {money(result['net'])}"
        )
        print(f"  {result['path'].relative_to(REPORTS_DIR.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
