"""כל נתיבי האתר.

סדר ההרשמה חשוב: הנתיבים הקבועים (``/about``, ``/blog``…) נרשמים לפני
נתיבי הקטגוריה, ובנוסף כל slug נבדק מול ``RESERVED_SLUGS`` בזמן הייבוא —
כך שקטגוריה לא תוכל להשתלט על עמוד קיים.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Iterable
from urllib.parse import quote

from flask import (
    Flask, Response, abort, current_app, jsonify, make_response, redirect,
    render_template, request, url_for,
)
from markupsafe import Markup, escape

from . import blog, codes, db, parasha, zmanim
from .config import rounded_floor
from .hebrew import normalize


def _canonical(path: str) -> str:
    return current_app.config["SITE_URL"] + path


def _meta(title: str, description: str, path: str, **extra) -> dict:
    """המטא-דאטה שמוזרקת ל-``base.html`` — מקבילה ל-generateMetadata."""
    site = current_app.config["SITE_NAME"]
    return {
        "title": title if title == site else f"{title} | {site}",
        "raw_title": title,
        "description": description,
        "canonical": _canonical(path),
        "path": path,
        **extra,
    }


#: העיר האחרונה שנבחרה. העדפת תצוגה בלבד — אין בה מידע מזהה.
CITY_COOKIE = "sofdavar-city"
CITY_COOKIE_MAX_AGE = 60 * 60 * 24 * 365


def _selected_city() -> tuple[zmanim.City, bool]:
    """העיר שלפיה מוצגים הזמנים, והאם היא נבחרה עכשיו.

    הסדר: פרמטר בכתובת (הבחירה הנוכחית), אחריו העוגייה (הבחירה הקודמת),
    ולבסוף ירושלים. הפרמטר קודם כדי שקישור לעיר מסוימת יעבוד גם למי
    שכבר בחר אחרת.
    """
    requested = (request.args.get("city") or "").strip()
    if requested in zmanim.CITIES_BY_SLUG:
        return zmanim.CITIES_BY_SLUG[requested], True
    return zmanim.get_city(request.cookies.get(CITY_COOKIE)), False


def _remember_city(html: str, city: zmanim.City, chosen: bool) -> Response:
    """שומר את הבחירה, כדי שהיא תחזיק גם בעמוד הבא ובביקור הבא.

    ``Vary: Cookie`` חובה: אותה כתובת בדיוק מחזירה זמנים אחרים לפי
    העוגייה, ובלעדיו מטמון משותף היה מגיש את ירושלים למי שבחר חיפה.
    """
    response = make_response(html)
    response.headers["Vary"] = "Cookie"
    if chosen:
        response.set_cookie(
            CITY_COOKIE,
            city.slug,
            max_age=CITY_COOKIE_MAX_AGE,
            samesite="Lax",
            httponly=True,
            secure=request.is_secure,
        )
    return response


def _codes(results: Iterable[dict]) -> list[str]:
    """קודי השאלות שכבר מוצגות, כדי שההצעות לא יחזרו עליהן."""
    return [r["code"] for r in results if r.get("code")]


def _log_empty(query: str, where: str) -> None:
    """רושם חיפוש שלא החזיר כלום.

    זו הרשימה של מה שחסר במאגר: כל שורה כאן היא אדם שחיפש ולא מצא.
    נכתב ל-stdout ולא לקובץ, כי מערכת הקבצים ב-Vercel אינה ניתנת
    לכתיבה והמופע נמחק בין בקשות.

    נרשמת השאילתה בלבד. אין כאן כתובת IP, מזהה משתמש או עוגייה —
    המטרה היא פערי תוכן, לא מעקב.
    """
    if not current_app.config.get("LOG_EMPTY_SEARCHES"):
        return
    # דורש לפחות אות או ספרה אחת: "?!?" עובר את הנרמול כמו שהוא, ורשימת
    # הפערים צריכה להישאר רשימה של שאלות ולא של הקלדות מקריות.
    if not any(ch.isalnum() for ch in normalize(query)):
        return
    current_app.logger.info('no-results where=%s q="%s"', where, query.replace('"', "'"))


def _breadcrumbs(*items: tuple[str, str]) -> dict:
    """BreadcrumbList — עוזר לגוגל להציג את מסלול הניווט בתוצאות."""
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": index + 1,
                "name": name,
                "item": _canonical(path),
            }
            for index, (name, path) in enumerate(items)
        ],
    }


def register_routes(app: Flask) -> None:
    # -----------------------------------------------------------------------
    # הקשר משותף לכל התבניות
    # -----------------------------------------------------------------------

    @app.context_processor
    def inject_globals() -> dict:
        return {
            "site_name": app.config["SITE_NAME"],
            "site_tagline": app.config["SITE_TAGLINE"],
            "verse": app.config["VERSE"],
            "verse_source": app.config["VERSE_SOURCE"],
            "verse_emphasis": app.config["VERSE_EMPHASIS"],
            "home_lede": app.config["HOME_LEDE"],
            "nav_categories": db.list_categories(),
            "current_year": date.today().year,
            "current_path": request.path,
        }

    @app.template_global()
    def display_total() -> int:
        """המספר שמוצג כ"למעלה מ-N" ברמז שבתוך תיבת השאלה.

        template_global ולא משתנה הקשר: הרמז מרונדר בתוך ``search_box``,
        ומאקרו מיובא אינו רואה את ההקשר של העמוד שקורא לו.
        """
        return app.config["DISPLAY_TOTAL_OVERRIDE"] or rounded_floor(db.question_count())

    @app.template_filter("thousands")
    def thousands(value: int) -> str:
        return f"{value:,}"

    @app.template_filter("emphasize")
    def emphasize(text: str, words: Iterable[str]) -> Markup:
        """עוטף מילים נבחרות ב-<em>. ההדגשה היא עניין של תצוגה בלבד, ולכן
        הפסוק נשאר מחרוזת אחת ב-config ומשמש כמו שהוא בפוטר ובמטא.

        מריצים escape לפני ההזרקה — הפסוק אמנם קבוע, אבל מסנן שמחזיר
        Markup חייב לחטא את הקלט שלו ולא להסתמך על מי שקורא לו.
        """
        out = str(escape(text))
        for word in words:
            if word:
                out = out.replace(word, f'<em class="verse-em">{word}</em>')
        return Markup(out)

    # -----------------------------------------------------------------------
    # עמודים ראשיים
    # -----------------------------------------------------------------------

    @app.route("/")
    def home():
        total = db.question_count()
        meta_copy = db.get_meta("copy", {}) or {}
        city, chosen = _selected_city()
        shabbat = zmanim.upcoming_shabbat(city)
        html = render_template(
            "home.html",
            meta=_meta(
                meta_copy.get("home_title") or app.config["SITE_NAME"],
                meta_copy.get("home_description") or app.config["SITE_TAGLINE"],
                "/",
                jsonld=[
                    {
                        "@context": "https://schema.org",
                        "@type": "WebSite",
                        "name": app.config["SITE_NAME"],
                        "url": _canonical("/"),
                        "inLanguage": "he-IL",
                        "potentialAction": {
                            "@type": "SearchAction",
                            "target": _canonical("/search?q={search_term_string}"),
                            "query-input": "required name=search_term_string",
                        },
                    }
                ],
            ),
            categories=db.list_categories(),
            total_questions=total,
            question_of_day=db.question_of_the_day(date.today()),
            shabbat=shabbat,
            shabbat_parasha=parasha.label(shabbat["saturday"]),
            cities=zmanim.CITIES,
        )
        return _remember_city(html, city, chosen)

    @app.route("/about")
    def about():
        meta_copy = db.get_meta("copy", {}) or {}
        return render_template(
            "about.html",
            meta=_meta(
                "אודות",
                meta_copy.get("about_description") or "על אתר סוף דבר ועל דרך העבודה שלו.",
                "/about",
                jsonld=[_breadcrumbs((app.config["SITE_NAME"], "/"), ("אודות", "/about"))],
            ),
            about_html=db.get_meta("about_html", ""),
            total_questions=db.question_count(),
            categories=db.list_categories(),
        )

    # -----------------------------------------------------------------------
    # חיפוש
    # -----------------------------------------------------------------------

    @app.route("/api/search")
    def api_search():
        query = (request.args.get("q") or "").strip()
        if not normalize(query).strip():
            return jsonify({"query": query, "results": [], "also": []})
        results = db.search(query, limit=10)
        if not results:
            _log_empty(query, "api")
        return jsonify({
            "query": query,
            "results": results,
            # מדור נפרד ולא ערבוב — ראה app/semantic.py
            "also": db.suggestions(query, _codes(results), limit=3),
        })

    @app.route("/search")
    def search_page():
        """תוצאות מלאות. קיים גם כדי שהחיפוש יעבוד בלי JavaScript."""
        query = (request.args.get("q") or "").strip()
        results = db.search(query, limit=50) if normalize(query).strip() else []
        if query and not results:
            _log_empty(query, "page")
        also = db.suggestions(query, _codes(results), limit=4) if results or query else []
        return render_template(
            "search.html",
            also=also,
            meta=_meta(
                f'שאלו אותי: {query}' if query else "שאלו אותי",
                f'תוצאות חיפוש עבור "{query}" במאגר סוף דבר.' if query
                else "שאלו אותי — חיפוש במאגר השאלות והתשובות.",
                "/search",
                noindex=True,  # עמודי תוצאות אינם תוכן ייחודי
            ),
            query=query,
            results=results,
        )

    @app.route("/q/<int:number>")
    def question_by_number(number: int):
        """קיצור היסטורי לציטוט: /q/47 מפנה לכתובת הקבועה של שאלה 47.

        המספר הרץ ממוספר מחדש בכל ייבוא, ולכן הוא לא יכול להיות הכתובת
        עצמה — אבל קישורים ישנים בנוסח הזה חייבים להמשיך לעבוד.
        """
        question = db.get_question_by_number(number)
        if not question:
            abort(404)
        return redirect(url_for("question", code=question["code"]), code=301)

    # -----------------------------------------------------------------------
    # זמנים
    # -----------------------------------------------------------------------

    @app.route("/zmanim")
    def zmanim_page():
        # אותה בחירת עיר של דף הבית, ובאותה עוגייה — מי שבחר שם לא צריך
        # לבחור שוב כאן.
        city, chosen = _selected_city()
        try:
            day = date.fromisoformat(request.args["date"]) if "date" in request.args else None
        except ValueError:
            day = None
        day = day or datetime.now(zmanim.ISRAEL_TZ).date()

        meta_copy = db.get_meta("copy", {}) or {}
        html = render_template(
            "zmanim.html",
            meta=_meta(
                f"זמני היום ב{city.name}",
                meta_copy.get("zmanim_description")
                or f"זמני כניסת שבת ויציאת שבת, נץ, חצות היום, שקיעה וצאת הכוכבים ב{city.name}.",
                "/zmanim",
                jsonld=[_breadcrumbs((app.config["SITE_NAME"], "/"), ("זמנים", "/zmanim"))],
            ),
            day=day,
            today=datetime.now(zmanim.ISRAEL_TZ).date(),
            city=city,
            cities=zmanim.CITIES,
            data=zmanim.compute(day, city),
            shabbat=zmanim.upcoming_shabbat(city),
        )
        return _remember_city(html, city, chosen)

    # -----------------------------------------------------------------------
    # מה נברך
    # -----------------------------------------------------------------------

    @app.route("/ma-nevarech")
    def berachot_page():
        meta_copy = db.get_meta("copy", {}) or {}
        texts = db.get_meta("blessing_texts", {}) or {}
        foods = db.list_berachot()
        return render_template(
            "berachot.html",
            meta=_meta(
                "מה נברך",
                meta_copy.get("berachot_description")
                or "טבלת ברכות למאות מאכלים ומשקאות, עם נוסח הברכות המלא בניקוד.",
                "/ma-nevarech",
                jsonld=[_breadcrumbs((app.config["SITE_NAME"], "/"), ("מה נברך", "/ma-nevarech"))],
            ),
            foods=foods,
            blessing_texts=texts,
            food_categories=sorted({f["category"] for f in foods}),
        )

    # -----------------------------------------------------------------------
    # בלוג
    # -----------------------------------------------------------------------

    @app.route("/blog")
    def blog_index():
        meta_copy = db.get_meta("copy", {}) or {}
        return render_template(
            "blog_index.html",
            meta=_meta(
                "בלוג",
                meta_copy.get("blog_description") or "מאמרים על הלכה, מנהג ודרכי לימוד.",
                "/blog",
                jsonld=[_breadcrumbs((app.config["SITE_NAME"], "/"), ("בלוג", "/blog"))],
            ),
            posts=blog.all_posts(app.config["BLOG_DIR"]),
        )

    @app.route("/blog/<slug>")
    def blog_post(slug: str):
        post = blog.get_post(app.config["BLOG_DIR"], slug)
        if not post:
            abort(404)
        path = f"/blog/{slug}"
        return render_template(
            "blog_post.html",
            meta=_meta(
                post.title, post.description, path,
                og_type="article",
                jsonld=[
                    {
                        "@context": "https://schema.org",
                        "@type": "BlogPosting",
                        "headline": post.title,
                        "description": post.description,
                        "datePublished": post.date.isoformat(),
                        "inLanguage": "he-IL",
                        "mainEntityOfPage": _canonical(path),
                        "publisher": {"@type": "Organization", "name": app.config["SITE_NAME"]},
                    },
                    _breadcrumbs(
                        (app.config["SITE_NAME"], "/"), ("בלוג", "/blog"), (post.title, path)
                    ),
                ],
            ),
            post=post,
        )

    # -----------------------------------------------------------------------
    # SEO
    # -----------------------------------------------------------------------

    @app.route("/sitemap.xml")
    def sitemap():
        urls: list[tuple[str, str]] = [
            ("/", "daily"), ("/about", "monthly"), ("/zmanim", "daily"),
            ("/ma-nevarech", "monthly"), ("/blog", "weekly"),
        ]
        urls += [(f"/blog/{p.slug}", "yearly") for p in blog.all_posts(app.config["BLOG_DIR"])]
        urls += [(f"/{c['slug']}", "weekly") for c in db.list_categories()]
        urls += [
            (f"/q/{r['code']}", "monthly")
            for r in db.all_question_refs()
        ]

        body = render_template("sitemap.xml", urls=urls, site_url=app.config["SITE_URL"],
                               today=date.today().isoformat(), quote=quote)
        return Response(body, mimetype="application/xml")

    @app.route("/robots.txt")
    def robots():
        lines = [
            "User-agent: *",
            "Allow: /",
            "Disallow: /search",   # עמודי תוצאות אינם תוכן ייחודי
            "Disallow: /api/",
            "",
            f"Sitemap: {_canonical('/sitemap.xml')}",
            "",
        ]
        return Response("\n".join(lines), mimetype="text/plain")

    # -----------------------------------------------------------------------
    # קטגוריות ושאלות — נרשמים אחרונים כי הם התופסים הרחבים ביותר
    # -----------------------------------------------------------------------

    @app.route("/<category_slug>")
    def category(category_slug: str):
        data = db.get_category(category_slug)
        if not data:
            abort(404)
        questions = db.questions_in_category(data["id"])
        path = f"/{category_slug}"

        # חלוקה לתת-נושאים. הסדר הוא סדר ההופעה הראשונה ולא סדר שרירותי:
        # השאלות נכתבו לפי סדר הלימוד בנושא, וכך גם ייקראו. קטגוריה שאין
        # בה תת-נושאים מקבלת קבוצה אחת בלי כותרת, ולכן העמוד לא משתנה
        # עבור עשרים הקטגוריות הקטנות.
        sections: list[dict[str, Any]] = []
        index: dict[str, dict[str, Any]] = {}
        for item in questions:
            name = (item.get("topic") or "").strip()
            group = index.get(name)
            if group is None:
                group = {"name": name, "slug": f"t{len(sections) + 1}", "questions": []}
                index[name] = group
                sections.append(group)
            group["questions"].append(item)
        if len(sections) < 2:
            sections = []
        return render_template(
            "category.html",
            meta=_meta(
                data["name"],
                data["meta_description"] or f"שאלות ותשובות בנושא {data['name']}.",
                path,
                jsonld=[_breadcrumbs((app.config["SITE_NAME"], "/"), (data["name"], path))],
            ),
            category=data,
            questions=questions,
            sections=sections,
        )

    @app.route("/q/<code>")
    @app.route("/q/<code>/<path:decoration>")
    def question(code: str, decoration: str | None = None):
        """עמוד השאלה. הכתובת הקבועה היא ``/q/<code>`` ותו לא.

        הסיומת הדקורטיבית מתקבלת כדי שאפשר יהיה לפרסם קישור קריא
        (``/q/k7m2/מוקצה``), אבל היא לא חלק מהזהות: היא מופנית מיד אל
        הכתובת הנקייה, וכך קיים לעמוד canonical אחד בלבד.
        """
        if not codes.is_code(code):
            abort(404)
        data = db.get_question_by_code(code)
        if not data:
            abort(404)
        if decoration is not None:
            return redirect(url_for("question", code=code), code=301)

        category_slug = data["category_slug"]
        path = f"/q/{code}"

        # FAQPage — התשובה שנמסרת למנוע החיפוש היא התשובה הישירה יחד עם
        # ההרחבה, בדיוק מה שמופיע בעמוד. אין כאן תוכן שהמשתמש לא רואה.
        answer_text = " ".join([data["short_answer"], *data["body"]])
        return render_template(
            "question.html",
            meta=_meta(
                data["question"],
                data["short_answer"][:155],
                path,
                og_type="article",
                jsonld=[
                    {
                        "@context": "https://schema.org",
                        "@type": "FAQPage",
                        "inLanguage": "he-IL",
                        "mainEntity": [
                            {
                                "@type": "Question",
                                "name": data["question"],
                                "acceptedAnswer": {"@type": "Answer", "text": answer_text},
                            }
                        ],
                    },
                    _breadcrumbs(
                        (app.config["SITE_NAME"], "/"),
                        (data["category_name"], f"/{category_slug}"),
                        (data["question"], path),
                    ),
                ],
            ),
            question=data,
            related=db.related_questions(data),
            neighbours=db.question_neighbours(data["number"]),
        )

    @app.route("/<category_slug>/<question_slug>")
    def legacy_question(category_slug: str, question_slug: str):
        """הכתובת הישנה — ``/shabbat/<slug עברי>``.

        חייבת להישאר: היא זו שנשמרה במועדפים, שותפה בוואטסאפ ונאספה
        לגוגל. 301 קבוע, ולכן מנועי החיפוש מעבירים את הדירוג לכתובת
        החדשה במקום להחזיק שתי כתובות לאותו תוכן.
        """
        data = db.get_question(category_slug, question_slug)
        if not data:
            abort(404)
        return redirect(url_for("question", code=data["code"]), code=301)

    # -----------------------------------------------------------------------
    # שגיאות
    # -----------------------------------------------------------------------

    @app.errorhandler(404)
    def not_found(_error):
        meta = _meta("הדף לא נמצא", "הדף המבוקש אינו קיים באתר.", request.path, noindex=True)
        return render_template("404.html", meta=meta), 404
