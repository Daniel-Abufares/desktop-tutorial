#!/usr/bin/env python3
"""בניית הדשבורד והסיכום החודשי מתוך data/transactions.csv.

    python3 scripts/build_dashboard.py [--month YYYY-MM] [--all]

ברירת מחדל: החודש האחרון שקיים ביומן.
מפיק reports/<YYYY-MM>/dashboard.html + summary.md, כולל זיהוי חריגות
מול הממוצע ההיסטורי (עד 6 חודשים אחורה, דגל מעל 30%).
"""

from __future__ import annotations

import argparse
import sys

import pandas as pd

from common import REPORTS_DIR, load_ledger, month_key
from render import bars, card, esc, money, page, table, tiles

ANOMALY_THRESHOLD = 0.30
HISTORY_MONTHS = 6
MIN_HISTORY = 2
MIN_AMOUNT = 100.0  # מתחת לזה סטייה באחוזים היא רעש


def expenses_by(df: pd.DataFrame, column: str) -> list[tuple[str, float]]:
    spend = df[df["amount"] < 0].groupby(column)["amount"].sum().abs()
    return [(str(k), float(v)) for k, v in spend.sort_values(ascending=False).items()]


def find_anomalies(ledger: pd.DataFrame, month: str) -> list[dict]:
    """משווה כל קטגוריה בחודש הנוכחי לממוצע ההיסטורי שלה."""
    months = sorted(m for m in ledger["month"].dropna().unique() if m < month)
    history_months = months[-HISTORY_MONTHS:]
    if len(history_months) < MIN_HISTORY:
        return []

    spend = (
        ledger[ledger["amount"] < 0]
        .groupby(["month", "category"])["amount"]
        .sum()
        .abs()
        .reset_index()
    )
    current = spend[spend["month"] == month].set_index("category")["amount"]
    past = spend[spend["month"].isin(history_months)]

    results = []
    for category in current.index:
        rows = past[past["category"] == category]
        if len(rows) < MIN_HISTORY:
            continue
        # ממוצע על פני כל חודשי ההיסטוריה, כולל חודשים ללא הוצאה בקטגוריה
        average = rows["amount"].sum() / len(history_months)
        now = float(current[category])
        if average <= 0 or max(now, average) < MIN_AMOUNT:
            continue
        delta = (now - average) / average
        if abs(delta) >= ANOMALY_THRESHOLD:
            results.append(
                {
                    "category": category,
                    "current": now,
                    "average": average,
                    "delta": delta,
                    "months": len(history_months),
                }
            )
    return sorted(results, key=lambda r: abs(r["delta"]), reverse=True)


def build_month(ledger: pd.DataFrame, month: str) -> dict:
    month_df = ledger[ledger["month"] == month]
    income = float(month_df[month_df["amount"] > 0]["amount"].sum())
    expense = float(-month_df[month_df["amount"] < 0]["amount"].sum())
    net = income - expense
    anomalies = find_anomalies(ledger, month)

    by_category = expenses_by(month_df, "category")
    by_account = expenses_by(month_df, "account")
    top = (
        month_df[month_df["amount"] < 0]
        .nsmallest(12, "amount")[["date", "description", "account", "amount"]]
        .values.tolist()
    )

    body = [
        f"<h1>דשבורד חודשי — {esc(month)}</h1>",
        f'<p class="sub">{len(month_df)} תנועות · '
        f'{len(month_df["account"].unique())} חשבונות</p>',
        tiles(
            [
                ("הכנסות", money(income), "pos", ""),
                ("הוצאות", money(expense), "neg", ""),
                (
                    "נטו",
                    money(net),
                    "pos" if net >= 0 else "neg",
                    "עודף" if net >= 0 else "גירעון",
                ),
            ]
        ),
    ]

    if anomalies:
        rows = []
        for item in anomalies:
            direction = "up" if item["delta"] > 0 else "down"
            arrow = "▲" if item["delta"] > 0 else "▼"
            word = "מעל" if item["delta"] > 0 else "מתחת"
            rows.append(
                [
                    esc(item["category"]),
                    money(item["current"]),
                    money(item["average"]),
                    f'<span class="flag {direction}">{arrow} {abs(item["delta"]) * 100:.0f}% {word} לממוצע</span>',
                ]
            )
        body.append(
            card(
                "חריגות מול הממוצע ההיסטורי",
                table(["קטגוריה", "החודש", "ממוצע", "סטייה"], rows),
            )
        )

    body.append(card("הוצאות לפי קטגוריה", bars(by_category)))
    body.append(card("הוצאות לפי חשבון/כרטיס", bars(by_account)))
    body.append(
        card(
            "התנועות הגדולות בחודש",
            table(
                ["תאריך", "תיאור", "חשבון", "סכום"],
                [
                    [esc(d), esc(desc), esc(acct), money(abs(amt))]
                    for d, desc, acct, amt in top
                ],
                numeric_from=3,
            ),
        )
    )

    out_dir = REPORTS_DIR / month
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "dashboard.html").write_text(
        page(f"דשבורד {month}", "\n".join(body)), encoding="utf-8"
    )

    lines = [
        f"# סיכום {month}",
        "",
        f"- תנועות: {len(month_df)}",
        f"- הכנסות: {money(income)}",
        f"- הוצאות: {money(expense)}",
        f"- נטו: {money(net)}",
        "",
        "## הוצאות לפי קטגוריה",
    ]
    lines += [f"- {name}: {money(value)}" for name, value in by_category]
    lines += ["", "## הוצאות לפי חשבון"]
    lines += [f"- {name}: {money(value)}" for name, value in by_account]
    lines += ["", "## חריגות"]
    if anomalies:
        for item in anomalies:
            word = "מעל" if item["delta"] > 0 else "מתחת"
            lines.append(
                f"- {item['category']}: {money(item['current'])} — "
                f"{abs(item['delta']) * 100:.0f}% {word} לממוצע ({money(item['average'])})"
            )
    else:
        lines.append("- לא זוהו חריגות משמעותיות.")
    (out_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {
        "month": month,
        "income": income,
        "expense": expense,
        "net": net,
        "anomalies": anomalies,
        "path": out_dir / "dashboard.html",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="בניית דשבורד חודשי")
    parser.add_argument("--month", help="YYYY-MM (ברירת מחדל: החודש האחרון ביומן)")
    parser.add_argument("--all", action="store_true", help="בנה מחדש את כל החודשים")
    args = parser.parse_args()

    ledger = load_ledger()
    if ledger.empty:
        print("data/transactions.csv ריק — אין מה לבנות.")
        return 0

    ledger["amount"] = pd.to_numeric(ledger["amount"], errors="coerce").fillna(0.0)
    ledger["month"] = month_key(ledger["date"])
    ledger = ledger[ledger["month"].notna()]

    months = sorted(ledger["month"].unique())
    targets = months if args.all else [args.month or months[-1]]

    for month in targets:
        if month not in months:
            print(f"אין תנועות לחודש {month}.")
            continue
        result = build_month(ledger, month)
        print(
            f"✓ {month}: הכנסות {money(result['income'])} | "
            f"הוצאות {money(result['expense'])} | נטו {money(result['net'])}"
            + (f" | {len(result['anomalies'])} חריגות" if result["anomalies"] else "")
        )
        print(f"  {result['path'].relative_to(REPORTS_DIR.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
