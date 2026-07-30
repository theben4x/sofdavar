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
    Flask, Response, abort, current_app, jsonify, redirect, render_template,
    request, url_for,
)
from markupsafe import Markup, escape

from . import blog, db, parasha, zmanim
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
        # הרצועה שמעל הפוטר יושבת ב-base.html ולכן מוצגת בכל עמוד. שני
        # הנתונים נלקחים מאותה שבת אחת, אחרת בערב שבת אחרי הצאת היו
        # מוצגים פרשה של שבוע אחד וזמן הדלקה של אחר.
        shabbat = zmanim.upcoming_shabbat(zmanim.DEFAULT_CITY)
        return {
            "site_name": app.config["SITE_NAME"],
            "site_tagline": app.config["SITE_TAGLINE"],
            "verse": app.config["VERSE"],
            "verse_source": app.config["VERSE_SOURCE"],
            "verse_emphasis": app.config["VERSE_EMPHASIS"],
            "home_lede": app.config["HOME_LEDE"],
            "home_lede_emphasis": app.config["HOME_LEDE_EMPHASIS"],
            "nav_categories": db.list_categories(),
            "current_year": date.today().year,
            "current_path": request.path,
            "strip_parasha": parasha.label(shabbat["saturday"]),
            "strip_shabbat": shabbat,
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
        return render_template(
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
            shabbat=zmanim.upcoming_shabbat(zmanim.DEFAULT_CITY),
        )

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
            return jsonify({"query": query, "results": []})
        return jsonify({"query": query, "results": db.search(query, limit=10)})

    @app.route("/search")
    def search_page():
        """תוצאות מלאות. קיים גם כדי שהחיפוש יעבוד בלי JavaScript."""
        query = (request.args.get("q") or "").strip()
        results = db.search(query, limit=50) if normalize(query).strip() else []
        return render_template(
            "search.html",
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
        """קיצור לציטוט: /q/47 מפנה לכתובת הקנונית של שאלה 47."""
        question = db.get_question_by_number(number)
        if not question:
            abort(404)
        return redirect(
            url_for(
                "question",
                category_slug=question["category_slug"],
                question_slug=question["slug"],
            ),
            code=301,
        )

    # -----------------------------------------------------------------------
    # זמנים
    # -----------------------------------------------------------------------

    @app.route("/zmanim")
    def zmanim_page():
        city = zmanim.get_city(request.args.get("city"))
        try:
            day = date.fromisoformat(request.args["date"]) if "date" in request.args else None
        except ValueError:
            day = None
        day = day or datetime.now(zmanim.ISRAEL_TZ).date()

        meta_copy = db.get_meta("copy", {}) or {}
        return render_template(
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
            (f"/{r['category_slug']}/{r['question_slug']}", "monthly")
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
        )

    @app.route("/<category_slug>/<question_slug>")
    def question(category_slug: str, question_slug: str):
        data = db.get_question(category_slug, question_slug)
        if not data:
            abort(404)
        path = f"/{category_slug}/{question_slug}"

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

    # -----------------------------------------------------------------------
    # שגיאות
    # -----------------------------------------------------------------------

    @app.errorhandler(404)
    def not_found(_error):
        meta = _meta("הדף לא נמצא", "הדף המבוקש אינו קיים באתר.", request.path, noindex=True)
        return render_template("404.html", meta=meta), 404
