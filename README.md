# ניהול פיננסי

איחוד דפי אשראי ובנק ממספר מקורות לקובץ תנועות אחד, סיווג קטגוריות, והפקת
דשבורד, דוח שנתי, חריגות ואופטימיזציית הטבות.

## התקנה

```bash
pip install -r requirements.txt
```

## שימוש

```bash
# הדגמה על נתונים סינתטיים — לראות שהכל עובד
python3 scripts/run_all.py --demo

# על הנתונים שלך
#   1. שים דפים ב-inbox/cal/ , inbox/max/ , inbox/bank/
#   2. כייל כל מקור חדש (פעם אחת בלבד):
python3 scripts/detect.py inbox/cal/<קובץ>
#   3. סמן verified: true ב-config/parsers.yaml, ואז:
python3 scripts/run_all.py
```

הדשבורד נוצר ב-`reports/dashboard.html`.

**ההוראות המלאות — כולל כיול כיוון הסימן — נמצאות ב-[CLAUDE.md](CLAUDE.md).**

## פרטיות

`inbox/`, `data/` ו-`reports/` חסומים ב-`.gitignore`. שום נתון פיננסי אמיתי
לא נכנס ל-git.
