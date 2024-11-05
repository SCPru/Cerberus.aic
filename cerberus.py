from random import random, choice, choices
from datetime import timedelta
from typing import List
from logger import get_logger
from asyncio import Semaphore

from fdbotapi.bot import Bot
from fdbotapi.wiki import Wiki, ForumThread, Page
from fdbotapi.utils import include_tags, exclude_tags, now, never
from config import config, extract_period, API_TOKEN

logger = get_logger()

wiki = Wiki(config["wiki_base_url"])
bot = Bot(wiki).auth(API_TOKEN)


def get_random_deletion_phrase():
    rand = random()
    avaliable_easter_phrases = [(phrase["weight"], phrase["text"]) for phrase in config["posting"]["phrases"]["deletion"]["easter"] if phrase["weight"] >= rand]

    if avaliable_easter_phrases:
        weights, easter_phrases = tuple(zip(*avaliable_easter_phrases))
        return choices(easter_phrases, weights=weights)[0]
    else:
        return choice(config["posting"]["phrases"]["deletion"]["common"])
    
async def is_in_grayzone(page: Page) -> bool:
    if page.rating > config["critical"]["rating"] and page.popularity < config["critical"]["popularity"]:
        last_category_move = await page.get_last_category_move()
        if now() - last_category_move.createdAt >= extract_period(config["grayzone"]["delay"]):
            return True
    return False
    
async def is_in_progress_expired(page: Page) -> bool:
    return now() - (await page.get_last_source_edit()).createdAt >= extract_period(config["in_progress"]["delay"])

async def is_last_chance_expired(page: Page) -> bool:
    tag_date = await page.get_tag_date(config["tags"]["deletion"])
    if tag_date:
        return now() - tag_date >= extract_period(config["critical"]["delay"])
    return False

def is_critical_rating_reached(page: Page) -> bool:
    return page.rating < config["critical"]["rating"] and page.votes_count >= config["critical"]["votes"]

def is_approvement_rating_reached(page: Page) -> bool:
    return page.votes_count > config["approvement"]["votes"] and page.popularity >= config["approvement"]["popularity"]

async def is_ready_for_approvement(page: Page) -> bool:
    if is_approvement_rating_reached(page):
        tag_date = await page.get_tag_date(config["tags"]["whitemark"])
        if tag_date:
            return now() - tag_date >= extract_period(config["approvement"]["delay"])
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
    logger.info(f"Запускаю {config["name"]} v{config["version"]}")
    if API_TOKEN:
        logger.info("Токен авторизаци успешно загружен")
        logger.info(f"Подключаюсь к вики: {wiki.wiki_base}")
    else:
        logger.error("Не удалось загрузить токен авторизации")
        bot.stop()

@bot.on_shutdown()
async def on_shutdown():
    logger.warning(f"Cerberus.aic v{config["version"]} завершает работу")

@bot.task(period=extract_period(config["runtime"]["work_period"]))
async def mark_for():
    target_pages = await bot.list_pages(
        category=" ".join(config["deletion"]["categories"]),
        tags=" ".join(config["deletion"]["branch_tags"] + exclude_tags([config["tags"]["deletion"], config["tags"]["whitemark"], config["tags"]["approved"], config["tags"]["in_progress"], config["tags"]["protected"]])),
    )

    for page in target_pages:
        await page.fetch()

        if await is_in_grayzone(page):
            prev_name = page.name
            thread = await page.get_thread()
            await page.rename(f"deleted:{page.name}")
            await page.set_tags({})
            await thread.new_post(
                title=config["posting"]["title"],
                source=config["posting"]["phrases"]["grayzone"] \
                .format(
                    popularity=page.popularity,
                    votes=page.votes
                )
            )
            logger.info(f"Перенесено в архив удаленных: {prev_name} -> {page}")

        elif is_approvement_rating_reached(page):
            await page.add_tags([config["tags"]["whitemark"]])
            logger.info(f"Проходной рейтинг набран: {page}")

        elif  is_critical_rating_reached(page):
            await page.add_tags([config["tags"]["deletion"]])
            logger.info(f"Помечено для удаления: {page}")
            
            thread = await page.get_thread()
            deletion_phrase = get_random_deletion_phrase()
            await thread.new_post(
                title=config["posting"]["title"],
                source=deletion_phrase
            )
            logger.info(f"На странице обсуждения {page.name} оставлено сообщение: {deletion_phrase}")

