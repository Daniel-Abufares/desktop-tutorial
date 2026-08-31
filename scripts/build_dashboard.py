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

from common import (
    REPORTS_DIR,
    load_balances,
    load_ledger,
    load_sync_status,
    month_he,
    month_key,
)
from render import (
    balances_card,
    card,
    chart_card,
    connections_strip,
    esc,
    head,
    money,
    money_html,
    page,
    searchable_table,
    table,
    tiles,
)

ANOMALY_THRESHOLD = 0.30
HISTORY_MONTHS = 6
MIN_HISTORY = 2
MIN_AMOUNT = 100.0  # מתחת לזה סטייה באחוזים היא רעש
NAV_MONTHS = 6

ACCENT_INCOME = "#1baf7a"
ACCENT_EXPENSE = "#eb6834"
ACCENT_NET = "#2a78d6"


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


def nav_for(month: str, all_months: list[str]) -> list[tuple[str, str, bool]]:
    """קישורים לחודשים האחרונים + לדוח השנתי, בנתיבים יחסיים."""
    recent = all_months[-NAV_MONTHS:]
    links = [
        (f"{month_he(m, with_year=False)} {m[2:4]}", f"../{m}/dashboard.html", m == month)
        for m in recent
    ]
    years = sorted({m[:4] for m in all_months})
    if years:
        links.append(("|", "", False))
        for year in years[-2:]:
            links.append((f"שנתי {year}", f"../annual/{year}/annual-report.html", False))
    return links


def delta_note(current: float, previous: float | None, rising_is_good: bool) -> str:
    """חיווי שינוי מול החודש הקודם — צבע לפי משמעות, לא לפי כיוון."""
    if previous is None or previous == 0:
        return ""
    change = (current - previous) / abs(previous) * 100
    if abs(change) < 0.5:
        return '<span class="flag">≈ כמו בחודש שעבר</span>'
    improved = (change > 0) == rising_is_good
    arrow = "▲" if change > 0 else "▼"
    return (
        f'<span class="flag {"down" if improved else "up"}">{arrow} {abs(change):.0f}%</span>'
        " מהחודש הקודם"
    )


def build_month(ledger: pd.DataFrame, month: str, all_months: list[str]) -> dict:
    month_df = ledger[ledger["month"] == month]
    income = float(month_df[month_df["amount"] > 0]["amount"].sum())
    expense = float(-month_df[month_df["amount"] < 0]["amount"].sum())
    net = income - expense

    index = all_months.index(month)
    previous = all_months[index - 1] if index > 0 else None
    if previous:
        prev_df = ledger[ledger["month"] == previous]
        p_income = float(prev_df[prev_df["amount"] > 0]["amount"].sum())
        p_expense = float(-prev_df[prev_df["amount"] < 0]["amount"].sum())
        p_net = p_income - p_expense
    else:
        p_income = p_expense = p_net = None

    anomalies = find_anomalies(ledger, month)
    by_category = expenses_by(month_df, "category")
    by_account = expenses_by(month_df, "account")

    # סדרות ל-sparkline: 6 החודשים האחרונים עד החודש הנוכחי (כולל)
    window = all_months[max(0, index - 5): index + 1]
    spark_income, spark_expense, spark_net = [], [], []
    for m in window:
        m_df = ledger[ledger["month"] == m]
        inc = float(m_df[m_df["amount"] > 0]["amount"].sum())
        exp = float(-m_df[m_df["amount"] < 0]["amount"].sum())
        spark_income.append(inc)
        spark_expense.append(exp)
        spark_net.append(inc - exp)

    accounts = sorted(month_df["account"].dropna().unique())
    body = [
        head(
            month_he(month),
            f"{len(month_df)} תנועות · {len(accounts)} חשבונות · {', '.join(accounts)}",
        ),
        connections_strip(load_sync_status()),
        tiles(
            [
                {
                    "label": "הכנסות",
                    "amount": income,
                    "cls": "pos",
                    "accent": ACCENT_INCOME,
                    "note": delta_note(income, p_income, True),
                    "spark": spark_income,
                },
                {
                    "label": "הוצאות",
                    "amount": expense,
                    "cls": "neg",
                    "accent": ACCENT_EXPENSE,
                    "note": delta_note(expense, p_expense, False),
                    "spark": spark_expense,
                },
                {
                    "label": "נטו",
                    "amount": net,
                    "cls": "pos" if net >= 0 else "neg",
                    "accent": ACCENT_NET,
                    "note": delta_note(net, p_net, True) or ("עודף" if net >= 0 else "גירעון"),
                    "spark": spark_net,
                },
            ]
        ),
        balances_card(load_balances()),
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
                    money_html(item["current"], sort_key=True),
                    money_html(item["average"]),
                    f'<span class="flag {direction}">{arrow} {abs(item["delta"]) * 100:.0f}%'
                    f" {word} לממוצע</span>",
                ]
            )
        body.append(
            card(
                f"חריגות מול הממוצע ההיסטורי ({anomalies[0]['months']} חודשים אחורה)",
                table(["קטגוריה", "החודש", "ממוצע", "סטייה"], rows),
            )
        )

    body.append(chart_card("הוצאות לפי קטגוריה", by_category, unit="הוצאה"))
    body.append(chart_card("הוצאות לפי חשבון/כרטיס", by_account, unit="הוצאה"))

    ledger_rows = []
    for _, row in month_df.sort_values("amount").iterrows():
        amount = float(row["amount"])
        sign_class = "neg" if amount < 0 else "pos"
        ledger_rows.append(
            [
                f'<span data-sort="{esc(row["date"])}">{esc(row["date"])}</span>',
                esc(row["description"]),
                f'<span class="chip">{esc(row["category"])}</span>',
                esc(row["account"]),
                f'<span class="{sign_class}">{money_html(amount, sort_key=True)}</span>',
            ]
        )
    body.append(
        searchable_table(
            "כל התנועות בחודש",
            ["תאריך", "תיאור", "קטגוריה", "חשבון", "סכום"],
            ledger_rows,
            table_id="tx",
            numeric_from=4,
        )
    )

    out_dir = REPORTS_DIR / month
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "dashboard.html").write_text(
        page(f"דשבורד {month}", "\n".join(body), nav_for(month, all_months)),
        encoding="utf-8",
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
        result = build_month(ledger, month, months)
        print(
            f"✓ {month}: הכנסות {money(result['income'])} | "
            f"הוצאות {money(result['expense'])} | נטו {money(result['net'])}"
            + (f" | {len(result['anomalies'])} חריגות" if result["anomalies"] else "")
        )
        print(f"  {result['path'].relative_to(REPORTS_DIR.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
