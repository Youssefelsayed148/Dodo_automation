"""Book-language labels rendered by code (never by the image model)."""

LABELS = {
    "en": {
        "belongs_to": "This book belongs to",
        "the_end": "The End",
        "end_note": "Thank you for coloring with us!",
        "maze": "Help find the way!",
        "dot_to_dot": "Connect the dots",
        "word_search": "Find the words",
        "trace_write": "Trace and write",
        "qa_page": "Question time",
        "answer_key": "Answers",
        "story": "",
        "by": "",
    },
    "ar": {
        "belongs_to": "هذا الكتاب ملك",
        "the_end": "النهاية",
        "end_note": "شكرًا لأنك لوّنت معنا!",
        "maze": "ساعدني في إيجاد الطريق!",
        "dot_to_dot": "صِل النقاط",
        "word_search": "ابحث عن الكلمات",
        "trace_write": "تتبّع واكتب",
        "qa_page": "وقت الأسئلة",
        "answer_key": "الإجابات",
        "story": "",
        "by": "",
    },
}


def label(lang: str, key: str) -> str:
    return LABELS.get(lang, LABELS["en"]).get(key, LABELS["en"].get(key, key))


def to_arabic_digits(n: int | str) -> str:
    return str(n).translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩"))


def page_number(n: int, lang: str) -> str:
    return to_arabic_digits(n) if lang == "ar" else str(n)
