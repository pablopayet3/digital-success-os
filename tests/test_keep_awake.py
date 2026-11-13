"""The keep-awake schedule must fit in the host's free hours (ADR 0026).

Synthetic data, fictional company. The free host stops the app after 15 minutes without a
visitor, and gives 750 running hours a month to the app and the API together. When those
hours are used up it suspends both until the next month, which is worse than a slow first
page. So the schedule is checked here, not left to arithmetic done once by hand.
"""

import yaml

from common.paths import ROOT

WORKFLOW = ROOT / ".github" / "workflows" / "keep-awake.yml"
FREE_HOURS_A_MONTH = 750  # one allowance, shared by the app and the API
HOURS_LEFT_FOR_THE_REST = 200  # the API, and visits to the app outside the schedule
MINUTES_BEFORE_THE_HOST_STOPS_THE_APP = 15


def schedule() -> list[str]:
    """The five fields of the workflow's one cron line: minute, hour, day, month, weekday."""
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    lines = workflow[True]["schedule"]  # PyYAML reads the key "on" as the value True
    assert len(lines) == 1
    return lines[0]["cron"].split()


def hours_named(field: str) -> set[int]:
    """The hours named by the hour field of a cron line, such as "11-23,0-2"."""
    hours: set[int] = set()
    for part in field.split(","):
        first, _, last = part.partition("-")
        hours.update(range(int(first), int(last or first) + 1))
    return hours


def test_the_schedule_fits_in_the_free_hours():
    _, hour, day, month, weekday = schedule()
    assert (day, month, weekday) == ("*", "*", "*")  # every day, so 31 days in the longest month
    awake_in_a_month = len(hours_named(hour)) * 31
    assert awake_in_a_month <= FREE_HOURS_A_MONTH - HOURS_LEFT_FOR_THE_REST


def test_one_missed_request_does_not_let_the_app_sleep():
    minute = schedule()[0]
    minutes_apart = int(minute.partition("/")[2])
    # If one request is dropped, the next must still arrive before the host stops the app.
    assert 2 * minutes_apart < MINUTES_BEFORE_THE_HOST_STOPS_THE_APP


def test_it_asks_for_the_address_the_readme_gives():
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    address = workflow["env"]["APP_URL"].rstrip("/")
    assert address in (ROOT / "README.md").read_text(encoding="utf-8")
    assert workflow["permissions"] == {}  # the job needs no access to the repository
