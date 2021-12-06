from core.wikidot import Wikidot
from core.logger import log
import config

from typing import Iterator, Callable, Optional, Union, Dict, List, Any
from abc import ABC, abstractmethod
from periodic import Periodic
import importlib
import sys
import os


sys.path.append(config.MODULES_FOLDER)


def inject(
    module: str, attr: str, value: Optional[Any] = None
) -> Union[Any, Callable[[Any], Any]]:
    """Inject value into selected module attribute.
    Note: This function is not safe. It can be used only in plugins for injecting variable into skippy source code.

    Args:
        module (str): Module name
        attr (str): Module attribute
        value (Optional[Any]): Value for injecting

    Returns:
        Union[Any, Callable[Any]]: If value is not None return value, else return decorator wrapper
    """

    def inject(value: Any) -> Any:
        """Inject value into selected module attribute.

        Args:
            value (Any): Value for injecting

        Returns:
            Any: Input value
        """
        loc = {}
        exec(f"import {module}; module = {module}", globals(), loc)
        setattr(loc["module"], attr, value)

        return value

    return inject(value) if value else inject


class AbstractModule(ABC):
    """Abstract module class

    Attributes:
        __alias__ (str): Module name
        __description__ (str): Module description
        __author__ (str): Module author
        __version__ (str): Module version

        interval (int): Interval for periodic run

        _wikidot (Wikidot): Wikidot singleton class
    """

    __alias__: str
    __description__: str
    __author__: str
    __version__: str

    interval: int

    def __init__(self):
        """Initializing module
        """
        self._wikidot = Wikidot()

        self.onReady()
        log.debug(f"Module \"{self.__alias__}\" was loaded")

    def start(self):
        """Start module
        """
        self.onStart()
        log.debug(f"Module \"{self.__alias__}\" was started")

    def stop(self):
        """Stop module
        """
        self.onStop()
        log.debug(f"Module \"{self.__alias__}\" was stopped")

    def run(self):
        """Run module
        """
        log.debug(f"Module \"{self.__alias__}\" is running")
        self.onRun()

    @abstractmethod
    def onRun(self):
        pass

    def onReady(self):
        pass

    def onStart(self):
        pass

    def onStop(self):
        pass

    @property
    def config(self):
        return config.load_config(self.__alias__)


class ModuleLoader:

    """Module loader class
    """

    def __init__(self):
        """Init module loader"""
        self._modules: List[AbstractModule] = []

    @staticmethod
    def modules() -> List[str]:
        """Get list of all modules

        Yields:
            List[str]: List of modules
        """
        return [
            os.path.splitext(file)[0]
            for file in os.listdir(config.MODULES_FOLDER)
            if os.path.isfile(os.path.join(config.MODULES_FOLDER, file))
            if file.endswith("_module.py")
        ]

    @classmethod
    def modules_data(cls) -> Iterator[Dict[str, str]]:
        """Get data of all modules

        Yields:
            Dict[str, str]: Module data
        """
        for file in cls.modules():
            module = cls.import_module(file)
            yield {
                "__alias__": module.__alias__,
                "__description__": module.__description__,
                "__author__": module.__author__,
                "__version__": module.__version__,
            }

    def load_modules(self):
        """Load all modules
        """
        for file in self.modules():
            module = self.import_module(file)
            self._modules.append(module)

    def start_modules(self):
        """Start all modules
        """
        for module in self._modules:
            module.start()

    def stop_modules(self):
        """Stop all modules
        """
        for module in self._modules:
            module.stop()

    @property
    def tasks(self) -> Iterator[Periodic]:
        """Get periodic tasks
        """
        for module in self._modules:
            yield Periodic(module.interval, module.run)

    @classmethod
    def import_module(cls, module: str) -> AbstractModule:
        """Import module by module name

        Args:
            module (str): Module name

        Returns:
            AbstractModule: Module instance
        """
        return importlib.import_module(module).load()
