"""Build the dashboard, the annual report, anomalies and benefit optimisation."""

from __future__ import annotations

import html
import os
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timedelta

from common import (REPORTS_DIR, load_yaml, read_transactions)

# --- validated palette (dataviz reference instance) ------------------------
# Income/expense sit in the CVD warn band as a pair, so every mark that uses
# them is direct-labelled and named in the legend -- never colour alone.
SERIES = {
    "income_light": "#1baf7a", "income_dark": "#199e70",
    "expense_light": "#e34948", "expense_dark": "#e66767",
    "accent_light": "#2a78d6", "accent_dark": "#3987e5",
}

ANOMALY_CATEGORY_JUMP = 0.40     # category over its own mean by this much
ANOMALY_CATEGORY_MIN_ILS = 250   # ...and by at least this much in shekels
ANOMALY_TXN_MULTIPLE = 3.0       # single txn over N x its baseline
ANOMALY_MIN_MONTHS = 3
ANOMALY_MERCHANT_HISTORY = 3     # prior charges needed to judge a merchant on its own
DUPLICATE_WINDOW_DAYS = 3
NEW_MERCHANT_THRESHOLD = 500.0
MAX_ANOMALIES = 15

SEVERITY_ORDER = {"serious": 0, "warning": 1}


def ils(n):
    return f"{n:,.0f} ₪"


# ------------------------------------------------------------ aggregation --

def by_month(rows):
    out = defaultdict(lambda: {"income": 0.0, "expense": 0.0})
    for r in rows:
        m = r["date"][:7]
        if r["amount"] >= 0:
            out[m]["income"] += r["amount"]
        else:
            out[m]["expense"] += -r["amount"]
    for m in out:
        out[m]["net"] = out[m]["income"] - out[m]["expense"]
    return dict(sorted(out.items()))


def category_totals(rows, month=None):
    out = defaultdict(float)
    for r in rows:
        if r["amount"] >= 0:
            continue
        if month and r["date"][:7] != month:
            continue
        out[r["category"]] += -r["amount"]
    return dict(sorted(out.items(), key=lambda x: -x[1]))


# -------------------------------------------------------------- anomalies --

