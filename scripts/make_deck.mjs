/**
 * בונה את מצגת הפרויקט של "סוף דבר" כקובץ PPTX ניתן לעריכה.
 *
 * כללי ה-RTL שמיושמים כאן:
 *  1. כל תיבת טקסט שיש בה עברית מקבלת rtlMode:true ויישור לימין — זה מה
 *     שכותב rtl="1" ב-<a:pPr>, והוא שקובע את כיוון הבסיס של הפסקה.
 *  2. שורה שכולה לטינית או מספרים (ערך בכרטיס סטטיסטיקה, כותרת עמודה
 *     Recall@1) מקבלת rtlMode:false — כך היא נשארת LTR ולא נתלית הפוך.
 *  3. אין get_display ואין תווי כיווניות: PowerPoint מריץ את אלגוריתם
 *     ה-bidi בעצמו, ועיבוד מוקדם היה הופך את הסדר פעמיים.
 *  4. חצים (←) יושבים בתיבה עם rtlMode:false, כי U+2190 הוא תו ממוראה
 *     ובהקשר RTL היה מתהפך לכיוון ההפוך.
 *  5. טבלאות: PowerPoint מסדר עמודות משמאל לימין תמיד, ולכן הן נכתבות
 *     כאן בסדר לוגי (העמודה הראשונה = הימנית) ומתהפכות ב-rtlTable.
 *
 * הרצה:  npm install pptxgenjs  &&  node make_deck.mjs
 */

import pptxgen from 'pptxgenjs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.dirname(HERE);
const ASSETS = path.join(ROOT, 'docs', 'deck-assets');   // צילומי המסך שבמצגת
const OUT = process.argv[2] || path.join(ROOT, 'docs', 'סוף דבר — מצגת הפרויקט.pptx');

/* ------------------------------------------------------------------ ערכת עיצוב
   הצבעים לקוחים מערכת הצבעים של האתר עצמו (app/static/site.css).
   הזהב העמוק משמש לטקסט קטן, כי הוא זה שעובר AA על רקע הקרם. */
const PAPER = 'F5F3EE', SURFACE = 'FBF9F5', INK = '14140F', MUTED = '6E6E66';
const GOLD = 'A67C2E', GOLD_DEEP = '6F4F17', GOLD_LIGHT = 'C9A961';
const RULE = 'E4DCC9', VEIL = 'F2EBDA', VEIL_LINE = 'DCCCA4';
const DARK = '16160F', CREAM = 'F0EEE6', CREAM_DIM = 'B3AE9E';

// גופנים שקיימים בכל התקנת Windows/Office — כדי שהמצגת תיפתח זהה גם אצל המרצה.
const SERIF = 'David';      // מקביל ל-Noto Serif Hebrew שבאתר
const SANS = 'Segoe UI';    // מקביל ל-Heebo

const W = 10, H = 5.625;            // 16:9 באינצ'ים
const M = 0.62;                     // שוליים
const CW = W - 2 * M;               // רוחב התוכן

const HEB = /[֐-׿]/;

const pptx = new pptxgen();
pptx.layout = 'LAYOUT_16x9';
pptx.rtlMode = true;
pptx.title = 'סוף דבר — מצגת הפרויקט';
pptx.subject = 'מאגר שאלות ותשובות בהלכה עם מנוע חיפוש היברידי';
pptx.company = 'סוף דבר';

let pageNo = 0;

/* ------------------------------------------------------------- תיקון כיווניות
   pptxgenjs מסמן rtl="1" על <a:pPr> בלבד, וכל מחרוזת נכנסת לריצה אחת. זה
   לא מספיק ל-PowerPoint: אסימון שמערב אותיות וספרות מתהפך («512MB» מודפס
   «MB512»), ורווח שצמוד לגבול בין לטינית לעברית נגזם («Model2Vecהיא»).
   שני הפגמים נמדדו מול PowerPoint עצמו, וגם התרופות שלא עבדו — LRM, LRE,
   ו-U+2066‑2069 שמצוירים כריבועים. מה שכן עובד הוא פיצול לריצות לפי כתב
   עם rtl מפורש בכל ריצה, וזה נעשה אחרי הכתיבה ב-fix_pptx_bidi.py.
   כאן רק מסומנת שפת הריצה, כדי ש-PowerPoint לא יסמן כל מילה עברית
   כשגיאת כתיב באנגלית. */
const heOpts = (text, opts = {}) =>
  (HEB.test(String(text)) && !opts.lang ? { ...opts, lang: 'he-IL' } : opts);

function wrap(s) {
  const addText = s.addText.bind(s), addTable = s.addTable.bind(s);
  s.addText = (text, opts = {}) => (Array.isArray(text)
    ? addText(text.map(o => ({ ...o, options: heOpts(o.text, o.options) })), opts)
    : addText(text, heOpts(text, opts)));
  s.addTable = (rows, opts = {}) => addTable(rows.map(r => r.map(c => (
    typeof c === 'string'
      ? { text: c, options: heOpts(c) }
      : { ...c, options: heOpts(c.text, c.options) }
  ))), opts);
  return s;
}

/* ----------------------------------------------------------------- עוזרי בנייה */

