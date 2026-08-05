from __future__ import annotations

from pathlib import Path


def test_moodle_image_uses_locked_lbplanner_dependencies() -> None:
    """Ensure the image build keeps LB Planner dependency resolution pinned."""
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"
    text = dockerfile.read_text()

    assert "COPY --from=lbplanner /composer.lock ./" in text
    assert "$composer['replace']" in text
    assert "composer install --no-dev" in text
    assert "composer update" not in text