def find_anomalies(rows):
    found = []
    months = by_month(rows)
    month_keys = sorted(months)
    if not month_keys:
        return found
    latest = month_keys[-1]

    # 1. category spending well above its own running average
    per_cat_month = defaultdict(lambda: defaultdict(float))
    for r in rows:
        if r["amount"] < 0:
            per_cat_month[r["category"]][r["date"][:7]] += -r["amount"]

    for cat, series in per_cat_month.items():
        history = [v for m, v in series.items() if m != latest]
        if len(history) < ANOMALY_MIN_MONTHS - 1:
            continue
        current = series.get(latest, 0.0)
        avg = statistics.mean(history)
        if (avg > 0 and current > avg * (1 + ANOMALY_CATEGORY_JUMP)
                and current - avg >= ANOMALY_CATEGORY_MIN_ILS):
            found.append({
                "kind": "קטגוריה חורגת",
                "severity": "warning",
                "text": f"{cat} — {ils(current)} בחודש {latest}, לעומת ממוצע {ils(avg)}",
                "delta": f"+{100 * (current / avg - 1):.0f}%",
            })

    # 2. single transaction far above its baseline, in the latest month only.
    #    A recurring merchant is judged against its own history -- a category
    #    median would flag every fuel stop just because parking shares the
    #    category. Only one-off merchants fall back to the category.
    per_cat_amounts = defaultdict(list)
    per_merch_amounts = defaultdict(list)
    for r in rows:
        if r["amount"] < 0:
            per_cat_amounts[r["category"]].append(-r["amount"])
            per_merch_amounts[r["merchant_norm"]].append(-r["amount"])

    for r in rows:
        if r["amount"] >= 0 or r["date"][:7] != latest:
            continue
        amt = -r["amount"]

        own = [a for a in per_merch_amounts[r["merchant_norm"]] if a != amt]
        if len(own) >= ANOMALY_MERCHANT_HISTORY:
            baseline, label = statistics.median(own), f"רגיל אצל {r['merchant']}"
        else:
            amounts = per_cat_amounts[r["category"]]
            if len(amounts) < 4:
                continue
            baseline, label = statistics.median(amounts), f"חציון {r['category']}"

        if baseline > 0 and amt > baseline * ANOMALY_TXN_MULTIPLE:
            found.append({
                "kind": "תנועה חריגה",
                "severity": "warning",
                "text": f"{r['merchant']} — {ils(amt)} ב-{r['date']} ({label}: {ils(baseline)})",
                "delta": f"×{amt / baseline:.1f}",
            })

    # 3. same merchant, same amount, a few days apart -- possible double charge
    buckets = defaultdict(list)
    for r in rows:
        if r["amount"] < 0:
            buckets[(r["merchant_norm"], round(-r["amount"], 2))].append(r)
    for (merch, amt), group in buckets.items():
        if len(group) < 2:
            continue
        group.sort(key=lambda x: x["date"])
        for a, b in zip(group, group[1:]):
            d1 = datetime.strptime(a["date"], "%Y-%m-%d")
            d2 = datetime.strptime(b["date"], "%Y-%m-%d")
            if 0 < (d2 - d1).days <= DUPLICATE_WINDOW_DAYS:
                found.append({
                    "kind": "חיוב כפול חשוד",
                    "severity": "serious",
                    "text": f"{b['merchant']} — {ils(amt)} פעמיים ({a['date']} ו-{b['date']})",
                    "delta": "×2",
                })

    # 4. large charge at a merchant that never appeared before
    first_seen = {}
    for r in sorted(rows, key=lambda x: x["date"]):
        first_seen.setdefault(r["merchant_norm"], r["date"])
    for r in rows:
        if r["amount"] >= 0 or r["date"][:7] != latest:
            continue
        if abs(r["amount"]) >= NEW_MERCHANT_THRESHOLD and first_seen[r["merchant_norm"]] == r["date"]:
            found.append({
                "kind": "בית עסק חדש",
                "severity": "warning",
                "text": f"{r['merchant']} — {ils(-r['amount'])} ב-{r['date']}, חיוב ראשון",
                "delta": "חדש",
            })

    found.sort(key=lambda a: SEVERITY_ORDER.get(a.get("severity"), 9))
    return found[:MAX_ANOMALIES]


# ------------------------------------------------------------- benefits ----

def optimise_benefits(rows, benefits):
    """What each category would have returned on the best card vs the one used."""
    cards = (benefits or {}).get("cards") or {}
    if not cards:
        return None

    def rate_for(card_id, category):
        card = cards.get(card_id)
        if not card:
            return 0.0
        base = (card.get("base") or {})
        rate = (card.get("category_rates") or {}).get(category, base.get("rate", 0.0))
        if base.get("unit") in ("points", "miles"):
            rate *= float(base.get("point_value") or 0.0)
        return float(rate or 0.0)

    per_cat_acct = defaultdict(float)
    for r in rows:
        if r["amount"] < 0:
            per_cat_acct[(r["category"], r["account"])] += -r["amount"]

    actual = 0.0
    best = 0.0
    suggestions = []

    per_cat = defaultdict(float)
    for (cat, acct), spend in per_cat_acct.items():
        actual += spend * rate_for(acct, cat)
        per_cat[cat] += spend

    for cat, spend in per_cat.items():
        best_card = max(cards, key=lambda c: rate_for(c, cat))
        best_rate = rate_for(best_card, cat)
        best += spend * best_rate

        used = {a: s for (c, a), s in per_cat_acct.items() if c == cat}
        main_card = max(used, key=used.get) if used else None
        if main_card and main_card != best_card:
            gain = spend * (best_rate - rate_for(main_card, cat))
            if gain >= 1:
                suggestions.append({
                    "category": cat,
                    "spend": spend,
                    "from": cards.get(main_card, {}).get("label", main_card),
                    "to": cards.get(best_card, {}).get("label", best_card),
                    "gain": gain,
                })

    suggestions.sort(key=lambda x: -x["gain"])
    return {"actual": actual, "best": best, "left_on_table": best - actual,
            "suggestions": suggestions}


# ----------------------------------------------------------------- charts --