/** שקף תוכן סטנדרטי: פס זהב, מותג-על, כותרת, קו מפריד וכותרת תחתונה. */
function base(kicker, title) {
  const s = wrap(pptx.addSlide());
  s.background = { color: PAPER };
  s.addShape(pptx.ShapeType.rect, { x: 0, y: 0, w: W, h: 0.05, fill: { color: GOLD_DEEP } });

  if (kicker) {
    s.addText(kicker, {
      x: M, y: 0.32, w: CW, h: 0.24, align: 'right', rtlMode: true, valign: 'top',
      fontFace: SANS, fontSize: 10.5, bold: true, color: GOLD_DEEP, margin: 0,
    });
  }
  if (title) {
    s.addText(title, {
      x: M, y: 0.58, w: CW, h: 0.58, align: 'right', rtlMode: true, valign: 'top',
      fontFace: SERIF, fontSize: 27, bold: true, color: INK, margin: 0,
    });
  }
  s.addShape(pptx.ShapeType.rect, { x: M, y: 1.29, w: CW, h: 0.011, fill: { color: RULE } });

  s.addText('סוף דבר · מצגת הפרויקט', {
    x: W - M - 4, y: 5.18, w: 4, h: 0.25, align: 'right', rtlMode: true,
    fontFace: SANS, fontSize: 8.5, color: MUTED, margin: 0,
  });
  s.addText(String(++pageNo), {
    x: M, y: 5.18, w: 1.2, h: 0.25, align: 'left', rtlMode: false,
    fontFace: SANS, fontSize: 8.5, color: MUTED, margin: 0,
  });
  return s;
}

/** פסקת פתיח מתחת לכותרת. */
function lead(s, text, { y = 1.48, h = 0.6, size = 12.5, color = INK, w = CW, x = M } = {}) {
  s.addText(text, {
    x, y, w, h, align: 'right', rtlMode: true, valign: 'top',
    fontFace: SANS, fontSize: size, color, margin: 0, lineSpacingMultiple: 1.3,
  });
}

/** רשימת תבליטים ל-addText, בסדר ובכיוון הנכונים. */
function bulletList(items, { size = 10.5, color = INK, after = 5, code = '2022' } = {}) {
  return items.map((t, i) => ({
    text: t,
    options: {
      bullet: { code, indent: 12 },
      fontFace: SANS, fontSize: size, color, rtlMode: true, align: 'right',
      paraSpaceAfter: i === items.length - 1 ? 0 : after,
      breakLine: true,
    },
  }));
}

/** כרטיס: מלבן מעוגל עם כותרת וגוף. */
function card(s, { x, y, w, h, title, body, items, fill = SURFACE, line = RULE,
                   titleColor = GOLD_DEEP, size = 10.5, titleSize = 14 }) {
  s.addShape(pptx.ShapeType.roundRect, {
    x, y, w, h, rectRadius: 0.09, fill: { color: fill }, line: { color: line, width: 1 },
  });
  const pad = 0.2;
  let cy = y + 0.15;
  if (title) {
    s.addText(title, {
      x: x + pad, y: cy, w: w - 2 * pad, h: 0.3, align: 'right', rtlMode: true, valign: 'top',
      fontFace: SERIF, fontSize: titleSize, bold: true, color: titleColor, margin: 0,
    });
    cy += 0.42;
  }
  if (body) {
    const bh = items ? 0.62 : (y + h - 0.14) - cy;
    s.addText(body, {
      x: x + pad, y: cy, w: w - 2 * pad, h: bh, align: 'right', rtlMode: true, valign: 'top',
      fontFace: SANS, fontSize: size, color: INK, margin: 0, lineSpacingMultiple: 1.25,
    });
    cy += bh + 0.06;
  }
  if (items) {
    s.addText(bulletList(items, { size: size - 0.5 }), {
      x: x + pad, y: cy, w: w - 2 * pad, h: (y + h - 0.14) - cy,
      align: 'right', rtlMode: true, valign: 'top', margin: 0,
    });
  }
}

/** אריח מספר: ערך גדול ותווית. */
function stat(s, { x, y, w, value, label, h = 0.92 }) {
  s.addShape(pptx.ShapeType.roundRect, {
    x, y, w, h, rectRadius: 0.08, fill: { color: VEIL }, line: { color: VEIL_LINE, width: 1 },
  });
  s.addText(value, {
    x, y: y + 0.09, w, h: 0.45, align: 'center', rtlMode: false, valign: 'middle',
    fontFace: SERIF, fontSize: 24, bold: true, color: GOLD_DEEP, margin: 0,
  });
  s.addText(label, {
    x, y: y + 0.53, w, h: 0.3, align: 'center', rtlMode: true, valign: 'top',
    fontFace: SANS, fontSize: 9.5, color: MUTED, margin: 0,
  });
}

/** רצועת הדגשה רוחבית. */
function strip(s, { x = M, y, w = CW, h = 0.6, text, size = 11.5, fill = VEIL,
                    line = VEIL_LINE, color = INK, bold = false }) {
  s.addShape(pptx.ShapeType.roundRect, {
    x, y, w, h, rectRadius: 0.08, fill: { color: fill }, line: { color: line, width: 1 },
  });
  s.addText(text, {
    x: x + 0.2, y, w: w - 0.4, h, align: 'right', rtlMode: true, valign: 'middle',
    fontFace: SANS, fontSize: size, bold, color, margin: 0, lineSpacingMultiple: 1.2,
  });
}

