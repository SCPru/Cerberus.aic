from random import random, choice
from datetime import datetime, timedelta, timezone

from fdbotapi.bot import Bot
from fdbotapi.wiki import Wiki, ForumThread
from fdbotapi.utils import normalize_tag, include_tags, exclude_tags, now
from config import *

import logging
import os

formatter = logging.Formatter("%(asctime)s  [%(levelname)s]  %(message)s")

os.makedirs(LOG_DIR, exist_ok=True)
fileHandler = logging.FileHandler(os.path.join(LOG_DIR, "work.log"), encoding="utf-8")
fileHandler.setFormatter(formatter)

consoleHandler = logging.StreamHandler()
consoleHandler.setFormatter(formatter)

logger = logging.getLogger()
logger.setLevel(logging.DEBUG if DEBUG else logging.INFO)
logger.addHandler(fileHandler)
logger.addHandler(consoleHandler)


wiki = Wiki(WIKI_BASE_URL)
bot = Bot(wiki).auth(API_TOKEN)


def get_random_deletion_phrase():
    rand = random()
    avaliable_easter_phrases = [phrase for chance, phrase in EASTER_DELETION_PHRASES if chance >= rand]

    if avaliable_easter_phrases:
        return choice(avaliable_easter_phrases)
    else:
        return choice(COMMON_DELETION_PHRASES)
    
@bot.on_startup()
async def on_startup():
    logger.info(f"Запускаю Cerberus.aic v{VERSION}")
    if API_TOKEN:
        logger.info("Токен авторизаци успешно загружен")
        print(API_TOKEN)
        logger.info(f"Подключаюсь к вики: {wiki.wiki_base}")
    else:
        logger.error("Не удалось загрузить токен авторизации")
        bot.stop()

@bot.on_shutdown()
async def on_shutdown():
    logger.info(f"Cerberus.aic v{VERSION} завершает работу")

@bot.task(minutes=WORKING_PERIOD_MINUTES)
async def mark_for():
    target_pages = await bot.list_pages(
        category=" ".join(DELETION_CATEGORIES),
        tags=" ".join(include_tags(DELETION_FILTER_TAGS) + exclude_tags([DELETION_MARK_TAG, WHITE_MARK_TAG, APPROVEMENT_TAG, IN_PROGRESS_TAG, PROTECTION_TAG])),
    )

    for page in target_pages:
        await page.fetch()

        if page.rating > CRITICAL_RATING and page.popularity < CRITICAL_POPULARITY:
            last_category_move = await page.get_last_category_move()

            if now() - last_category_move.createdAt >= timedelta(days=GRAYZONE_DELAY_DAYS):
                prev_name = page.name
                await page.rename(f"deleted:{page.name}")
                await page.set_tags({})
                logger.info(f"Перенесено в архив удаленных: {prev_name} -> {page}")
                continue

        if page.votes_count > APPROVEMENT_VOTES_COUNT and page.popularity >= CRITICAL_POPULARITY:
            await page.add_tags([WHITE_MARK_TAG])
            logger.info(f"Проходной рейтинг набран: {page}")
            continue

        if not (page.rating < CRITICAL_RATING and page.votes_count >= CRITICAL_VOTES_COUNT):
            continue

        await page.add_tags([DELETION_MARK_TAG])
        logger.info(f"Помечено для удаления: {page}")

        thread = await page.get_thread()
        deletion_phrase = get_random_deletion_phrase()

        await thread.new_post(
            title="Системное уведомление",
            source=deletion_phrase
        )
        logger.info(f"На странице обсуждения {page.name} оставлено сообщение: {deletion_phrase}")

@bot.task(minutes=WORKING_PERIOD_MINUTES)
async def delete_marked():
    target_pages = await bot.list_pages(
        category=" ".join(DELETION_CATEGORIES),
        tags=" ".join(include_tags([DELETION_MARK_TAG]) + exclude_tags([IN_PROGRESS_TAG, PROTECTION_TAG]))
    )

    for page in target_pages:
        await page.fetch()

        if page.rating >= CRITICAL_RATING:
            await page.remove_tags([DELETION_MARK_TAG])
            logger.info(f"Метка к удалению снята: {page}")
            continue

        tag_date = await page.get_tag_date(DELETION_MARK_TAG)
        if tag_date is None or now() - tag_date < timedelta(days=DELETION_DELAY_DAYS):
            continue

        report_thread = ForumThread(wiki, DELETION_REPORT_TEMPLATE['thread_id'])

        await page.delete_page()
        await report_thread.new_post(
            title=DELETION_REPORT_TEMPLATE["title"],
            source=DELETION_REPORT_TEMPLATE['source'] \
            .format(title=page.title, rating=page.rating, votes=page.votes_count, popularity=page.popularity, author=page.author.username)
        )
        logger.info(f"Страница удалена безвозвратно: {page}")

@bot.task(minutes=WORKING_PERIOD_MINUTES)
async def approve_marked():
    target_pages = await bot.list_pages(
        category=" ".join(DELETION_CATEGORIES),
        tags=" ".join(include_tags([WHITE_MARK_TAG]) + exclude_tags([APPROVEMENT_TAG, IN_PROGRESS_TAG, PROTECTION_TAG])),
    )

    for page in target_pages:
        await page.fetch()

        if page.votes_count > APPROVEMENT_VOTES_COUNT and page.popularity >= CRITICAL_POPULARITY:
            tag_date = await page.get_tag_date(WHITE_MARK_TAG)

            if now() - tag_date >= timedelta(days=APPROVEMENT_DELAY_DAYS):
                await page.update_tags(
                    add_tags=[APPROVEMENT_TAG, TO_TAGGING_TAG],
                    remove_tags=[WHITE_MARK_TAG]
                )
                logger.info(f"Помечено к переносу: {page}")

        else:
            await page.remove_tags([WHITE_MARK_TAG])
            logger.info(f"Проходной рейтинг утрачен: {page}")

@bot.task(minutes=WORKING_PERIOD_MINUTES)
async def handle_in_progress_articles():
    target_pages = await bot.list_pages(
        category=" ".join(DELETION_CATEGORIES),
        tags=" ".join(include_tags([IN_PROGRESS_TAG]) + exclude_tags([PROTECTION_TAG])),
    )

    unwanted_tags = [APPROVEMENT_TAG, TO_TAGGING_TAG, WHITE_MARK_TAG, DELETION_MARK_TAG]

    for page in target_pages:
        await page.fetch()

        if now() - page.last_edit >= timedelta(days=IN_PROGRESS_MAX_DAYS):
            prev_name = page.name
            thread = await page.get_thread()
            
            await page.rename(f"deleted:{page.name}")
            await page.set_tags({})
            await thread.new_post(
                title="Системное уведомление",
                source="В соответствии с пунктом 1.5 правил публикации, раздел \"Автору\", статья переносится в Удалённые."
            )

            logger.info(f"Статья в работе перенесена в архив удаленных: {prev_name} -> {page}")

            continue

        for tag in unwanted_tags:
            if normalize_tag(tag) in page.tags:
                removed_tags = await page.remove_tags(unwanted_tags)
                logger.info(f"Удалены теги полигона для статьи в работе: {page.name} {removed_tags}")