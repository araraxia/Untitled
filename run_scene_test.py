"""[DEV ONLY] Standalone smoke test for client/engine/scene.py's
`Scene` class -- no GPU, no window, no backend/network involvement.
Steps 3-4 of .github/prompts/area-system.prompt.md.

Mirrors run_gametick_test.py's no-GPU verification pattern: a real,
permanent script, not a one-off manual check.

Usage:
    python run_scene_test.py
"""

import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.independant_logger import Logger

logger = Logger(
    log_name="run_scene_test",
    log_file="scene_test.log",
    log_level=20,  # INFO
).get_logger()

from client.engine.scene import Scene


def check(label: str, condition: bool) -> None:
    status = "PASS" if condition else "FAIL"
    logger.info(f"[{status}] {label}")
    if not condition:
        raise AssertionError(label)


def test_add_entity_source_conflict() -> None:
    scene = Scene()
    ok1 = scene.add_entity("a", {"x": 0}, "authoritative")
    check("add_entity: first add (authoritative) succeeds", ok1 is True)

    ok2 = scene.add_entity("a", {"x": 5}, "local")
    check("add_entity: cross-source overwrite refused", ok2 is False)
    check("add_entity: refused write did not mutate data", scene.entities["a"]["x"] == 0)

    ok3 = scene.add_entity("a", {"x": 10}, "authoritative")
    check("add_entity: same-source overwrite proceeds", ok3 is True)
    check("add_entity: same-source overwrite applied", scene.entities["a"]["x"] == 10)


def test_update_and_remove_entity() -> None:
    scene = Scene()
    scene.add_entity("a", {"x": 0, "y": 0}, "local")
    scene.update_entity("a", {"y": 5})
    check("update_entity: merge applied", scene.entities["a"] == {"x": 0, "y": 5})

    scene.update_entity("missing", {"y": 5})  # should warn, not raise
    check("update_entity: unknown id is a no-op, not a crash", "missing" not in scene.entities)

    scene.remove_entity("a")
    check("remove_entity: entity gone", "a" not in scene.entities)
    check("remove_entity: source tag gone too", scene.entity_source("a") is None)


def test_set_lighting_dual_write() -> None:
    scene = Scene()
    scene.set_lighting({"ambientColor": [0.5, 0.5, 0.5], "fogFar": 1000})
    check("set_lighting: recorded on scene.lighting", scene.lighting["fogFar"] == 1000)
    check(
        "set_lighting: dual-written onto scene.camera (renderer reads it from here)",
        scene.camera["fogFar"] == 1000 and scene.camera["ambientColor"] == [0.5, 0.5, 0.5],
    )


def test_start_camera_decoupled_from_live_camera() -> None:
    scene = Scene()
    scene.set_start_camera({"mode": "3d", "position": [0, 0, 0]})
    scene.set_camera({"mode": "3d", "position": [999, 999, 999]})  # simulates free-fly movement
    check(
        "start_camera untouched by set_camera (free-fly never changes the saved spawn point)",
        scene.start_camera["position"] == [0, 0, 0],
    )
    check("live camera did move", scene.camera["position"] == [999, 999, 999])


def test_zones_round_trip_and_api() -> None:
    scene = Scene()
    scene.add_zone("zone_a", {"shape": {"type": "aabb"}, "on_enter": [], "on_exit": []})
    scene.update_zone("zone_a", {"tags": ["water"]})
    check("update_zone: merge applied", scene.zones["zone_a"]["tags"] == ["water"])
    scene.remove_zone("zone_a")
    check("remove_zone: zone gone", "zone_a" not in scene.zones)


def test_load_and_save_round_trip() -> None:
    area_data = {
        "entities": {
            "crate": {
                "entity_id": "crate",
                "x": 10,
                "y": 0,
                "z": 5,
                "render_template": "entity-example-crate",
            }
        },
        "camera": {"mode": "3d", "position": [0, 100, 300], "target": [0, 0, 0]},
        "lighting": {"ambientColor": [1, 1, 1], "fogFar": 0},
        "zones": {
            "zone_a": {
                "shape": {"type": "aabb", "min": [0, 0, 0], "max": [10, 10, 10]},
                "on_enter": [{"type": "fire_event", "event": "test"}],
                "on_exit": [],
            }
        },
    }

    with tempfile.TemporaryDirectory() as tmp_dir:
        src_path = Path(tmp_dir) / "area-test.json"
        src_path.write_text(json.dumps(area_data), encoding="utf-8")

        scene = Scene.load_from_area_file(src_path)
        check("load: entity present", "crate" in scene.entities)
        check("load: entity tagged authoritative", scene.entity_source("crate") == "authoritative")
        check("load: camera applied to live view", scene.camera["position"] == [0, 100, 300])
        check("load: start_camera captured separately", scene.start_camera["position"] == [0, 100, 300])
        check("load: lighting recorded", scene.lighting["ambientColor"] == [1, 1, 1])
        check("load: zone present -- this is the gap the audit found and fixed", "zone_a" in scene.zones)

        # Simulate free-fly moving the live camera after load -- must
        # not affect what gets saved (the whole point of start_camera).
        scene.set_camera({"position": [500, 500, 500]})

        out_path = Path(tmp_dir) / "area-test-out.json"
        scene.save_to_area_file(out_path)
        round_tripped = json.loads(out_path.read_text(encoding="utf-8"))

        check(
            "save: camera saved is the authored start_camera, not the free-flown live camera",
            round_tripped["camera"]["position"] == [0, 100, 300],
        )
        check(
            "save: zones round-tripped losslessly (the concrete gap area-system.prompt.md's "
            "audit found -- Scene.zones/load/save didn't originally handle this key at all)",
            round_tripped["zones"] == area_data["zones"],
        )
        check("save: entities round-tripped", round_tripped["entities"] == area_data["entities"])

        # And loading the *saved* file back should reproduce the same
        # scene shape -- proves the round-trip is stable, not one-way.
        scene2 = Scene.load_from_area_file(out_path)
        check("re-load: zone present after round-trip", "zone_a" in scene2.zones)


def main() -> None:
    logger.info("=" * 50)
    logger.info("[DEV ONLY] Scene smoke test (no GPU, no backend)")
    logger.info("=" * 50)

    test_add_entity_source_conflict()
    test_update_and_remove_entity()
    test_set_lighting_dual_write()
    test_start_camera_decoupled_from_live_camera()
    test_zones_round_trip_and_api()
    test_load_and_save_round_trip()

    logger.info("PASS: Scene API, source-tagging, lighting dual-write, start_camera "
                "decoupling, and zones round-trip all verified.")


if __name__ == "__main__":
    main()
