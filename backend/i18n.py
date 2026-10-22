"""Language support on the server.

- The interface language of a request comes from the `X-Lang` header (en | ar), set by
  the frontend; error messages are localized with it on the way out.
- AI-generated content (questions, lessons, activities) is written in the trainee's
  language, chosen at sign-up (Trainee.language); `language_rule` tells the prompts.
- Everything else the server returns is a code (statuses, decisions, signals …)
  that the frontend translates, so switching language updates it instantly.
"""

import re
from contextvars import ContextVar

LANGS = ("en", "ar")
DEFAULT_LANG = "en"
request_lang: ContextVar[str] = ContextVar("request_lang", default=DEFAULT_LANG)
# Set only when the page sent X-Lang: AI content is then written in the language on screen.
content_lang: ContextVar[str | None] = ContextVar("content_lang", default=None)

LANGUAGE_RULES = {
    "en": (
        "OUTPUT LANGUAGE: write every trainee-facing text in clear, natural professional English. "
        "Code, queries, configs and logs stay in English."
    ),
    "ar": (
        "OUTPUT LANGUAGE: write every trainee-facing text in clear Modern Standard Arabic, keeping established "
        "technical terms in English where professionals use them (e.g. API, JOIN, commit). Code, queries, configs "
        "and logs stay in English."
    ),
}
TRUE_FALSE_OPTIONS = {"en": ["True", "False"], "ar": ["صح", "خطأ"]}


def lang_of(trainee) -> str:
    """The language on screen; otherwise the trainee's saved language (older trainees were Arabic-only)."""
    lang = content_lang.get() or getattr(trainee, "language", None)
    return lang if lang in LANGS else "ar"


def parse_header(value: str | None) -> str:
    value = (value or "").strip().lower()[:2]
    return value if value in LANGS else DEFAULT_LANG


# ---------------------------------------------------------------------------
# Error messages (written in Arabic in the code; translated here for English)
# ---------------------------------------------------------------------------