def svg_monthly(months, limit=12):
    """Grouped bars: income vs expense per month. Both series direct-labelled."""
    keys = list(months)[-limit:]
    if not keys:
        return "<p class='empty'>אין נתונים</p>"

    W, H = 760, 300
    ml, mr, mt, mb = 46, 8, 28, 46
    plot_w = W - ml - mr
    plot_h = H - mt - mb

    peak = max(max(months[k]["income"], months[k]["expense"]) for k in keys) or 1
    slot = plot_w / len(keys)
    bar_w = min(20, (slot - 12) / 2)

    parts = [f'<svg viewBox="0 0 {W} {H}" role="img" class="chart" '
             f'aria-label="הכנסות מול הוצאות לפי חודש">']

    # recessive gridlines, each carrying its value
    for frac in (0.25, 0.5, 0.75, 1.0):
        y = mt + plot_h - plot_h * frac
        parts.append(f'<line class="grid" x1="{ml}" y1="{y:.1f}" x2="{W-mr}" y2="{y:.1f}"/>')
        parts.append(f'<text class="tick axis-val" x="{ml-8}" y="{y+4:.1f}">'
                     f'{peak*frac/1000:.0f}k</text>')
    parts.append(f'<line class="axis" x1="{ml}" y1="{mt+plot_h}" x2="{W-mr}" y2="{mt+plot_h}"/>')

    for i, k in enumerate(keys):
        cx = ml + slot * i + slot / 2
        # Both series carry a direct value label -- identity is never colour alone.
        for j, (series, colour) in enumerate((("income", "var(--income)"),
                                              ("expense", "var(--expense)"))):
            val = months[k][series]
            h = (val / peak) * plot_h
            # 2px surface gap between the paired bars
            x = cx - bar_w - 1 + j * (bar_w + 2)
            y = mt + plot_h - h
            label = "הכנסות" if series == "income" else "הוצאות"
            if h > 0.5:
                parts.append(
                    f'<rect class="bar" x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" '
                    f'height="{h:.1f}" rx="4" fill="{colour}">'
                    f'<title>{k} · {label}: {ils(val)}</title></rect>')
                parts.append(f'<text class="bar-label" x="{x + bar_w/2:.1f}" '
                             f'y="{y - 5:.1f}">{val/1000:.1f}k</text>')

        parts.append(f'<text class="tick" x="{cx:.1f}" y="{mt + plot_h + 18:.1f}">{k[5:]}/{k[2:4]}</text>')

    parts.append("</svg>")
    return "".join(parts)


def html_category_bars(cats, limit=9):
    """Horizontal bars in plain HTML -- keeps RTL labels and values honest."""
    items = list(cats.items())
    if not items:
        return "<p class='empty'>אין נתונים</p>"
    head, tail = items[:limit], items[limit:]
    if tail:
        head.append(("אחר", sum(v for _, v in tail)))

    peak = max(v for _, v in head) or 1
    out = ['<div class="cat-bars">']
    for name, val in head:
        pct = 100 * val / peak
        out.append(
            f'<div class="cat-row" title="{html.escape(name)}: {ils(val)}">'
            f'<span class="cat-name">{html.escape(name)}</span>'
            f'<span class="cat-track"><span class="cat-fill" style="width:{pct:.1f}%"></span></span>'
            f'<span class="cat-val">{ils(val)}</span>'
            f"</div>")
    out.append("</div>")
    return "".join(out)


# ------------------------------------------------------------------ page ---

