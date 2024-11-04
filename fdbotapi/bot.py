from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List

from .wiki import Wiki, Page, Endpoint, Route, Module

import asyncio
import logging

@dataclass
class Task:
    action: Callable
    name: str

@dataclass
class PeriodicTask(Task):
    period: int

class Bot:
    def __init__(self, wiki: Wiki):
        self.wiki = wiki
        self._on_startup: List[Task] = []
        self._on_shutdown: List[Task] = []
        self._scheduled_tasks: List[PeriodicTask] = []
        self._ev = asyncio.get_event_loop()
        self.is_running = False
        self._logger = logging.getLogger()

    def run(self):
        if self.is_running:
            return
        
        self._logger.debug("Running bot event loop")
        self.is_running = True

        for task in self._on_startup:
            self._ev.create_task(task.action())
        try:
            self._scheduler = self._ev.create_task(self._task_scheduler())
            self._ev.run_forever()
        finally:
            self.stop()

    def stop(self):
        if not self.is_running:
            return
        
        self._logger.debug("Stopping bot")
        self.is_running = False

        self._scheduler.cancel()
        
        for task in self._on_shutdown:
            self._ev.create_task(task.action())
        self._ev.create_task(self.wiki._close_api())

        self._ev.call_soon(self._ev.stop)
        if not self._ev.is_running():
            self._ev.run_forever()

    def auth(self, auth_token=None) -> Bot:
        if auth_token:
            self.wiki.token = auth_token
        return self
    
    def on_startup(self):
        def decorator(func):
            async def wrapper():
                return await func()
            
            self._on_startup.append(Task(wrapper, func.__name__))
            self._logger.debug(f"Added new startup task {func.__name__}")

            return wrapper
        return decorator
    
    def on_shutdown(self):
        def decorator(func):
            async def wrapper():
                return await func()
            
            self._on_shutdown.append(Task(wrapper, func.__name__))
            self._logger.debug(f"Added new shutdown task {func.__name__}")
            
            return wrapper
        return decorator

    def task(self, minutes=0, hours=0, days=0):
        if minutes + hours + days <= 0:
            raise ValueError("Task delay must be greater than zero.")

        def decorator(func):
            async def wrapper():
                return await func()
            
            self._scheduled_tasks.append(
                PeriodicTask(wrapper, func.__name__, minutes + hours * 60 + days * 1440)
            )
            self._logger.debug(f"Added new periodic task {func.__name__}")

            return wrapper
        return decorator
    
    async def _task_scheduler(self):
        cycles = 0

        while True:
            for task in self._scheduled_tasks:
                if cycles % task.period == 0:
                    self._ev.create_task(task.action())
                    self._logger.debug(f"Running periodic task {task.name}")

            await asyncio.sleep(60)
            cycles += 1
    
    async def get_page(self, page_id: str, lazy: bool=True) -> Page:
        return await self.wiki.get_page(page_id, lazy)

    async def api(self, endpoint: Endpoint | Route, *args, **kwargs):
        return await self.wiki.api(endpoint, *args, **kwargs)
    
    async def module(self, module: Module, method: str, **kwargs):
        return await self.wiki.module(module, method, **kwargs)
    
    async def list_pages(self, **params) -> List[Page]:
        return await self.wiki.list_pages(**params)
    
    async def get_all_pages(self) -> List[Page]:
        return await self.wiki.get_all_pages()