_EN = {
    "مهارة غير معروفة.": "Unknown skill.",
    "المعرّف يجب أن يكون من 6 إلى 20 حرفًا إنجليزيًا ورقمًا، ويحتوي على حرف ورقم على الأقل.": "Your ID must be 6–20 English letters and digits, with at least one letter and one digit.",
    "هذا المعرّف مستخدم، اختر معرّفًا آخر.": "This ID is taken — choose another one.",
    "لم نجد هذا المعرّف.": "We couldn't find this ID.",
    "اختيار المهارات مقفل حتى تنهي محطات رحلتك الحالية.": "Skill selection is locked until you finish your current journey's stations.",
    "اختر مهارة واحدة على الأقل لرحلتك.": "Pick at least one skill for your journey.",
    "هذه ليست رحلة مهارات.": "This is not a skills journey.",
    "إعادة القياس غير متاحة لرحلة المهارات.": "Re-assessment isn't available for a skills journey.",
    "أكمل التقييم أولًا.": "Complete the assessment first.",
    "لا توجد مرحلة نشطة الآن.": "There is no active level right now.",
    "انتهت هذه المرحلة.": "This level is already finished.",
    "لا توجد تلميحات في مرحلة الزعيم.": "No hints in the final challenge.",
    "لا توجد تلميحات أخرى في هذه المرحلة.": "No more hints in this level.",
    "جارٍ تنفيذ هذه الخطوة بالفعل، انتظر قليلًا.": "This step is already in progress — please wait a moment.",
    "لا يمكن تنفيذ هذه الخطوة في المرحلة الحالية من التقييم.": "This step isn't available at the current stage of the assessment.",
    "اكتب إجابتك قبل المتابعة.": "Write your answer before continuing.",
    "رتّب جميع العناصر قبل المتابعة.": "Order all the items before continuing.",
    "اختر إجابة صالحة.": "Choose a valid answer.",
    "لا يوجد سؤال بانتظار الإجابة في هذه المرحلة.": "There is no question waiting for an answer.",
    "هذا السؤال لم يعد السؤال الحالي. حدّث الصفحة.": "This is no longer the current question. Refresh the page.",
    "سبق أن أجبت عن هذا الباب.": "You already answered this door.",
    "اختر خيارًا واحدًا.": "Choose one option.",
    "اتخذ القرار أولًا.": "Make the decision first.",
    "سبق أن برّرت قرارك.": "You already justified your decision.",
    "اختر تبريرًا صالحًا.": "Choose a valid justification.",
    "إجراء غير معروف.": "Unknown action.",
    "هذه الكفاءة ليست ضمن رحلتك التعليمية.": "This competency is not part of your learning journey.",
    "أسلوب شرح غير معروف.": "Unknown explanation style.",
    "اختر خيارًا.": "Choose an option.",
    "اختر سطرًا من المحتوى.": "Choose a line from the content.",
    "اختر تصنيفًا من القائمة.": "Choose a category from the list.",
    "سبق أن فحصت هذا السطر.": "You already checked this line.",
    "اصطد الخطأ أولًا.": "Catch the mistake first.",
    "سبق أن برّرت هذا الخطأ.": "You already justified this mistake.",
    "اختيار غير صالح.": "Invalid choice.",
    "سلّمت خطواتك بالفعل.": "You already submitted your steps.",
    "لا توجد نقطة توقف حالية.": "There is no current pause point.",
    "استخدمت تلميح هذه النقطة.": "You already used the hint for this pause.",
    "انتهت نقاط التوقف في هذه المرحلة.": "All pause points in this level are done.",
    "اختر بطاقة.": "Choose a card.",
    "اختر خطواتك ورتّبها (خطوتان على الأقل).": "Choose and order your steps (at least two).",
    "انتهت محادثة هذه الجولة؛ أنهِ المرحلة.": "This round's conversation is over — finish the level.",
    "دخل سعود الاختبار بالفعل.": "Saud already took the test.",
    "استخدمت كل محاولات التسليم في هذه المرحلة.": "You used all submissions for this level.",
    "التقرير غير جاهز بعد؛ أكمل قسمي التقييم أولًا.": "The report isn't ready yet — complete both assessment sections first.",
    "مراجعة الأسئلة متاحة بعد اكتمال التقييم فقط.": "Question review is available only after the assessment is complete.",
    "تقييم جودة الأسئلة متاح بعد اكتمال التقييم فقط.": "Rating question quality is available only after the assessment is complete.",
    "لا يوجد شرح لهذه الفجوة بعد.": "There is no lesson for this gap yet.",
    "رمز الدخول مطلوب.": "An access code is required.",
    "المفتاح لا يملك صلاحية استخدام النموذج المحدد.": "The API key has no access to the configured model.",
    "النموذج المحدد في الإعدادات (AI_MODEL) غير موجود.": "The configured model (AI_MODEL) does not exist.",
    "تم تجاوز حد الطلبات أو الرصيد لدى مزود الذكاء الاصطناعي. انتظر قليلًا أو راجع الرصيد.": "The AI provider's rate limit or credit was exceeded. Wait a moment or check your balance.",
    "تعذّر الحصول على رد من خدمة الذكاء الاصطناعي. حاول مرة أخرى.": "The AI service didn't respond. Please try again.",
    "تعذّر الاتصال بخدمة الذكاء الاصطناعي. تحقق من الإنترنت ثم حاول مرة أخرى.": "Couldn't reach the AI service. Check the connection and try again.",
    "رفض نموذج الذكاء الاصطناعي هذا الطلب. جرّب مرة أخرى أو عدّل الهدف المكتوب في الملف.": "The AI model declined this request. Try again or edit the goal in your profile.",
    "أنتج الذكاء الاصطناعي مخرجات غير صالحة. حاول مرة أخرى.": "The AI produced invalid output. Please try again.",
}
_EN_PATTERNS = [
    (re.compile(r"^نشاط «(.+)» قيد البناء حاليًا\.$"), "The activity “{0}” is under construction."),
    (re.compile(r"^أكمل خطوات الرحلة التعليمية أولًا \((\d+) من (\d+)\)\.$"), "Complete the learning journey first ({0} of {1})."),
    (re.compile(r"^اكتب شرحك \((\d+)–(\d+) حرفًا\)\.$"), "Write your explanation ({0}–{1} characters)."),
    (re.compile(r"^اكتب مخرجك \((\d+)–(\d+) حرفًا\)\.$"), "Write your deliverable ({0}–{1} characters)."),
    (re.compile(r"^مفتاح الذكاء الاصطناعي غير صالح\. حدّثه عبر: (.+)$"), "The AI API key is invalid. Update it with: {0}"),
    (re.compile(r"^مفتاح الذكاء الاصطناعي غير مُعدّ على الخادم\. شغّل: (.+)$"), "The AI API key is not set on the server. Run: {0}"),
]


def localize(message: str, lang: str | None = None) -> str:
    """Translate a server message (Arabic in the code) into the request language."""
    lang = lang or request_lang.get()
    if lang == "ar" or not isinstance(message, str):
        return message
    if message in _EN:
        return _EN[message]
    for pattern, template in _EN_PATTERNS:
        m = pattern.match(message)
        if m:
            return template.format(*m.groups())
    return message


_ENUMERATOR = re.compile(r"^\s*(?:(?:step|الخطوة|خطوة)\s*)?[(\[]?[0-9٠-٩]{1,2}\s*(?:[)\]]|[.:\-–—](?=\s))\s*", re.IGNORECASE)


def strip_enumerator(text: str) -> str:
    """Drop a leading "1)", "2.", "٣-" or "Step 1:" the AI added to an item that the page already numbers."""
    stripped = _ENUMERATOR.sub("", text, count=1).strip()
    return stripped or text.strip()