CSS = """
*,*::before,*::after{box-sizing:border-box}
:root{
  color-scheme:light;
  --surface-0:#f5f5f3; --surface-1:#fcfcfb; --border:#e2e1dc;
  --text-primary:#0b0b0b; --text-secondary:#52514e; --text-muted:#84837c;
  --income:#1baf7a; --expense:#e34948; --accent:#2a78d6;
  --warn-bg:#fdf3e7; --warn-bd:#eda100; --serious-bg:#fdecec; --serious-bd:#e34948;
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    color-scheme:dark;
    --surface-0:#121211; --surface-1:#1a1a19; --border:#33332f;
    --text-primary:#fff; --text-secondary:#c3c2b7; --text-muted:#8f8e85;
    --income:#199e70; --expense:#e66767; --accent:#3987e5;
    --warn-bg:#2b2412; --warn-bd:#c98500; --serious-bg:#2e1a1a; --serious-bd:#e66767;
  }
}
:root[data-theme="dark"]{
  color-scheme:dark;
  --surface-0:#121211; --surface-1:#1a1a19; --border:#33332f;
  --text-primary:#fff; --text-secondary:#c3c2b7; --text-muted:#8f8e85;
  --income:#199e70; --expense:#e66767; --accent:#3987e5;
  --warn-bg:#2b2412; --warn-bd:#c98500; --serious-bg:#2e1a1a; --serious-bd:#e66767;
}
body{margin:0;background:var(--surface-0);color:var(--text-primary);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans Hebrew",Arial,sans-serif;
  direction:rtl;line-height:1.5}
.wrap{max-width:920px;margin:0 auto;padding:32px 20px 64px}
h1{font-size:24px;margin:0 0 4px} h2{font-size:16px;margin:0 0 14px;font-weight:600}
.sub{color:var(--text-secondary);font-size:13px;margin:0 0 24px}
.banner{background:var(--warn-bg);border:1px solid var(--warn-bd);border-radius:8px;
  padding:12px 14px;font-size:13px;margin:0 0 24px}
.card{background:var(--surface-1);border:1px solid var(--border);border-radius:12px;
  padding:20px;margin:0 0 20px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:0 0 20px}
.tile{background:var(--surface-1);border:1px solid var(--border);border-radius:12px;padding:16px}
.tile .k{font-size:12px;color:var(--text-secondary);margin:0 0 6px}
.tile .v{font-size:26px;font-weight:650;letter-spacing:-.02em}
.tile .m{font-size:11px;color:var(--text-muted);margin-top:4px}
.v.pos{color:var(--income)} .v.neg{color:var(--expense)}
.legend{display:flex;gap:16px;font-size:12px;color:var(--text-secondary);margin:0 0 10px}
.legend i{width:10px;height:10px;border-radius:3px;display:inline-block;margin-left:6px}
.chart{width:100%;height:auto;overflow:visible}
.grid{stroke:var(--border);stroke-width:1}
.axis{stroke:var(--border);stroke-width:1}
.bar{transition:opacity .12s} .bar:hover{opacity:.75}
.tick{font-size:10px;fill:var(--text-muted);text-anchor:middle}
.axis-val{text-anchor:end}
.bar-label{font-size:10px;fill:var(--text-secondary);text-anchor:middle}
.cat-bars{display:flex;flex-direction:column;gap:8px}
.cat-row{display:grid;grid-template-columns:130px 1fr 88px;align-items:center;gap:10px;font-size:13px}
.cat-name{color:var(--text-secondary);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cat-track{background:var(--surface-0);border-radius:4px;height:14px;overflow:hidden}
.cat-fill{display:block;height:100%;background:var(--accent);border-radius:4px}
.cat-val{text-align:left;font-variant-numeric:tabular-nums;color:var(--text-primary)}
.an{border-inline-start:3px solid var(--warn-bd);background:var(--warn-bg);
  border-radius:6px;padding:10px 12px;margin:0 0 8px;font-size:13px}
.an.serious{border-inline-start-color:var(--serious-bd);background:var(--serious-bg)}
.an .kind{font-weight:650;margin-left:8px}
.an .delta{float:left;color:var(--text-secondary);font-size:12px}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:right;padding:7px 8px;border-bottom:1px solid var(--border)}
th{color:var(--text-secondary);font-weight:600}
td.num{font-variant-numeric:tabular-nums;text-align:left}
details{margin-top:10px} summary{cursor:pointer;color:var(--text-secondary);font-size:13px}
.empty{color:var(--text-muted);font-size:13px}
.scroll{overflow-x:auto}
footer{color:var(--text-muted);font-size:12px;margin-top:28px}
"""