/** מסגרת זהב דקה מאחורי צילום מסך. */
function shot(s, { file, x, y, w, aspect }) {
  const h = w / aspect;
  s.addShape(pptx.ShapeType.rect, {
    x: x - 0.035, y: y - 0.035, w: w + 0.07, h: h + 0.07,
    fill: { color: 'FFFFFF' }, line: { color: RULE, width: 1 },
    shadow: { type: 'outer', color: '8A7A52', blur: 8, offset: 2, angle: 90, opacity: 0.18 },
  });
  s.addImage({ path: path.join(ASSETS, file), x, y, w, h });
  return h;
}

/** טבלה בסדר לוגי RTL: העמודה הראשונה במערך היא הימנית במצגת. */
function rtlTable(s, { x = M, y, w = CW, colW, head, rows, fontSize = 10, rowH = 0.29 }) {
  const flip = a => [...a].reverse();
  const last = head.length - 1;
  const cell = (t, i, opts) => ({
    text: t,
    options: {
      align: i === last ? 'right' : 'center',
      rtlMode: HEB.test(t),
      fontFace: SANS,
      ...opts,
    },
  });
  const headRow = flip(head).map((t, i) => cell(t, i, {
    bold: true, color: GOLD_DEEP, fill: { color: VEIL },
  }));
  const bodyRows = rows.map(r => flip(r).map((t, i) => cell(t, i, { color: INK })));
  s.addTable([headRow, ...bodyRows], {
    x, y, w, colW: flip(colW), rowH,
    fontFace: SANS, fontSize, valign: 'middle', color: INK,
    border: { type: 'solid', color: RULE, pt: 0.75 },
    margin: [2, 8, 2, 8],
  });
}

/* ================================================================ 1 · שער */
{
  const s = wrap(pptx.addSlide());
  s.background = { color: DARK };
  s.addShape(pptx.ShapeType.rect, {
    x: 0.28, y: 0.26, w: W - 0.56, h: H - 0.52,
    fill: { type: 'solid', color: DARK }, line: { color: GOLD_DEEP, width: 1 },
  });

  s.addText('◆', {
    x: 0, y: 0.62, w: W, h: 0.3, align: 'center', rtlMode: false,
    fontFace: SANS, fontSize: 12, color: GOLD, margin: 0,
  });
  s.addText('סוף דבר', {
    x: 0, y: 0.95, w: W, h: 0.9, align: 'center', rtlMode: true, valign: 'middle',
    fontFace: SERIF, fontSize: 50, bold: true, color: CREAM, margin: 0,
  });
  s.addText('סוֹף דָּבָר הַכֹּל נִשְׁמָע אֶת הָאֱלֹהִים יְרָא\nוְאֶת מִצְוֺתָיו שְׁמוֹר כִּי זֶה כׇּל הָאָדָם.', {
    x: 1.5, y: 1.95, w: 7, h: 0.85, align: 'center', rtlMode: true, valign: 'top',
    fontFace: SERIF, fontSize: 15, color: GOLD_LIGHT, margin: 0, lineSpacingMultiple: 1.35,
  });
  s.addText('קהלת יב, יג', {
    x: 0, y: 2.82, w: W, h: 0.25, align: 'center', rtlMode: true,
    fontFace: SANS, fontSize: 9.5, color: CREAM_DIM, margin: 0,
  });
  s.addShape(pptx.ShapeType.rect, { x: (W - 2.2) / 2, y: 3.2, w: 2.2, h: 0.012, fill: { color: GOLD_DEEP } });

  s.addText('מאגר שאלות ותשובות בהלכה וביהדות', {
    x: 0, y: 3.42, w: W, h: 0.38, align: 'center', rtlMode: true, valign: 'top',
    fontFace: SANS, fontSize: 16, color: CREAM, margin: 0,
  });
  s.addText('אתר תוכן עם מנוע חיפוש היברידי — לקסיקלי וסמנטי — ומודל שפה שרץ מקומית, בלי ענן ובלי עלות', {
    x: 1.1, y: 3.82, w: 7.8, h: 0.34, align: 'center', rtlMode: true, valign: 'top',
    fontFace: SANS, fontSize: 10.5, color: CREAM_DIM, margin: 0,
  });

  s.addShape(pptx.ShapeType.rect, { x: (W - 1.1) / 2, y: 4.42, w: 1.1, h: 0.011, fill: { color: '3A3527' } });
  s.addText('מגיש: ⟨שם⟩   ·   ⟨שם הקורס⟩   ·   מרצה: ⟨שם⟩   ·   ⟨תאריך⟩', {
    x: 0, y: 4.62, w: W, h: 0.3, align: 'center', rtlMode: true,
    fontFace: SANS, fontSize: 10, color: CREAM_DIM, margin: 0,
  });
  pageNo = 1;
}

/* =============================================================== 2 · הבעיה */
{
  const s = base('01 · הבעיה', 'שאלה שצריכה תשובה עכשיו');
  lead(s, 'מי ששואל שאלה בהלכה שואל אותה ברגע מסוים, בניסוח שלו, ובלי לדעת איך היא נקראת בספר. שלושה דברים עומדים בינו לבין התשובה.',
    { y: 1.46, h: 0.56 });

  const w = 2.78, gap = 0.21;
  const xs = [M + 2 * (w + gap), M + (w + gap), M];   // הראשון מימין
  const cards = [
    ['הרגע', 'שבת נכנסת בעוד רבע שעה, המאכל כבר על הפלטה והאורח בדלת. אין זמן לחפש בספר, ולא תמיד יש את מי לשאול.'],
    ['החיפוש', 'מנוע חיפוש כללי מחזיר פורומים, תשובות סותרות ושו״ת סרוק. אין מקום אחד שנותן תשובה קצרה, עם מקור ועם המנהגים.'],
    ['העברית', 'ניקוד, אותיות סופיות ואותיות שימוש שוברות כל התאמת טקסט פשוטה: מי שמקליד «בשבת» לא ימצא שאלה שכתוב בה «שבת».'],
  ];
  cards.forEach(([t, b], i) => card(s, { x: xs[i], y: 2.18, w, h: 2.18, title: t, body: b, size: 11 }));
}

