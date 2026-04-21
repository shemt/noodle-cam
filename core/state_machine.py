import logging
from enum import Enum, auto
from typing import Callable, Dict, Any

logger = logging.getLogger(__name__)


class State(Enum):
    IDLE = auto()
    GUIDING = auto()
    COOKING = auto()
    WAITING = auto()


class StateMachine:
    def __init__(self):
        self.state = State.IDLE
        self._transitions: Dict[State, Dict[str, State]] = {
            State.IDLE: {"customer_approach": State.GUIDING},
            State.GUIDING: {"bowl_placed": State.COOKING, "timeout": State.IDLE},
            State.COOKING: {"meal_ready": State.WAITING, "bowl_removed": State.IDLE},
            State.WAITING: {"bowl_removed": State.IDLE, "timeout": State.IDLE},
        }
        self._handlers: Dict[str, Callable] = {}
        self.context: Dict[str, Any] = {}

    def on(self, event: str, handler: Callable):
        self._handlers[event] = handler
        return self

    def trigger(self, event: str, **kwargs) -> bool:
        if self.state not in self._transitions:
            logger.warning(f"当前状态 {self.state} 无转移定义")
            return False

        allowed = self._transitions[self.state]
        if event not in allowed:
            logger.debug(f"状态 {self.state.name} 忽略事件 {event}")
            return False

        old_state = self.state
        self.state = allowed[event]
        self.context.update(kwargs)
        logger.info(f"状态转移: {old_state.name} -> {self.state.name} (事件: {event})")

        handler = self._handlers.get(event)
        if handler:
            try:
                handler(old_state, self.state, self.context)
            except Exception as e:
                logger.error(f"事件处理器异常: {e}")
        return True

    def reset(self):
        self.state = State.IDLE
        self.context.clear()
