"""Engine layer — the Python analog of frontend/js/engine/.

Stable, reusable rendering/asset/network/input infrastructure. Must never
import from client.game (mirrors the existing frontend/js/engine/ vs.
frontend/js/game/ rule — see CLAUDE.md's "Engine vs. Game Separation").
"""