/* =============================================================== 3 · הרעיון */
{
  const s = base('02 · הרעיון', 'מאגר אחד, בשפה של השואל');
  s.addShape(pptx.ShapeType.roundRect, {
    x: M, y: 1.46, w: CW, h: 1.16, rectRadius: 0.1,
    fill: { color: VEIL }, line: { color: GOLD, width: 1.25 },
  });
  s.addText('מאגר עברי אחד של שאלות ותשובות בהלכה — כתובות מראש, עם מקורות ועם מנהגי אשכנז וספרד — שאפשר למצוא אותן בניסוח היומיומי של השאלה, ולא במונחים המקצועיים שלה.', {
    x: M + 0.28, y: 1.46, w: CW - 0.56, h: 1.16, align: 'right', rtlMode: true, valign: 'middle',
    fontFace: SERIF, fontSize: 16, color: INK, margin: 0, lineSpacingMultiple: 1.3,
  });

  const w = 2.78, gap = 0.21;
  const xs = [M + 2 * (w + gap), M + (w + gap), M];
  const tiles = [
    ['תשובה קצרה קודם', 'משפט אחד חד-משמעי בראש העמוד, ורק אחריו ההרחבה, המקורות והמנהגים. מי שממהר מקבל תשובה בשורה אחת.'],
    ['חיפוש בשפה טבעית', 'המשתמש מקליד כמו שהוא מדבר. הגישור אל המונח ההלכתי הוא תפקיד המערכת, לא תפקידו.'],
    ['לדעת לשתוק', 'כשאין תשובה במאגר, המערכת אומרת «לא מצאתי» — ולא מגישה את התוצאה הכי קרובה כאילו היא התשובה.'],
  ];
  tiles.forEach(([t, b], i) => card(s, { x: xs[i], y: 2.84, w, h: 1.62, title: t, body: b, size: 10.5, titleSize: 13 }));
}

/* =============================================================== 4 · התוכן */
{
  const s = base('03 · התוכן', '2,125 שאלות בעשרים ושבעה נושאים');

  const tw = (CW - 3 * 0.18) / 4;
  [['2,125', 'שאלות במאגר'], ['27', 'נושאים'], ['4', 'תווים בכתובת קבועה'], ['0 ₪', 'עלות תפעול חודשית']]
    .forEach(([v, l], i) => stat(s, { x: M + (3 - i) * (tw + 0.18), y: 1.44, w: tw, value: v, label: l }));

  s.addText('כל שאלה היא רשומה אחת:', {
    x: 5.4, y: 2.56, w: 3.98, h: 0.26, align: 'right', rtlMode: true, valign: 'top',
    fontFace: SERIF, fontSize: 13, bold: true, color: GOLD_DEEP, margin: 0,
  });
  s.addText(bulletList([
    'נוסח השאלה כפי שהיא נשאלת בפועל',
    'תשובה קצרה — משפט אחד חד-משמעי',
    'שתי פסקאות הרחבה',
    'מקורות בני-אימות: שולחן ערוך, משנה ברורה, רמ״א',
    'מנהג אשכנז וספרד היכן שיש הבדל ממשי',
    'שבע עד עשר מילות חיפוש בניסוח דיבור',
    'קוד כתובת קבוע בן ארבעה תווים: /q/k7m2',
  ], { size: 10.5, after: 4 }), {
    x: 5.4, y: 2.86, w: 3.98, h: 1.66, align: 'right', rtlMode: true, valign: 'top', margin: 0,
  });
  s.addText('לצד המאגר: זמני היום ההלכתיים לכל עיר בחישוב אסטרונומי מקומי, לוח עברי, טבלת «מה נברך» ובלוג.', {
    x: 5.4, y: 4.58, w: 3.98, h: 0.5, align: 'right', rtlMode: true, valign: 'top',
    fontFace: SANS, fontSize: 9.5, color: MUTED, margin: 0, lineSpacingMultiple: 1.2,
  });

  shot(s, { file: 'shot-question.png', x: M, y: 2.62, w: 4.55, aspect: 2.225 });
  s.addText('עמוד שאלה: התשובה הקצרה קודמת לכל השאר.', {
    x: M, y: 4.72, w: 4.55, h: 0.28, align: 'right', rtlMode: true,
    fontFace: SANS, fontSize: 9, color: MUTED, margin: 0,
  });
}

