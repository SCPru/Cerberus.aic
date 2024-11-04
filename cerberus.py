from random import random, choice
from datetime import timedelta
from typing import List
from logger import get_logger
from asyncio import Semaphore

from fdbotapi.bot import Bot
from fdbotapi.wiki import Wiki, ForumThread, Page
from fdbotapi.utils import include_tags, exclude_tags, now, never
from config import *

logger = get_logger()

wiki = Wiki(WIKI_BASE_URL)
bot = Bot(wiki).auth(API_TOKEN)


def get_random_deletion_phrase():
    rand = random()
    avaliable_easter_phrases = [phrase for chance, phrase in EASTER_DELETION_PHRASES if chance >= rand]

    if avaliable_easter_phrases:
        return choice(avaliable_easter_phrases)
    else:
        return choice(COMMON_DELETION_PHRASES)
    
async def is_in_grayzone(page: Page) -> bool:
    if page.rating > CRITICAL_RATING and page.popularity < CRITICAL_POPULARITY:
        last_category_move = await page.get_last_category_move()
        if now() - last_category_move.createdAt >= timedelta(days=GRAYZONE_DELAY_DAYS):
            return True
    return False
    
async def is_in_progress_expired(page: Page) -> bool:
    return now() - (await page.get_last_source_edit()).createdAt >= timedelta(days=IN_PROGRESS_MAX_DAYS)

async def is_last_chance_expired(page: Page) -> bool:
    tag_date = await page.get_tag_date(DELETION_MARK_TAG)
    if tag_date:
        return now() - tag_date >= timedelta(days=DELETION_DELAY_DAYS)
    return False

def is_critical_rating_reached(page: Page) -> bool:
    return page.rating < CRITICAL_RATING and page.votes_count >= CRITICAL_VOTES_COUNT

def is_approvement_rating_reached(page: Page) -> bool:
    return page.votes_count > APPROVEMENT_VOTES_COUNT and page.popularity >= CRITICAL_POPULARITY

async def is_ready_for_approvement(page: Page) -> bool:
    if is_approvement_rating_reached(page):
        tag_date = await page.get_tag_date(WHITE_MARK_TAG)
        if tag_date:
            return now() - tag_date >= timedelta(days=APPROVEMENT_DELAY_DAYS)
        return False
    return False

# global_last_pages_registry_update = never()
# global_pages_registry = []
# sem = Semaphore()
# async def get_all_pages_lazy(update_after: timedelta):
#     async with sem:
#         global global_pages_registry, global_last_pages_registry_update
#         curr_moment = now()

#         if curr_moment - global_last_pages_registry_update >= update_after:
#             global_pages_registry = await bot.get_all_pages()
#             global_last_pages_registry_update = curr_moment

#         return global_pages_registry

# async def get_pages(categories: List[str]=[], tags: List[str]=[]):
#     pages = await get_all_pages_lazy(timedelta(minutes=WORKING_PERIOD_MINUTES))
#     return await Wiki.filter_pages(pages, categories, tags)
    
@bot.on_startup()
async def on_startup():
    logger.info(f"Запускаю Cerberus.aic v{VERSION}")
    if API_TOKEN:
        logger.info("Токен авторизаци успешно загружен")
        logger.info(f"Подключаюсь к вики: {wiki.wiki_base}")
    else:
        logger.error("Не удалось загрузить токен авторизации")
        bot.stop()

@bot.on_shutdown()
async def on_shutdown():
    logger.warning(f"Cerberus.aic v{VERSION} завершает работу")