def build_dashboard(rows, anomalies, benefits_result, demo=False):
    months = by_month(rows)
    keys = sorted(months)
    latest = keys[-1] if keys else "—"
    cur = months.get(latest, {"income": 0, "expense": 0, "net": 0})
    cats = category_totals(rows, latest)
    all_cats = category_totals(rows)

    banner = ""
    if demo:
        banner = ('<div class="banner"><b>נתוני דוגמה סינתטיים.</b> '
                  'זו הדגמה של המערכת — לא הכספים שלך. '
                  'שים דפים אמיתיים ב-<code>inbox/</code> והרץ '
                  '<code>python3 scripts/run_all.py</code> כדי להחליף.</div>')

    p = [f'<div class="wrap"><h1>דשבורד פיננסי</h1>'
         f'<p class="sub">חודש {latest} · {len(rows)} תנועות · '
         f'הופק ב-{datetime.now():%d/%m/%Y %H:%M}</p>{banner}']

    # hero tiles
    p.append('<div class="tiles">')
    p.append(f'<div class="tile"><p class="k">הכנסות</p>'
             f'<div class="v pos">{ils(cur["income"])}</div></div>')
    p.append(f'<div class="tile"><p class="k">הוצאות</p>'
             f'<div class="v neg">{ils(cur["expense"])}</div></div>')
    net_cls = "pos" if cur["net"] >= 0 else "neg"
    rate = (100 * cur["net"] / cur["income"]) if cur["income"] else 0
    p.append(f'<div class="tile"><p class="k">נטו</p>'
             f'<div class="v {net_cls}">{ils(cur["net"])}</div>'
             f'<p class="m">שיעור חיסכון {rate:.0f}%</p></div>')
    if len(keys) > 1:
        avg_exp = statistics.mean(months[k]["expense"] for k in keys[:-1])
        diff = cur["expense"] - avg_exp
        # Spending above the average is the bad direction, so it wears the
        # expense colour; below-average spending wears the income colour.
        diff_cls = "neg" if diff >= 0 else "pos"
        p.append(f'<div class="tile"><p class="k">הוצאות מול הממוצע</p>'
                 f'<div class="v {diff_cls}">{"+" if diff >= 0 else "−"}{abs(diff):,.0f} ₪</div>'
                 f'<p class="m">ממוצע {len(keys)-1} החודשים הקודמים: {ils(avg_exp)}</p></div>')
    p.append("</div>")

    # monthly chart
    p.append('<div class="card"><h2>הכנסות מול הוצאות לפי חודש</h2>'
             '<div class="legend">'
             '<span><i style="background:var(--income)"></i>הכנסות</span>'
             '<span><i style="background:var(--expense)"></i>הוצאות</span></div>')
    p.append(svg_monthly(months))
    p.append("<details><summary>הצג כטבלה</summary><div class='scroll'><table>"
             "<tr><th>חודש</th><th>הכנסות</th><th>הוצאות</th><th>נטו</th></tr>")
    for k in reversed(keys):
        m = months[k]
        p.append(f"<tr><td>{k}</td><td class='num'>{m['income']:,.0f}</td>"
                 f"<td class='num'>{m['expense']:,.0f}</td>"
                 f"<td class='num'>{m['net']:,.0f}</td></tr>")
    p.append("</table></div></details></div>")

    # categories
    p.append(f'<div class="card"><h2>הוצאות לפי קטגוריה — {latest}</h2>')
    p.append(html_category_bars(cats))
    p.append("</div>")

    # anomalies
    p.append('<div class="card"><h2>חריגות</h2>')
    if anomalies:
        for a in anomalies:
            cls = "an serious" if a.get("severity") == "serious" else "an"
            p.append(f'<div class="{cls}"><span class="delta">{html.escape(a["delta"])}</span>'
                     f'<span class="kind">{html.escape(a["kind"])}</span>'
                     f'{html.escape(a["text"])}</div>')
    else:
        p.append('<p class="empty">לא נמצאו חריגות.</p>')
    p.append("</div>")

    # benefits
    p.append('<div class="card"><h2>אופטימיזציית הטבות</h2>')
    if benefits_result is None:
        p.append('<p class="empty">לא הוגדרו הטבות. מלא את '
                 '<code>config/card_benefits.yaml</code> כדי להפעיל את הדוח הזה.</p>')
    elif not benefits_result["suggestions"]:
        p.append(f'<p class="empty">הצבירה כבר אופטימלית — {ils(benefits_result["actual"])} '
                 f'הוחזרו בתקופה.</p>')
    else:
        p.append(f'<p class="sub">הוחזר בפועל {ils(benefits_result["actual"])} · '
                 f'אפשרי {ils(benefits_result["best"])} · '
                 f'<b>הפסד {ils(benefits_result["left_on_table"])}</b></p>')
        p.append("<div class='scroll'><table><tr><th>קטגוריה</th><th>הוצאה</th>"
                 "<th>שולם ב-</th><th>עדיף</th><th>הפרש</th></tr>")
        for s in benefits_result["suggestions"][:10]:
            p.append(f"<tr><td>{html.escape(s['category'])}</td>"
                     f"<td class='num'>{s['spend']:,.0f}</td>"
                     f"<td>{html.escape(str(s['from']))}</td>"
                     f"<td>{html.escape(str(s['to']))}</td>"
                     f"<td class='num'>{s['gain']:,.0f}</td></tr>")
        p.append("</table></div>")
    p.append("</div>")

    # all-time categories
    p.append('<div class="card"><h2>הוצאות לפי קטגוריה — כל התקופה</h2>')
    p.append(html_category_bars(all_cats))
    p.append("</div>")

    p.append('<footer>נוצר על ידי scripts/report.py · הנתונים ב-data/transactions.csv</footer>')
    p.append("</div>")

    return (f'<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>דשבורד פיננסי</title><style>{CSS}</style></head>'
            f'<body>{"".join(p)}</body></html>')