/* =============================================================== 5 · המוצר */
{
  const s = base('04 · המוצר', 'כך זה נראה');
  const h = shot(s, { file: 'shot-home.png', x: M, y: 1.52, w: 5.75, aspect: 1.97 });

  const notes = [
    ['תיבת חיפוש אחת', 'combobox לפי תקן WAI-ARIA: ניווט בחצים, Enter ו-Escape, והכרזת מספר התוצאות לקורא מסך.'],
    ['עובד בלי JavaScript', 'כל עמוד מרונדר בשרת. כשה-JS כבוי, החיפוש נשלח כטופס רגיל וממשיך לעבוד.'],
    ['מצב כהה ובהיר', 'נשמר ב-localStorage בלי הבזק בטעינה. הניגודיות נבדקה מול WCAG AA בשני המצבים.'],
  ];
  notes.forEach(([t, b], i) => {
    const y = 1.52 + i * 1.16;
    s.addText(t, {
      x: 6.62, y, w: 2.76, h: 0.28, align: 'right', rtlMode: true, valign: 'top',
      fontFace: SERIF, fontSize: 13, bold: true, color: GOLD_DEEP, margin: 0,
    });
    s.addText(b, {
      x: 6.62, y: y + 0.3, w: 2.76, h: 0.8, align: 'right', rtlMode: true, valign: 'top',
      fontFace: SANS, fontSize: 10, color: INK, margin: 0, lineSpacingMultiple: 1.22,
    });
  });
  s.addText('עמוד הבית — הפסוק, המאגר ותיבת החיפוש היחידה.', {
    x: M, y: 1.62 + h, w: 5.75, h: 0.28, align: 'right', rtlMode: true,
    fontFace: SANS, fontSize: 9, color: MUTED, margin: 0,
  });
}

/* ============================================================= 6 · ההדגמה */
{
  const s = base('05 · ההדגמה', 'מה שמקלידים אינו מה שכתוב במאגר');
  lead(s, 'השאילתה «אכלתי פיצה מתי מותר המבורגר» אינה חולקת אף מילה עם השאלה שבמאגר — «כמה זמן ממתינים אחרי גבינה לפני אכילת בשר?» — ובכל זאת היא התוצאה הראשונה. הגישור נעשה בשתי דרכים: מילות חיפוש בניסוח דיבור שנכתבות לכל שאלה, ונרמול עברי שמסיר ניקוד ומאחד «בשבת» ל«שבת».',
    { y: 1.44, h: 0.9, size: 12 });
  shot(s, { file: 'shot-search.png', x: 1.9, y: 2.42, w: 6.2, aspect: 2.5 });
  s.addText('צילום מסך מן האתר. שאר התוצאות מגיעות מנושאים אחרים — ברכות, שבת — ולכן שער הראיות הוא שמחליט מה באמת קשור.', {
    x: 1.0, y: 4.99, w: 8.0, h: 0.28, align: 'center', rtlMode: true,
    fontFace: SANS, fontSize: 9, color: MUTED, margin: 0,
  });
}

/* ============================================================== 7 · המנוע */
{
  const s = base('06 · המנוע', 'שתי שכבות חיפוש, ולא אחת');
  const w = 4.27, gap = 0.22;
  card(s, {
    x: M + w + gap, y: 1.44, w, h: 2.5, title: 'לקסיקלי — מילים',
    body: 'SQLite FTS5 עם דירוג bm25. הנרמול העברי מופעל בשני הצדדים — גם על הטקסט שנכנס לאינדקס וגם על השאילתה:',
    items: [
      'ניקוד וטעמי מקרא מוסרים',
      'אותיות סופיות מאוחדות: ך ם ן ף ץ',
      'אותיות שימוש נחתכות — «בשבת» מוצא «שבת»',
      'התאמת תחילית: השלמה כבר מהתו השני',
    ],
  });
  card(s, {
    x: M, y: 1.44, w, h: 2.5, title: 'סמנטי — משמעות',
    body: 'ווקטור אחד לכל שאלה, ודמיון קוסינוס מול כל המאגר בכפל מטריצה יחיד — כמילישנייה:',
    items: [
      'מוצא ניסוח שאין בו אף מילה משותפת',
      'הווקטור נבנה שדה-שדה, במשקלים מפורשים',
      'מוצג באתר כמדור נפרד: «עוד מהמאגר»',
      'בלי מסד ווקטורי, בלי ANN ובלי faiss',
    ],
  });
  strip(s, {
    y: 4.16, h: 0.66,
    text: 'המיזוג — Reciprocal Rank Fusion עם k=60: כל שיטה תורמת ניקוד ההופכי למיקום שנתנה, והסכום מכריע.',
    size: 11.5,
  });
}

