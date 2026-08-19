"""Frame-based animation clip playback.

Port of frontend/js/engine/sprites/animation.js -- Step 7 of
.github/prompts/wgpu-py-migration.prompt.md.

Deliberate omission, noted for the same reason as client/engine's
missing spritesheet.py (see that module's absence, Step 3): the JS
`AnimationController.draw(ctx, x, y, flipX)` calls a Canvas-2D
`SpriteSheet.drawFrame()`, which has no native-client equivalent -- this
client has no 2D canvas fallback surface at all. The state-tracking API
(`play`/`update`/`current_frame`) is ported faithfully and is exactly
what entity_renderer.py (Step 9) needs; frame selection for an actual
GPU draw happens there via `gpu_sprite_sheet.get_uv_rect(current_frame)`,
not via a `draw()` method on this class.
"""


class Animation:
    """A single animation sequence.

    Args:
        name: Name of the animation.
        start_frame: Starting frame index in the sprite sheet.
        frame_count: Total number of frames in this animation.
        frame_time: Duration of each frame in milliseconds.
        loop: Whether the animation should loop.
    """

    def __init__(
        self,
        name: str,
        start_frame: int,
        frame_count: int,
        frame_time: float,
        loop: bool = True,
    ):
        self.name = name
        self.start_frame = start_frame
        self.frame_count = frame_count
        self.frame_time = frame_time
        self.loop = loop


class AnimationController:
    """Controls and manages sprite animation playback state.

    Args:
        animations: dict mapping animation names to Animation instances.
    """

    def __init__(self, animations: dict):
        self.animations = animations
        self.current_animation: "Animation | None" = None
        self.current_frame = 0
        self.time_accumulator = 0.0

    def play(self, animation_name: str) -> None:
        """Play a specific animation by name. Only resets if switching
        to a different animation -- calling play() with the
        already-playing animation's name is a no-op, matching the JS
        version's behaviour exactly (this is what lets
        entity_renderer.py wire an entity.state -> animation-name
        mapping unconditionally every frame without constantly
        restarting the clip).
        """
        if self.current_animation is not None and self.current_animation.name == animation_name:
            return

        self.current_animation = self.animations.get(animation_name)
        if self.current_animation is not None:
            self.current_frame = self.current_animation.start_frame
            self.time_accumulator = 0.0

    def update(self, delta_time: float) -> None:
        """Update the animation state based on elapsed time.

        Args:
            delta_time: Time elapsed since last update, in milliseconds
                (matches the JS version's unit -- callers pass the same
                millisecond delta used elsewhere in this port).
        """
        if self.current_animation is None:
            return

        self.time_accumulator += delta_time

        if self.time_accumulator >= self.current_animation.frame_time:
            self.time_accumulator -= self.current_animation.frame_time
            self.current_frame += 1

            max_frame = self.current_animation.start_frame + self.current_animation.frame_count

            if self.current_frame >= max_frame:
                if self.current_animation.loop:
                    self.current_frame = self.current_animation.start_frame
                else:
                    self.current_frame = max_frame - 1