@bot.task(minutes=WORKING_PERIOD_MINUTES)
async def mark_for():
    target_pages = await bot.list_pages(
        category=" ".join(DELETION_CATEGORIES),
        tags=" ".join(include_tags(DELETION_BRANCH_TAGS) + exclude_tags([DELETION_MARK_TAG, WHITE_MARK_TAG, APPROVEMENT_TAG, IN_PROGRESS_TAG, PROTECTION_TAG])),
    )

    for page in target_pages:
        await page.fetch()

        if await is_in_grayzone(page):
            prev_name = page.name
            thread = await page.get_thread()
            await page.rename(f"deleted:{page.name}")
            await page.set_tags({})
            await thread.new_post(
                title=SYSTEM_MESSAGE_TITLE,
                source=GRAYZONE_ARCHIVATION_MESSAGE \
                .format(
                    popularity=page.popularity,
                    votes=page.votes
                )
            )
            logger.info(f"Перенесено в архив удаленных: {prev_name} -> {page}")

        elif is_approvement_rating_reached(page):
            await page.add_tags([WHITE_MARK_TAG])
            logger.info(f"Проходной рейтинг набран: {page}")

        elif  is_critical_rating_reached(page):
            await page.add_tags([DELETION_MARK_TAG])
            logger.info(f"Помечено для удаления: {page}")
            
            thread = await page.get_thread()
            deletion_phrase = get_random_deletion_phrase()
            await thread.new_post(
                title=SYSTEM_MESSAGE_TITLE,
                source=deletion_phrase
            )
            logger.info(f"На странице обсуждения {page.name} оставлено сообщение: {deletion_phrase}")

@bot.task(minutes=WORKING_PERIOD_MINUTES)
async def delete_marked():
    target_pages = await bot.list_pages(
        category=" ".join(DELETION_CATEGORIES),
        tags=" ".join(include_tags(DELETION_BRANCH_TAGS + [DELETION_MARK_TAG]) + exclude_tags([IN_PROGRESS_TAG, PROTECTION_TAG]))
    )
    
    deleted_pages: List[Page] = []

    for page in target_pages:
        await page.fetch()

        if not is_critical_rating_reached(page):
            await page.remove_tags([DELETION_MARK_TAG])
            logger.info(f"Метка к удалению снята: {page}")

        elif await is_last_chance_expired(page):
            await page.delete_page()
            deleted_pages.append(page)
            logger.info(f"Страница удалена безвозвратно: {page}")

    if deleted_pages:
        report_thread = ForumThread(wiki, DELETION_REPORT_TEMPLATE['thread_id'])
        deletion_message = \
            DELETION_REPORT_TEMPLATE['prepend'] + "\n" + \
            "\n".join([
                DELETION_REPORT_TEMPLATE['line'] \
                .format(title=page.title, rating=page.rating, votes=page.votes_count, popularity=page.popularity, author=page.author.username, tags=", ".join(page.tags))
                for page in deleted_pages
            ])

        await report_thread.new_post(
            title=DELETION_REPORT_TEMPLATE["title"],
            source=deletion_message
        )

@bot.task(minutes=WORKING_PERIOD_MINUTES)
async def approve_marked():
    target_pages = await bot.list_pages(
        category=" ".join(DELETION_CATEGORIES),
        tags=" ".join(include_tags(DELETION_BRANCH_TAGS + [WHITE_MARK_TAG]) + exclude_tags([APPROVEMENT_TAG, IN_PROGRESS_TAG, PROTECTION_TAG])),
    )

    for page in target_pages:
        await page.fetch()

        if await is_ready_for_approvement(page):
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
        tags=" ".join(include_tags(DELETION_BRANCH_TAGS + [IN_PROGRESS_TAG]) + exclude_tags([PROTECTION_TAG])),
    )

    unwanted_tags = {APPROVEMENT_TAG, TO_TAGGING_TAG, WHITE_MARK_TAG, DELETION_MARK_TAG}

    for page in target_pages:
        await page.fetch()

        if await is_in_progress_expired(page):
            prev_name = page.name
            thread = await page.get_thread()
            await page.rename(f"deleted:{page.name}")
            await page.set_tags({})
            await thread.new_post(
                title=SYSTEM_MESSAGE_TITLE,
                source=LONG_IN_PROGRESS_ARCHIVATION_MESSAGE
            )
            logger.info(f"Статья в работе перенесена в архив удаленных: {prev_name} -> {page}")
        else:
            if unwanted_tags.intersection(page.tags):
                removed_tags = await page.remove_tags(unwanted_tags)
                logger.info(f"Удалены теги полигона для статьи в работе: {page.name} {removed_tags}")