/* =========================================================== 8 · המודל */
{
  const s = base('07 · הבינה המלאכותית', 'מודל שפה עברי שרץ אצלנו, בלי ענן');
  lead(s, 'Model2Vec היא שיטת זיקוק: מריצים מודל טרנספורמר על כל אוצר המילים, ושומרים לכל טוקן את הווקטור שיצא — כלומר ממירים רשת עמוקה לטבלת חיפוש אחת. קידוד משפט הוא שליפת שורות וממוצע, במיקרו-שניות ועל CPU.',
    { y: 1.44, h: 0.68, size: 12 });

  const bw = 2.68, bgap = 0.36;
  const steps = [
    ['המורה: DictaBERT', 'מודל עברי ילידי\n127,996 שורות'],
    ['זיקוק Model2Vec', 'טבלת חיפוש אחת\n512 ממדים'],
    ['קוונטיזציה ל-int8', 'מקדם לכל שורה\nהמטריצה: 65.5MB'],
  ];
  steps.forEach(([t, b], i) => {
    const x = M + (2 - i) * (bw + bgap);
    s.addShape(pptx.ShapeType.roundRect, {
      x, y: 2.26, w: bw, h: 0.92, rectRadius: 0.08,
      fill: { color: i === 2 ? VEIL : SURFACE }, line: { color: i === 2 ? VEIL_LINE : RULE, width: 1 },
    });
    s.addText(t, {
      x, y: 2.33, w: bw, h: 0.26, align: 'center', rtlMode: true, valign: 'top',
      fontFace: SERIF, fontSize: 12, bold: true, color: GOLD_DEEP, margin: 0,
    });
    s.addText(b, {
      x, y: 2.62, w: bw, h: 0.5, align: 'center', rtlMode: true, valign: 'top',
      fontFace: SANS, fontSize: 9.5, color: INK, margin: 0, lineSpacingMultiple: 1.15,
    });
    if (i < 2) {
      s.addText('←', {
        x: x - bgap, y: 2.26, w: bgap, h: 0.92, align: 'center', valign: 'middle', rtlMode: false,
        fontFace: SANS, fontSize: 16, color: GOLD, margin: 0,
      });
    }
  });
  s.addText('סך הכול 69MB בתיקייה data/model — קטן מן המודל הרב-לשוני הקודם, ובלי שלב גזימה כלל.', {
    x: M, y: 3.24, w: CW, h: 0.26, align: 'center', rtlMode: true,
    fontFace: SANS, fontSize: 9.5, color: MUTED, margin: 0,
  });

  s.addText(bulletList([
    'למה הוחלף: כל הכשלים שנמדדו היו מאותו סוג — «אייפון» מול «טלפון נייד», «הבגד הלבן עם החוטים» מול «טלית קטן». פער באיכות המודל בעברית, לא במתכון הווקטור.',
    'מה שנמדד: שינויים במתכון עצמו נעו בין 0.132 ל-0.167 ב-MRR מול 0.160 — רעש. מורה רב-לשוני חזק יותר ירד ל-0.128. חמישה מודלים עבריים שונים עברו את הבסיס.',
    'המגבלות שעיצבו את הפתרון: תקרת 500MB לפונקציית Python ב-Vercel ותקרת 100MB לקובץ בודד ב-GitHub. בזמן ריצה יש numpy ו-tokenizers בלבד — אין torch, אין API, אין רשת.',
  ], { size: 10.5, after: 6 }), {
    x: M, y: 3.62, w: CW, h: 1.4, align: 'right', rtlMode: true, valign: 'top', margin: 0,
  });
}

/* ========================================================= 9 · הזמנים */
{
  const s = base('08 · הזמנים', 'זמני היום מחושבים, לא נשלפים');
  lead(s, 'זמני היום ההלכתיים אינם נתון שמורידים מאיפשהו — הם פונקציה של קו רוחב, קו אורך ותאריך. האתר מחשב אותם בעצמו, בשרת, לפי אלגוריתם המיקום הסולרי של NOAA, ובלי אף קריאת רשת בזמן ריצה.',
    { y: 1.44, h: 0.68, size: 12 });

  const tw = (CW - 3 * 0.18) / 4;
  [['32', 'ערים בישראל'], ['14', 'זמנים ליום'], ['0', 'קריאות רשת בזמן ריצה'], ['0 ₪', 'עלות לקריאה']]
    .forEach(([v, l], i) => stat(s, { x: M + (3 - i) * (tw + 0.18), y: 2.24, w: tw, value: v, label: l, h: 0.86 }));

  s.addText(bulletList([
    'הזוויות שמתחת לאופק הן ההכרעה ההלכתית: עלות השחר 16.1°, זמן טלית ותפילין 11.5°, צאת הכוכבים 8.5°.',
    'החישוב נעשה בגובה פני הים, כמו ברוב הלוחות המקובלים בארץ, ולא לפי גובה היישוב בפועל.',
    'זמן הדלקת נרות אינו חישוב אלא מנהג המקום — ולכן הוא נתון לכל עיר בנפרד, יחד עם מקור המנהג.',
    'גם הלוח העברי מקומי: מולד וארבע הדחיות, אותו אלגוריתם שב-Calendrical Calculations. אין טבלה ואין רשת.',
  ], { size: 10.5, after: 6 }), {
    x: M, y: 3.32, w: CW, h: 1.34, align: 'right', rtlMode: true, valign: 'top', margin: 0,
  });

  strip(s, {
    y: 4.62, h: 0.5, size: 10, fill: PAPER, line: RULE, color: MUTED,
    text: 'app/zmanim.py — 340 שורות של אסטרונומיה, בלי ספרייה חיצונית אחת.',
  });
}

/* ================================================= 10 · האימות מול Hebcal */
{
  const s = base('09 · האימות', 'ה-API של Hebcal — בוחן, לא ספק');
  lead(s, 'את ה-API של Hebcal אנחנו כן מפעילים, אבל רק בפיתוח ולא בזמן ריצה: הוא אינו מקור הזמנים אלא האורקל שבודק אותם. סקריפט אחד מריץ את המנוע המקומי מול השירות לאורך שנה שלמה, ומדפיס את הפער המרבי לכל זמן.',
    { y: 1.44, h: 0.72, size: 12 });

  rtlTable(s, {
    x: M, y: 2.3, w: 4.3, colW: [1.9, 2.4],
    head: ['מה נמדד', 'הריצה האחרונה'],
    rows: [
      ['השוואות', '1,344'],
      ['זמנים', '14'],
      ['ערים', '4'],
      ['תאריכים לאורך שנה', '24'],
      ['סבילות', 'דקה אחת'],
      ['הפער המרבי שנמצא', '0.75 דקות'],
    ],
    fontSize: 10, rowH: 0.255,
  });

  s.addText('למה לא לקרוא ל-API בזמן ריצה', {
    x: 5.1, y: 2.3, w: 4.28, h: 0.28, align: 'right', rtlMode: true, valign: 'top',
    fontFace: SERIF, fontSize: 13, bold: true, color: GOLD_DEEP, margin: 0,
  });
  s.addText(bulletList([
    'תלות: כשהשירות נופל או משנה מבנה, האתר מפסיק לתת זמנים.',
    'מגבלת קצב ועלות — שתיהן נמנעות כשהחישוב מקומי.',
    'זמן תגובה: כפל מטריצה מקומי מול קריאת רשת חיצונית בכל בקשה.',
    'פרטיות: מיקום המשתמש אינו יוצא לשום שרת אחר.',
  ], { size: 10, after: 5 }), {
    x: 5.1, y: 2.64, w: 4.28, h: 1.5, align: 'right', rtlMode: true, valign: 'top', margin: 0,
  });

  strip(s, {
    y: 4.22, h: 0.72, size: 11,
    text: 'התוצאה: הפער המרבי בכל 1,344 ההשוואות היה 45 שניות, בחצות היום, וכל שאר הזמנים בתוך חצי דקה. הבדיקה מורצת מחדש אחרי כל שינוי במנוע — python scripts/verify_zmanim.py',
  });
}

