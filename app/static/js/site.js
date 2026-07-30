/* ============================================================================
   סוף דבר — התנהגות צד לקוח
   ----------------------------------------------------------------------------
   שלושה דברים בלבד: מצב תצוגה, תיבת החיפוש, ומסנן טבלת הברכות.
   כל השאר מרונדר בשרת, וכל עמוד עובד גם כשה-JavaScript חסום — החיפוש הופך
   לטופס רגיל שנשלח ל-/search, והטבלה פשוט מוצגת במלואה.
   ========================================================================== */
(function () {
  'use strict';

  /* ---------------------------------------------------------------- מצב תצוגה */

  var toggle = document.getElementById('theme-toggle');
  if (toggle) {
    toggle.addEventListener('click', function () {
      var root = document.documentElement;
      var next = root.dataset.theme === 'dark' ? 'light' : 'dark';
      root.dataset.theme = next;
      try { localStorage.setItem('sofdavar-theme', next); } catch (e) { /* מצב פרטי */ }
    });
  }

  /* ------------------------------------------- שיתוף והעתקה בעמוד שאלה */

  var actions = document.querySelector('.qa-actions');
  if (actions) {
    var shareUrl = actions.dataset.shareUrl || location.href;
    var answer = actions.dataset.answer || '';

    var status = actions.querySelector('[data-status]');

    /* הכפתורים הם אייקון בלבד, ולכן המשוב הוא החלפת האייקון בווי —
       ובמקביל הודעה ל-status, שהיא הדרך היחידה שקורא מסך יידע שקרה משהו. */
    function flash(button, message, ok) {
      if (button.dataset.busy) return;
      button.dataset.busy = '1';
      button.classList.add(ok ? 'is-done' : 'is-failed');
      if (status) status.textContent = message;
      setTimeout(function () {
        button.classList.remove('is-done', 'is-failed');
        if (status) status.textContent = '';
        delete button.dataset.busy;
      }, 1800);
    }

    /* execCommand כגיבוי: clipboard API דורש הקשר מאובטח, ובפיתוח מעל
       http הוא פשוט לא קיים. */
    function copy(text) {
      if (navigator.clipboard && window.isSecureContext) {
        return navigator.clipboard.writeText(text);
      }
      return new Promise(function (resolve, reject) {
        var area = document.createElement('textarea');
        area.value = text;
        area.setAttribute('readonly', '');
        area.style.position = 'fixed';
        area.style.opacity = '0';
        document.body.appendChild(area);
        area.select();
        var ok = false;
        try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
        document.body.removeChild(area);
        ok ? resolve() : reject();
      });
    }

    actions.addEventListener('click', function (event) {
      var button = event.target.closest('[data-copy]');
      if (!button) return;
      var text = button.dataset.copy === 'answer' ? answer : shareUrl;
      copy(text).then(
        function () { flash(button, 'הועתק', true); },
        function () { flash(button, 'ההעתקה נכשלה', false); }
      );
    });

    /* Web Share API קיים בעיקר בנייד. נחשף רק כשהוא באמת זמין. */
    var shareButton = actions.querySelector('[data-share]');
    if (shareButton && navigator.share) {
      shareButton.hidden = false;
      shareButton.addEventListener('click', function () {
        navigator.share({
          title: document.title,
          text: answer.split('\n\n')[0],
          url: shareUrl
        }).catch(function () { /* המשתמש ביטל — לא שגיאה */ });
      });
    }
  }

  /* ------------------------------------------------------------ תפריט בנייד */

  var navToggle = document.getElementById('nav-toggle');
  var topbar = document.getElementById('topbar');
  var nav = document.getElementById('nav');

  if (navToggle && topbar && nav) {
    var setNav = function (open) {
      topbar.classList.toggle('topbar--open', open);
      navToggle.setAttribute('aria-expanded', String(open));
      navToggle.setAttribute('aria-label', open ? 'סגור תפריט' : 'פתח תפריט');
    };

    navToggle.addEventListener('click', function () {
      var open = !topbar.classList.contains('topbar--open');
      setNav(open);
      // ה-nav קודם לכפתור ב-DOM, ולכן Tab קדימה מדלג עליו. מעבירים פוקוס
      // ידנית. focus() תוכניתי אינו מדליק :focus-visible, אז למגע ולעכבר
      // אין שינוי ויזואלי.
      if (open) {
        var first = nav.querySelector('a');
        if (first) first.focus();
      }
    });

    document.addEventListener('click', function (event) {
      if (!topbar.classList.contains('topbar--open')) return;
      if (topbar.contains(event.target)) return;  // הבועה מהכפתור עצמו
      setNav(false);
    });

    document.addEventListener('keydown', function (event) {
      if (event.key !== 'Escape') return;
      if (!topbar.classList.contains('topbar--open')) return;
      setNav(false);
      navToggle.focus();
    });

    // יציאה בטאב מהקישור האחרון סוגרת — בלי מלכודת פוקוס.
    nav.addEventListener('focusout', function (event) {
      if (!topbar.classList.contains('topbar--open')) return;
      if (nav.contains(event.relatedTarget) || event.relatedTarget === navToggle) return;
      setNav(false);
    });
  }

  /* -------------------------------------------------------- נרמול עברי משותף */

  var NIQQUD = /[֑-ׇֽֿׁׂׅׄ]/g;
  var PUNCT = /[־׀׃׆׳״'"`]/g;
  var FINALS = { 'ך': 'כ', 'ם': 'מ', 'ן': 'נ', 'ף': 'פ', 'ץ': 'צ' };

  // חייב להתנהג כמו normalize() ב-app/hebrew.py, אחרת המסנן בצד הלקוח
  // ימצא דברים אחרים מהחיפוש בשרת.
  function normalize(value) {
    return String(value || '')
      .normalize('NFD').replace(NIQQUD, '').normalize('NFC')
      .replace(PUNCT, ' ')
      .replace(/[ךםןףץ]/g, function (c) { return FINALS[c]; })
      .toLowerCase()
      .replace(/\s+/g, ' ')
      .trim();
  }

  /* -------------------------------------------------------------- תיבת החיפוש */

  var form = document.getElementById('search');
  if (form) {
    var input = document.getElementById('search-input');
    var panel = document.getElementById('search-panel');
    var status = document.getElementById('search-status');
    var clear = document.getElementById('search-clear');

    var results = [];
    var activeIndex = -1;
    var timer = null;
    var sequence = 0;

    var topbarEl = document.getElementById('topbar');
    var fieldEl = form.querySelector('.search__field');

    // המקלדת בנייד מכסה את חצי המסך התחתון. visualViewport הוא היחיד
    // שיודע כמה שטח באמת נשאר — layout viewport לא משתנה כשהיא נפתחת.
    function fitPanel() {
      var viewport = window.visualViewport;
      var space = (viewport ? viewport.height : window.innerHeight)
        - fieldEl.getBoundingClientRect().bottom - 24;
      panel.style.setProperty('--search-max', Math.max(160, space) + 'px');
    }

    // מושכים את השדה אל מתחת לכותרת הדביקה כדי שכל השטח שמעל המקלדת יתפנה
    // לרשימה. התנאי מבטיח שהגלילה לעולם לא קופצת אחורה.
    function liftField() {
      if (!window.matchMedia('(max-width: 860px)').matches) return;
      var bar = topbarEl ? topbarEl.offsetHeight : 0;
      var y = form.getBoundingClientRect().top + window.scrollY - bar - 8;
      if (y > window.scrollY + 4) window.scrollTo({ top: y, behavior: 'smooth' });
    }

    input.addEventListener('focus', liftField);
    if (window.visualViewport) {
      window.visualViewport.addEventListener('resize', fitPanel);
      window.visualViewport.addEventListener('scroll', fitPanel);
    }

    function setExpanded(open) {
      input.setAttribute('aria-expanded', String(open));
      panel.hidden = !open;
      if (open) fitPanel();
      if (!open) {
        activeIndex = -1;
        input.removeAttribute('aria-activedescendant');
      }
    }

    function close() { setExpanded(false); }

    function setActive(index) {
      var options = panel.querySelectorAll('.search__option');
      if (!options.length) return;

      // גלילה מעגלית: מלמטה חוזרים לראש הרשימה ולהפך.
      activeIndex = (index + options.length) % options.length;
      for (var i = 0; i < options.length; i++) {
        var on = i === activeIndex;
        options[i].classList.toggle('is-active', on);
        options[i].setAttribute('aria-selected', String(on));
        if (on) {
          input.setAttribute('aria-activedescendant', options[i].id);
          options[i].scrollIntoView({ block: 'nearest' });
        }
      }
    }

    function render(items, query) {
      results = items;
      activeIndex = -1;
      panel.innerHTML = '';

      if (!items.length) {
        var empty = document.createElement('li');
        empty.className = 'search__empty';
        empty.textContent = 'לא נמצאו תוצאות';
        panel.appendChild(empty);
        status.textContent = 'לא נמצאו תוצאות';
        setExpanded(true);
        return;
      }

      items.forEach(function (item, index) {
        var li = document.createElement('li');
        li.setAttribute('role', 'presentation');

        var link = document.createElement('a');
        link.className = 'search__option';
        link.id = 'search-option-' + index;
        link.setAttribute('role', 'option');
        link.setAttribute('aria-selected', 'false');
        // combobox לפי ARIA 1.2: ניווט בחצים בלבד, ו-Tab יוצא מהווידג'ט
        // במקום לעבור אחת-אחת על עשר ההצעות.
        link.tabIndex = -1;
        link.href = item.url;

        var badge = document.createElement('span');
        badge.className = 'search__badge search__badge--' + item.kind;
        badge.textContent = item.kind_label;
        link.appendChild(badge);

        var text = document.createElement('span');
        text.className = 'search__text';

        var title = document.createElement('span');
        title.className = 'search__title';
        title.textContent = item.title;
        text.appendChild(title);

        var meta = document.createElement('span');
        meta.className = 'search__meta';
        meta.textContent = item.subtitle;
        text.appendChild(meta);

        link.appendChild(text);

        if (item.number) {
          var number = document.createElement('span');
          number.className = 'search__number';
          number.textContent = '#' + item.number;
          link.appendChild(number);
        }

        li.appendChild(link);
        panel.appendChild(li);
      });

      status.textContent = items.length + ' תוצאות עבור ' + query;
      setExpanded(true);
    }

    function fetchResults(query) {
      // כל בקשה מקבלת מספר סידורי, כדי שתשובה איטית של הקלדה קודמת
      // לא תדרוס תוצאה חדשה יותר.
      var current = ++sequence;
      fetch('/api/search?q=' + encodeURIComponent(query), {
        headers: { 'Accept': 'application/json' }
      })
        .then(function (response) { return response.ok ? response.json() : null; })
        .then(function (data) {
          if (!data || current !== sequence) return;
          render(data.results || [], query);
        })
        .catch(function () { /* בעיית רשת — הטופס עדיין נשלח ל-/search */ });
    }

    input.addEventListener('input', function () {
      var query = input.value.trim();
      form.classList.toggle('search--filled', query.length > 0);

      clearTimeout(timer);
      // תו אחד מספיק: החיפוש בשרת מהיר, וההשלמה אמורה להתחיל מיד.
      if (normalize(query).length < 1) {
        close();
        return;
      }
      timer = setTimeout(function () { fetchResults(query); }, 140);
    });

    input.addEventListener('keydown', function (event) {
      var open = input.getAttribute('aria-expanded') === 'true';

      switch (event.key) {
        case 'ArrowDown':
          event.preventDefault();
          if (open) setActive(activeIndex + 1);
          else if (normalize(input.value).length >= 1) fetchResults(input.value.trim());
          break;
        case 'ArrowUp':
          event.preventDefault();
          if (open) setActive(activeIndex - 1);
          break;
        case 'Home':
          if (open) { event.preventDefault(); setActive(0); }
          break;
        case 'End':
          if (open) { event.preventDefault(); setActive(results.length - 1); }
          break;
        case 'Enter':
          // בלי הצעה מסומנת, Enter שולח את הטופס לעמוד התוצאות המלא.
          if (open && activeIndex >= 0 && results[activeIndex]) {
            event.preventDefault();
            window.location.href = results[activeIndex].url;
          }
          break;
        case 'Escape':
          if (open) { event.preventDefault(); close(); }
          break;
      }
    });

    if (clear) {
      clear.addEventListener('click', function () {
        input.value = '';
        form.classList.remove('search--filled');
        close();
        input.focus();
      });
    }

    document.addEventListener('click', function (event) {
      if (!form.contains(event.target)) close();
    });

    input.addEventListener('focus', function () {
      if (results.length && normalize(input.value).length >= 1) setExpanded(true);
    });

    if (input.value.trim()) form.classList.add('search--filled');

    /* ------------------------------------------------ רמז ההקלדה שבשדה */

    var hint = document.getElementById('search-hint');
    if (hint) {
      var hintLine = hint.querySelector('.search__hint-line');
      var started = false;
      var focused = false;

      /* offsetWidth ולא getBoundingClientRect: ה-rect הוא המלבן *החזותי*
         ולכן הוא מוכפל בכל transform של הורה — והשכבה עצמה יושבת על
         translateY(-50%). offsetWidth הוא מידת פריסה, שקופה ל-transform,
         וגם כבר מעגלת כלפי מעלה. 3px נוספים הם רוחב הסמן. */
      var measureHint = function () {
        var width = hintLine.offsetWidth;
        // אפס = הרמז אינו מרונדר כרגע (hidden לפני ההתחלה, או display:none
        // בזמן שיש טקסט בשדה). מדידה כזאת הייתה נועלת --tw על 3px.
        if (!width) return;
        hint.style.setProperty('--tw', width + 3 + 'px');
      };

      var startHint = function () {
        hint.hidden = false;
        measureHint();
        // רק כאן מוחקים את ה-placeholder. עד לרגע הזה הוא הרמז היחיד,
        // ומחיקה מוקדמת הייתה משאירה שדה ריק עד שהפונטים נטענים.
        input.placeholder = '';
        form.classList.add('search--hinting');
        if (focused) form.classList.add('search--hinted');
        started = true;
      };

      // פוקוס באמצע ההקלדה: שני סמנים מהבהבים באותו שדה קוראים כתקלה.
      // הדגל נשמר גם אם הפוקוס הגיע לפני ההתחלה (autofocus ב-/search).
      input.addEventListener('focus', function () {
        focused = true;
        if (started) form.classList.add('search--hinted');
      });

      // מחכים לגלילה אל השדה — בעמוד הקטגוריה הוא באמצע העמוד, ואנימציה
      // שרצה מחוץ למסך פשוט הולכת לאיבוד.
      var observeHint = function () {
        if (!window.IntersectionObserver) { startHint(); return; }
        var io = new IntersectionObserver(function (entries) {
          if (!entries[0].isIntersecting) return;
          io.disconnect();                 // פעם אחת בלבד
          startHint();
        }, { threshold: 0.6 });
        io.observe(form);
      };

      /* חובה לחכות לפונטים — מדידה לפני שהם נטענים מודדת את פונט ברירת
         המחדל, והסמן חונה אחרי סוף הטקסט. בלי תקרת זמן הרמז היה תלוי
         ב-fonts.googleapis.com, ואם הוא חסום — לתמיד. */
      if (document.fonts && document.fonts.ready) {
        Promise.race([
          document.fonts.ready,
          new Promise(function (resolve) { setTimeout(resolve, 1500); })
        ]).then(observeHint);

        // הגיעו אחרי שכבר מדדנו? למדוד שוב. hintType קורא את var(--tw)
        // מחדש, ולכן הרוחב מתעדכן גם באמצע האנימציה וגם אחריה.
        if (document.fonts.addEventListener) {
          document.fonts.addEventListener('loadingdone', measureHint);
        }
      } else {
        observeHint();
      }

      // הזנב ("ותשובות") יורד במסך צר, ולכן הרוחב הסופי משתנה עם המידה.
      window.addEventListener('resize', measureHint);
    }
  }

  /* ------------------------------------------------------- מסנן טבלת הברכות */

  var filter = document.getElementById('beracha-filter');
  var table = document.getElementById('beracha-table');
  if (filter && table) {
    var rows = Array.prototype.slice.call(table.tBodies[0].rows);
    var chips = document.getElementById('beracha-categories');
    var noResults = document.getElementById('beracha-empty');
    var tableStatus = document.getElementById('beracha-status');
    var category = '';

    // מנרמלים פעם אחת בטעינה ולא בכל הקלדה.
    rows.forEach(function (row) {
      row.dataset.haystack = normalize(
        row.dataset.name + ' ' + (row.dataset.aliases || '')
      );
    });

    function apply() {
      var needle = normalize(filter.value);
      var visible = 0;

      rows.forEach(function (row) {
        var matchesText = !needle || row.dataset.haystack.indexOf(needle) !== -1;
        var matchesCategory = !category || row.dataset.category === category;
        var show = matchesText && matchesCategory;
        row.hidden = !show;
        if (show) visible++;
      });

      if (noResults) noResults.hidden = visible > 0;
      if (tableStatus) tableStatus.textContent = visible + ' מאכלים מוצגים';
    }

    filter.addEventListener('input', apply);

    if (chips) {
      chips.addEventListener('click', function (event) {
        var button = event.target.closest('.chip');
        if (!button) return;
        category = button.dataset.category || '';
        chips.querySelectorAll('.chip').forEach(function (chip) {
          chip.setAttribute('aria-pressed', String(chip === button));
        });
        apply();
      });
    }
  }
})();
