"""The five gamified learning activities and which one fits which gap.

Every activity shares one game system (mission card, levels, XP, hint coins, AI mentor,
boss level, badges); the AI fills the template with content for the specific gap.
"""

ACTIVITIES = {
    "escape_room": {
        "name": "غرفة الهروب المهنية",
        "icon": "🔐",
        "summary": "أبواب مقفلة، وكل باب مشكلة من العمل. كل قرار يفتح جزءًا من الرمز ويؤثر على الباب التالي.",
        "best_for": "المهارات الإجرائية التي تحتاج سلسلة قرارات متتابعة.",
        "available": True,
    },
    "gap_hunter": {
        "name": "صياد الفجوات",
        "icon": "🕵️",
        "summary": "مخرج عمل فيه أخطاء مخفية. اصطدها، صنّفها، برّرها، واقترح إصلاحها.",
        "best_for": "مهارات التشخيص واكتشاف الأخطاء والمراجعة.",
        "available": True,
    },
    "work_challenge": {
        "name": "تحديات من واقع العمل",
        "icon": "🧩",
        "summary": "مهمة من مدير أو عميل، بمعايير قبول وتغيير مفاجئ في المتطلبات، ومراجعة من «المدير».",
        "best_for": "المهارات الناعمة وتطبيق المهارة كاملة في مهمة حقيقية.",
        "available": True,
    },
    "shadow": {
        "name": "الظل والظل العكسي",
        "icon": "👥",
        "summary": "تشاهد خبيرًا يحل المشكلة وتتوقع خطوته التالية، ثم تحلها أنت ويقارن الخبير خطواتك بخطواته.",
        "best_for": "الفجوات الكبيرة: تعلّم طريقة الخبير قبل التطبيق المستقل.",
        "available": True,
    },
    "teach_others": {
        "name": "علّم غيرك",
        "icon": "🎓",
        "summary": "«سعود» متدرب جديد عنده مفاهيم خاطئة. اشرح له حتى ينجح في اختباره.",
        "best_for": "فجوات الفهم: ما لا تفهمه جيدًا لا تقدر تشرحه.",
        "available": True,
    },
}

DIAGNOSTIC_TYPES = {"error_detection", "true_false", "multiple_choice"}


def choose_activities(result: dict, missed_types: list[str]) -> list[str]:
    """Ordered activity ids for one gap: the first is the recommended one, the rest
    are alternatives offered when the gap persists ("جرّب طريقة ثانية")."""
    dimension, kind, status = result["dimension"], result.get("skill_kind"), result["status"]
    if dimension == "skill" and kind == "soft":
        order = ["work_challenge", "shadow", "teach_others", "escape_room", "gap_hunter"]
    elif dimension == "skill" and status == "likely_gap":
        order = ["shadow", "escape_room", "gap_hunter", "work_challenge", "teach_others"]
    elif dimension == "skill":
        diagnostic = sum(t in DIAGNOSTIC_TYPES for t in missed_types) >= len(missed_types) / 2 if missed_types else True
        order = (
            ["gap_hunter", "escape_room", "work_challenge", "shadow", "teach_others"]
            if diagnostic
            else ["escape_room", "gap_hunter", "work_challenge", "shadow", "teach_others"]
        )
    elif status == "likely_gap":
        order = ["shadow", "teach_others", "gap_hunter", "escape_room", "work_challenge"]
    else:
        order = ["teach_others", "gap_hunter", "shadow", "escape_room", "work_challenge"]
    return order


def activity_card(activity_id: str) -> dict:
    return {"activity_type": activity_id, **ACTIVITIES[activity_id]}