/* ======================================================= 11 · שער הראיות */
{
  const s = base('10 · יושרה', 'המערכת יודעת לומר «לא מצאתי»');
  lead(s, 'מנוע שמחזיר תמיד תוצאה כלשהי מסוכן דווקא כאן: התוצאה הקרובה ביותר אינה בהכרח קשורה לשאלה. לכן נבנה שער ראיות שחוסם תשובה כשאין די ראיה.',
    { y: 1.44, h: 0.56, size: 12 });

  s.addText('איך זה עובד', {
    x: 5.1, y: 2.06, w: 4.28, h: 0.28, align: 'right', rtlMode: true, valign: 'top',
    fontFace: SERIF, fontSize: 13, bold: true, color: GOLD_DEEP, margin: 0,
  });
  s.addText(bulletList([
    'לכל גזע נשמרת שכיחות המסמכים שלו במאגר.',
    'מילה שמופיעה ביותר מעשרה אחוזים מהשאלות היא מילת מילוי, ואינה נחשבת ראיה.',
    'לשאר מחושב משקל IDF קלאסי, לפי שכיחותן ההפוכה.',
    'תוצאה שאינה מכסה לפחות חמישית ממסת המידע של השאילתה נפסלת.',
  ], { size: 10.5, after: 5 }), {
    x: 5.1, y: 2.38, w: 4.28, h: 1.7, align: 'right', rtlMode: true, valign: 'top', margin: 0,
  });

  s.addText('הסף נבחר ממדידה, לא מתחושה', {
    x: M, y: 2.06, w: 4.28, h: 0.28, align: 'right', rtlMode: true, valign: 'top',
    fontFace: SERIF, fontSize: 13, bold: true, color: GOLD_DEEP, margin: 0,
  });
  rtlTable(s, {
    x: M, y: 2.4, w: 4.28, colW: [0.98, 1.16, 1.14, 1.0],
    head: ['סף', 'Recall@1', 'טעות בטוחה', 'אפס תוצאות'],
    rows: [
      ['ללא סף', '25.3%', '64.0%', '0.0%'],
      ['0.20', '24.0%', '46.7%', '18.7%'],
      ['0.34', '17.3%', '13.3%', '64.0%'],
    ],
    fontSize: 9.5, rowH: 0.3,
  });
  s.addText('הסף שנבחר, 0.20, מוותר על 1.3 נקודות דיוק וחוסך שבע-עשרה נקודות של תשובות בטוחות-ושגויות. נמדד על מאגר של 1,422 שאלות.', {
    x: M, y: 3.72, w: 4.28, h: 0.6, align: 'right', rtlMode: true, valign: 'top',
    fontFace: SANS, fontSize: 9.5, color: MUTED, margin: 0, lineSpacingMultiple: 1.2,
  });

  strip(s, {
    y: 4.36, h: 0.66, fill: 'F7F2E6', line: RULE, color: INK, size: 10,
    text: 'ועל הדמיון הסמנטי אין סף כלל: נמדד שהציון אינו מפריד בין נכון לשגוי — שאילתה שאין לה תשובה במאגר קיבלה 0.750, גבוה מכל פגיעה נכונה שנמדדה, 0.658.',
  });
}

