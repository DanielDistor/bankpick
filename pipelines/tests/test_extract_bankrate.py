from pathlib import Path

from pipelines.extract_bankrate import should_save

FIXTURE = (Path(__file__).parent / "fixtures" / "bankrate_savings_2026-11-05.md").read_text()


def test_identical_page_is_not_saved():
    assert should_save(FIXTURE, FIXTURE) is False


def test_changed_apy_is_saved():
    changed = FIXTURE.replace("APY as of 11/3/2026\n    3.75%", "APY as of 11/3/2026\n    3.65%", 1)
    assert changed != FIXTURE
    assert should_save(changed, FIXTURE) is True


def test_new_weekly_history_point_is_saved():
    changed = FIXTURE.replace("11/03/2026| 3.75%| 0.57%", "11/10/2026| 3.75%| 0.57%  \n11/03/2026| 3.75%| 0.57%", 1)
    assert should_save(changed, FIXTURE) is True


def test_first_snapshot_is_saved():
    assert should_save(FIXTURE, None) is True
