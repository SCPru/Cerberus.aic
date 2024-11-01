from os import getenv
from json import loads

VERSION = "2.0.0"
LOG_DIR = "logs/"

WIKI_BASE_URL = getenv("WIKI_BASE_URL", "https://scpfoundation.net")
API_TOKEN = getenv("CERBERUS_AUTHKEY")
DEBUG = bool(loads(getenv("DEBUG", "true")))

WORKING_PERIOD_MINUTES = 15

CRITICAL_RATING = 2.0
CRITICAL_VOTES_COUNT = 8
CRITICAL_POPULARITY = 66
APPROVEMENT_VOTES_COUNT = 15

DELETION_DELAY_DAYS = 1
GRAYZONE_DELAY_DAYS = 30
APPROVEMENT_DELAY_DAYS = 7
IN_PROGRESS_MAX_DAYS = 30

APPROVEMENT_TAG = "полигон:к_переносу"
TO_TAGGING_TAG = "полигон:к_тегованию"
WHITE_MARK_TAG = "полигон:_рейтинг_набран"
DELETION_MARK_TAG = "полигон:_к_удалению"
IN_PROGRESS_TAG = "полигон:в_работе"
PROTECTION_TAG = "структура:_защищено"

DELETION_FILTER_TAGS = ["филиал:ru"]
DELETION_CATEGORIES = ["sandbox"]

DELETION_REPORT_TEMPLATE = {
    "thread_id": 3838453,
    "title": "Re: Журнал удалений",
    "source": "Удалено по достижении критического рейтинга:\n\n* {title} - {rating} ({votes}) / {popularity}%\n* Автор: [[user {author}]]"
}

COMMON_DELETION_PHRASES = [
    "Критический рейтинг набран, статья будет удалена завтра."
]

EASTER_DELETION_PHRASES = [
    (0.2, "Критический рейтинг набран, статья будет съедена завтра."),
    (0.1, "Критический рейтинг набран, статья будет передана в Отдел Удалений в течение суток."),
    (0.1, "Критический рейтинг набран, статья будет отправлена в пространство между мирами завтра."),
    (0.1, "Критический рейтинг набран, статья будет удалена из согласованной нормальности завтра."),
    (0.05, "Критический рейтинг набран, вы ещё можете удалить статью самостоятельно."),
    (0.01, "Критический рейтинг набран, Чорная Клика санкционирует завтрашнее удаление."),
]