/* ============================================================ 10 · מדידה */
{
  const s = base('11 · מדידה', 'כל החלטה נמדדה');
  lead(s, 'מסגרת מדידה קבועה: 102 שאילתות — 85 עם תשובה ידועה ו-17 שאין להן תשובה במכוון — חמש שיטות ושישה מדדים, מורצות מחדש אחרי כל הוספת תוכן.',
    { y: 1.42, h: 0.52, size: 11.5 });

  rtlTable(s, {
    y: 2.0, colW: [2.4, 1.55, 1.55, 1.5, 1.76],
    head: ['שיטה', 'Recall@1', 'Recall@5', 'MRR@10', 'אפס תוצאות'],
    rows: [
      ['לקסיקלי AND', '7.1%', '7.1%', '0.071', '88.2%'],
      ['לקסיקלי OR', '25.9%', '41.2%', '0.314', '0.0%'],
      ['סמנטי בלבד', '18.8%', '27.1%', '0.225', '0.0%'],
      ['מיזוג RRF', '22.4%', '42.4%', '0.302', '0.0%'],
      ['מה שרץ באתר', '27.1%', '35.3%', '0.301', '10.6%'],
    ],
    fontSize: 10, rowH: 0.285,
  });

  strip(s, {
    y: 3.82, h: 0.7, bold: false, size: 11,
    text: 'המסקנה הכנה: הלקסיקלי עדיין המדויק ביותר במקום הראשון, והמיזוג הטוב ביותר בחמש הראשונות. הרחבת המאגר ב-260 שאלות הורידה את כל המספרים — כל שאלה חדשה היא מסיח לשאילתות הישנות.',
  });
  s.addText('שלוש-עשרה שיטות שיפור נמדדו ונדחו: SIF/IDF, p-mean, מרכוז, all-but-the-top, מורה שאומן על עברית רבנית, אוצר מילים תחומי, מרב על פני שדות ונרמול מילה-מילה. אף אחת לא עברה את המתכון הקיים בשני גדלי מאגר.', {
    x: M, y: 4.62, w: CW, h: 0.44, align: 'right', rtlMode: true, valign: 'top',
    fontFace: SANS, fontSize: 9, color: MUTED, margin: 0, lineSpacingMultiple: 1.2,
  });
}

/* ========================================================= 11 · התוכן וה-LLM */
{
  const s = base('12 · יצירת התוכן', 'מודל שפה כותב את התוכן — לא את התשובה');

  const w = 2.78, gap = 0.21;
  const steps = [
    ['1 · כתיבה', 'סוכן לכל תת-נושא מייצר שאלות ותשובות במבנה JSON קבוע: שאלה, תשובה קצרה, פסקאות הרחבה, מקורות, מנהגים ומילות חיפוש.'],
    ['2 · בקרת איכות', 'סוכן שני קורא את הפלט, מאתר כפילויות, מתקן מבנה ובודק סימני שגיאה הלכתיים.'],
    ['3 · אימות מול המקור', 'סקריפט בודק כל הפניה מול ספריא — קיימת, ועוסקת בנושא — ומסיר כפילויות מול המאגר על טקסט מנורמל.'],
  ];
  steps.forEach(([t, b], i) => card(s, {
    x: M + (2 - i) * (w + gap), y: 1.44, w, h: 1.78, title: t, body: b, size: 10.5, titleSize: 13,
  }));

  strip(s, {
    y: 3.4, h: 0.68, size: 11.5,
    text: 'כל זה קורה מראש, בזמן ההכנה. בזמן ריצה אין LLM בנתיב הבקשה — האתר מחזיר תשובות שנכתבו ואומתו, ולא תשובות שנוצרות בזמן אמת.',
  });
  strip(s, {
    y: 4.22, h: 0.64, size: 10, fill: PAPER, line: RULE, color: MUTED,
    text: 'הבהרה: התוכן נועד ללימוד ולהתמצאות בלבד. אינו תחליף לשאלת רב, ואין להסתמך עליו למעשה.',
  });
}

/* ============================================================ 12 · סיכום */
{
  const s = base('13 · סיכום', 'מה יש כאן');

  s.addText(bulletList([
    'מאגר עברי אחד: 2,125 שאלות, תשובה קצרה, מקורות ומנהגים.',
    'מנוע חיפוש היברידי שמגשר בין ניסוח יומיומי למונח ההלכתי.',
    'מודל שפה עברי מקומי בן 69MB — בלי ענן, בלי API ובלי עלות.',
    'מסגרת מדידה שהכריעה בין השיטות, ודחתה שלוש-עשרה מהן.',
    'מערכת שמעדיפה לשתוק על פני לענות תשובה שאינה נכונה.',
  ], { size: 11.5, after: 9, code: '25C6' }), {
    x: 4.62, y: 1.5, w: 4.76, h: 2.2, align: 'right', rtlMode: true, valign: 'top', margin: 0,
  });

  card(s, {
    x: M, y: 1.5, w: 3.72, h: 2.05, title: 'מה הלאה',
    items: [
      'להמשיך לאזן: חלקה של שבת במאגר ירד מ-71% ל-63% והיא עדיין הנושא הגדול.',
      'שיפור החיפוש בניסוח חופשי, שם המדידה עדיין נמוכה.',
      'עלייה לדומיין קבוע, ומדידה על שאילתות אמת.',
    ],
    size: 10.5, titleSize: 13,
  });

  s.addShape(pptx.ShapeType.rect, { x: (W - 1.6) / 2, y: 4.12, w: 1.6, h: 0.012, fill: { color: GOLD } });
  s.addText('תודה', {
    x: 0, y: 4.3, w: W, h: 0.45, align: 'center', rtlMode: true, valign: 'top',
    fontFace: SERIF, fontSize: 20, bold: true, color: GOLD_DEEP, margin: 0,
  });
}

await pptx.writeFile({ fileName: OUT });

// שלב שני, הכרחי: פיצול הריצות לפי כתב וסימון rtl בכל אחת. בלעדיו
// «512MB» מודפס «MB512» ורווחים נעלמים בגבול בין לטינית לעברית.
const fix = spawnSync('python', [path.join(HERE, 'fix_pptx_bidi.py'), OUT],
  { encoding: 'utf8' });
process.stdout.write(fix.stdout || '');
if (fix.status !== 0) {
  process.stderr.write(fix.stderr || '');
  throw new Error('fix_pptx_bidi.py נכשל — המצגת נשארה עם כיווניות שבורה');
}
console.log('נכתב:', OUT, '—', pageNo, 'שקפים');
