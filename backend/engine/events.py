"""Engine EventBus — synchronous publish/subscribe broker."""

from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional


class EventBus:
    """Synchronous publish/subscribe message broker.

    Events are dispatched within the tick that publishes them.
    Handlers are invoked in subscription order.

    Typical use::

        bus = EventBus()

        def on_death(payload):
            print(f"Entity {payload['id']} died")

        bus.subscribe('entity_died', on_death)
        bus.publish('entity_died', {'id': 'abc'})
        bus.unsubscribe('entity_died', on_death)

    Notes:
        Replaces direct SocketIO calls for internal simulation
        communication.  SocketIO remains only for the client ↔
        server boundary.
    """

    def __init__(self) -> None:
        self._handlers: Dict[str, List[Callable[[Any], None]]] = defaultdict(list)

    def subscribe(
        self,
        event_type: str,
        handler: Callable[[Any], None],
    ) -> None:
        """Register *handler* for *event_type*.

        Duplicate registrations are silently ignored.
        """
        if handler not in self._handlers[event_type]:
            self._handlers[event_type].append(handler)

    def unsubscribe(
        self,
        event_type: str,
        handler: Callable[[Any], None],
    ) -> None:
        """Remove *handler* from *event_type*.

        No-op if the handler is not registered.
        """
        try:
            self._handlers[event_type].remove(handler)
        except ValueError:
            pass

    def publish(
        self,
        event_type: str,
        payload: Optional[Any] = None,
    ) -> None:
        """Dispatch *payload* to all handlers for *event_type*.

        A snapshot of the handler list is taken before dispatch so
        that handlers that unsubscribe during delivery do not affect
        the current batch.
        """
        for handler in list(self._handlers[event_type]):
            handler(payload)

    def clear(self, event_type: Optional[str] = None) -> None:
        """Remove all handlers, or only those for *event_type*."""
        if event_type is None:
            self._handlers.clear()
        else:
            self._handlers.pop(event_type, None)
