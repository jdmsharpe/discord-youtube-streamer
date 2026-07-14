import logging
from asyncio import AbstractEventLoop
from collections.abc import Callable
from inspect import iscoroutinefunction


class EventBus:
    """Instance-scoped pub/sub. Each guild session owns its own bus so events
    raised by one guild's queue can never trigger another guild's voice client
    or UI (a module-level subscriber dict would broadcast to every guild)."""

    __slots__ = ("subscribers",)

    def __init__(self):
        self.subscribers: dict[str, list[Callable]] = {}

    def subscribe(self, event_type: str, function: Callable) -> None:
        self.subscribers.setdefault(event_type, []).append(function)

    def post(self, event_type: str, loop: AbstractEventLoop, *args) -> None:
        for function in self.subscribers.get(event_type, []):
            if iscoroutinefunction(function):
                try:
                    loop.create_task(function(*args))
                except (TypeError, RuntimeError) as error:
                    logging.error("Unable to create task for %s: %s", function, error)
            elif callable(function):
                try:
                    function(*args)
                except TypeError as error:
                    logging.error("Unable to run function for %s: %s", function, error)
            else:
                logging.error("%s not detected to be a valid callable or coroutine", function)
