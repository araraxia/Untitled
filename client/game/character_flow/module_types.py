"""Character-flow module interface contract.

Port of frontend/js/game/characterFlow/moduleTypes.js -- Step 14
(checkpoint 2 of 4) of .github/prompts/wgpu-py-migration.prompt.md.
The JS original is pure type documentation (JSDoc `@typedef` comments)
plus a `window.CharacterFlow = window.CharacterFlow || {}`
namespace-object bootstrap. Python needs neither: each
`client/game/character_flow/*.py` file is already its own namespace
(imported directly, no shared global object to lazily initialize), and
this file's `Protocol` plays the JSDoc typedef's documentation-only
role.

**Deliberately synchronous, not `async def`**: JS's typedef allows
`init`/`mount`/`unmount`/`destroy` to return a `Promise` (real modules
may `await` inside them). Nothing this port's actual flow modules
(character_creation.py, checkpoint 4) do involves genuine async I/O --
`client/engine/network.py` (Step 11) already delivers SocketIO events
via synchronous callback registration, not awaited promises -- so
committing to `async def` here would require running an event loop for
no real benefit. Same reasoning as `gpu_sprite_sheet.py`'s Step 7
sync-`load()` decision.

**Every method here is optional, matching the JS original exactly**:
`flowController.js` guards every call with `typeof x.method ===
"function"` rather than assuming the interface is fully implemented.
`CharacterFlowModule` here is documentation for IDEs/type-checkers,
not an enforced contract -- `flow_controller.py` duck-types the same
way, via `callable(getattr(module, 'name', None))`.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class CharacterFlowModule(Protocol):
    """Shape a character-flow module may implement. All methods are
    optional -- see module docstring.
    """

    id: str

    def init(self, ctx: dict) -> None: ...
    def mount(self, ctx: dict) -> None: ...
    def unmount(self, ctx: dict) -> None: ...
    def handle_event(self, event_name: str, data: dict, ctx: dict) -> "bool | None": ...
    def destroy(self, ctx: dict) -> None: ...
