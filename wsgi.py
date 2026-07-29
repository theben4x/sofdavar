"""נקודת הכניסה ל-WSGI בפרודקשן — Vercel, gunicorn, uWSGI.

Vercel מחפש *מופע* Flask בשם ``app`` באחד מהשמות המוכרים (app.py, index.py,
server.py, main.py, wsgi.py, asgi.py — בשורש או תחת src/ app/ api/).
``run.py`` הוא factory ומייצר את המופע רק בתוך main(), ולכן הוא לא נמצא.
כאן המופע נוצר ברמת המודול, פעם אחת לכל תהליך.

    gunicorn wsgi:app

לפיתוח מקומי המשיכו להשתמש ב-``python run.py`` — הוא נותן --port ו--debug.

הערה: ``app.py`` בשורש היה מתנגש עם חבילת ``app/`` של הפרויקט, ולכן דווקא
השם הזה. אל תשנו אותו בלי לעדכן את vercel.json.
"""

from __future__ import annotations

from app import create_app

app = create_app()
