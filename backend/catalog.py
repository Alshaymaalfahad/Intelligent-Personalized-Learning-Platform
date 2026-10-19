"""Technical specializations and the interest areas offered for each one.

Each specialization offers 3 suggested interest areas; trainees can also add their
own (stored as typed). Catalog values are stored in English; `label_ar` is for display.
The skills and knowledge areas themselves are produced by the AI per trainee
(see prompts/), so this file only drives the profile form.
"""

SPECIALIZATIONS: list[dict] = [
    {
        "name": "Software Engineering",
        "label_ar": "هندسة البرمجيات",
        "interests": [
            {"name": "Software Design and Architecture", "label_ar": "تصميم ومعمارية البرمجيات"},
            {"name": "Programming and Data Structures", "label_ar": "البرمجة وهياكل البيانات"},
            {"name": "Software Testing", "label_ar": "اختبار البرمجيات"},
        ],
    },
    {
        "name": "Information Systems",
        "label_ar": "نظم المعلومات",
        "interests": [
            {"name": "Systems Analysis and Design", "label_ar": "تحليل وتصميم النظم"},
            {"name": "Database Management", "label_ar": "إدارة قواعد البيانات"},
            {"name": "Business Intelligence", "label_ar": "ذكاء الأعمال وتحليل البيانات"},
        ],
    },
    {
        "name": "Computer Science",
        "label_ar": "علوم الحاسب",
        "interests": [
            {"name": "Algorithms", "label_ar": "الخوارزميات"},
            {"name": "Operating Systems", "label_ar": "أنظمة التشغيل"},
            {"name": "Computer Networks", "label_ar": "شبكات الحاسب"},
        ],
    },
    {
        "name": "Cybersecurity",
        "label_ar": "الأمن السيبراني",
        "interests": [
            {"name": "Network Security", "label_ar": "أمن الشبكات"},
            {"name": "Security Operations", "label_ar": "عمليات الأمن (SOC)"},
            {"name": "Application Security", "label_ar": "أمن التطبيقات"},
        ],
    },
    {
        "name": "Data Science and AI",
        "label_ar": "علم البيانات والذكاء الاصطناعي",
        "interests": [
            {"name": "Data Analysis", "label_ar": "تحليل البيانات"},
            {"name": "Statistics", "label_ar": "الإحصاء"},
            {"name": "Machine Learning", "label_ar": "تعلم الآلة"},
        ],
    },
    {
        "name": "Network Engineering",
        "label_ar": "هندسة الشبكات",
        "interests": [
            {"name": "Routing and Switching", "label_ar": "التوجيه والتبديل"},
            {"name": "Network Design", "label_ar": "تصميم الشبكات"},
            {"name": "Network Troubleshooting", "label_ar": "تشخيص أعطال الشبكات"},
        ],
    },
]


def find_specialization(name: str) -> dict | None:
    """Case-insensitive lookup by English name."""
    key = name.strip().casefold()
    return next((s for s in SPECIALIZATIONS if s["name"].casefold() == key), None)