@bot.task(period=extract_period(config["runtime"]["deletion_period"]))
async def delete_marked():
    target_pages = await bot.list_pages(
        category=" ".join(config["deletion"]["categories"]),
        tags=" ".join(config["deletion"]["branch_tags"] + include_tags([config["tags"]["deletion"]]) + exclude_tags([config["tags"]["in_progress"], config["tags"]["protected"]]))
    )
    
    deleted_pages: List[Page] = []

    for page in target_pages:
        await page.fetch()

        if not is_critical_rating_reached(page):
            await page.remove_tags([config["tags"]["deletion"]])
            logger.info(f"Метка к удалению снята: {page}")

        elif await is_last_chance_expired(page):
            await page.delete_page()
            deleted_pages.append(page)
            logger.info(f"Страница удалена безвозвратно: {page}")

    if deleted_pages:
        report_thread = ForumThread(wiki, config["report"]["thread"])
        deletion_message = \
            config["report"]["prepend"] + "\n" + \
            "\n".join([
                config["report"]["line"] \
                .format(title=page.title, rating=page.rating, votes=page.votes_count, popularity=page.popularity, author=page.author.username, tags=", ".join(page.tags))
                for page in deleted_pages
            ])

        await report_thread.new_post(
            title=config["report"]["title"],
            source=deletion_message
        )

@bot.task(period=extract_period(config["runtime"]["work_period"]))
async def approve_marked():
    target_pages = await bot.list_pages(
        category=" ".join(config["deletion"]["categories"]),
        tags=" ".join(config["deletion"]["branch_tags"] + include_tags([config["tags"]["whitemark"]]) + exclude_tags([config["tags"]["approved"], config["tags"]["in_progress"], config["tags"]["protected"]])),
    )

    for page in target_pages:
        await page.fetch()

        if await is_ready_for_approvement(page):
            await page.update_tags(
                add_tags=[config["tags"]["approved"], config["tags"]["tagging"]],
                remove_tags=[config["tags"]["whitemark"]]
            )
            logger.info(f"Помечено к переносу: {page}")
        else:
            await page.remove_tags([config["tags"]["whitemark"]])
            logger.info(f"Проходной рейтинг утрачен: {page}")

@bot.task(period=extract_period(config["runtime"]["work_period"]))
async def handle_in_progress_articles():
    target_pages = await bot.list_pages(
        category=" ".join(config["deletion"]["categories"]),
        tags=" ".join(config["deletion"]["branch_tags"] + include_tags([config["tags"]["in_progress"]]) + exclude_tags([config["tags"]["protected"]])),
    )

    unwanted_tags = {config["tags"]["approved"], config["tags"]["tagging"], config["tags"]["whitemark"], config["tags"]["deletion"]}

    for page in target_pages:
        await page.fetch()

        if await is_in_progress_expired(page):
            prev_name = page.name
            thread = await page.get_thread()
            await page.rename(f"deleted:{page.name}")
            await page.set_tags({})
            await thread.new_post(
                title=config["posting"]["title"],
                source=config["posting"]["phrases"]["too_long_in_progress"]
            )
            logger.info(f"Статья в работе перенесена в архив удаленных: {prev_name} -> {page}")
        else:
            if unwanted_tags.intersection(page.tags):
                removed_tags = await page.remove_tags(unwanted_tags)
                logger.info(f"Удалены теги полигона для статьи в работе: {page.name} {removed_tags}")