def build_annual_md(rows, anomalies):
    months = by_month(rows)
    years = defaultdict(lambda: {"income": 0.0, "expense": 0.0})
    for m, v in months.items():
        years[m[:4]]["income"] += v["income"]
        years[m[:4]]["expense"] += v["expense"]

    out = ["# דוח שנתי", ""]
    for y in sorted(years, reverse=True):
        v = years[y]
        net = v["income"] - v["expense"]
        out += [f"## {y}", "",
                f"- הכנסות: **{ils(v['income'])}**",
                f"- הוצאות: **{ils(v['expense'])}**",
                f"- נטו: **{ils(net)}**", ""]
        ycats = category_totals([r for r in rows if r["date"][:4] == y])
        out += ["| קטגוריה | סכום | חלק |", "|---|---:|---:|"]
        tot = sum(ycats.values()) or 1
        for c, amt in list(ycats.items())[:15]:
            out.append(f"| {c} | {amt:,.0f} | {100*amt/tot:.1f}% |")
        out.append("")

    out += ["## חריגות", ""]
    if anomalies:
        for a in anomalies:
            out.append(f"- **{a['kind']}** ({a['delta']}) — {a['text']}")
    else:
        out.append("לא נמצאו חריגות.")
    out.append("")
    return "\n".join(out)


def main(demo=False):
    rows = read_transactions()
    if not rows:
        print("  אין תנועות. הרץ קודם את ingest.py.")
        return 1

    os.makedirs(REPORTS_DIR, exist_ok=True)
    anomalies = find_anomalies(rows)

    benefits = load_yaml("card_benefits.yaml")
    ben_result = optimise_benefits(rows, benefits)

    dash = os.path.join(REPORTS_DIR, "dashboard.html")
    with open(dash, "w", encoding="utf-8") as fh:
        fh.write(build_dashboard(rows, anomalies, ben_result, demo=demo))

    annual = os.path.join(REPORTS_DIR, "annual.md")
    with open(annual, "w", encoding="utf-8") as fh:
        fh.write(build_annual_md(rows, anomalies))

    months = by_month(rows)
    latest = sorted(months)[-1]
    cur = months[latest]

    print(f"  דשבורד : {dash}")
    print(f"  שנתי   : {annual}")
    print(f"\n  {latest}:  הכנסות {ils(cur['income'])} · "
          f"הוצאות {ils(cur['expense'])} · נטו {ils(cur['net'])}")
    print(f"  חריגות : {len(anomalies)}")
    if ben_result and ben_result["suggestions"]:
        print(f"  הטבות  : הפסד {ils(ben_result['left_on_table'])} בתקופה")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    sys.exit(main("--demo" in sys.argv))
