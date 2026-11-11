"""What one account does in the product, and commercially, on one day.

Synthetic data, fictional company. Every number in this file is an assumption
about how customers behave (see docs/decisions/0005). The hidden traits drive
usage, setup, expansion and churn, so the models in Phase 3 have real patterns
to find, and usage really does fall before an account churns.
"""

from __future__ import annotations

import math
from datetime import timedelta

import numpy as np

from synth.accounts import compute_arr, user_id
from synth.util import clamp, pick

SETUP_STEPS = ("board_created", "users_invited", "integration_connected", "sso_configured")
USERS_NEEDED = 5  # "users_invited" counts as done once five people have a seat
EDITION_ORDER = ["free", "standard", "premium", "enterprise"]

WORK_TEMPLATES = ["kanban", "sprint", "roadmap", "project_plan"]
DOC_LIKE_TEMPLATES = ["meeting_notes", "wiki", "knowledge_base"]  # boards used as documents
INTEGRATIONS = ["chat", "calendar", "code_repository", "cloud_drive", "crm", "video_meetings"]
ASSIST_FEATURES = ["summarize", "draft", "search"]
PLATFORMS = ["web", "desktop", "mobile"]


def simulate_account_day(world, account, today, rng, out) -> None:
    """Move one account forward by one day and record the product events it produced."""
    age = (today - account.contract_start).days
    if age == 0:
        _sign_up(world, account, today, out)

    update_momentum(account, age, rng)
    active_users = _daily_usage(account, today, rng, out)
    _feature_usage(world, account, today, active_users, rng, out)
    _setup_progress(account, today, age, rng, out)
    _invite_users(account, today, age, rng, out)
    _commercial_changes(world, account, today, age, rng)


def setup_closure(account) -> float:
    """Share of the four setup steps that are done (the brief's "prerequisite closure")."""
    return len(account.setup_done) / len(SETUP_STEPS)


def self_activation(account) -> float:
    """How much of the setup an admin does unaided, from 0 (nothing) to 1 (everything).

    Admins with a setup_drive below 0.35 do almost nothing on their own; above
    0.6 they do it all. The ones in between are who a nudge can tip over.
    """
    return clamp((account.setup_drive - 0.35) / 0.25, 0.0, 1.0)


def seat_utilisation(account) -> float:
    return account.seats_assigned / account.seats_licensed


def assist_credits_30d(account) -> int:
    return sum(account.credits_log[-30:])


def at_edition_limit(world, account) -> bool:
    """True when the account has run into a limit that the next edition would lift."""
    limits = world.cfg["editions"][account.edition]
    included_credits = limits["assist_credits_per_seat"] * account.seats_licensed
    return (
        account.n_rules >= limits["automation_rules"]
        or account.n_integrations >= limits["integrations"]
        or ("assist" in account.products and assist_credits_30d(account) >= 0.9 * included_credits)
    )


def churn_hazard(account, today) -> float:
    """Chance that the account cancels today. Rises steeply as momentum falls."""
    age = (today - account.contract_start).days
    if age < 30:
        return 0.0
    hazard = 0.0005 * math.exp(5.0 * (0.75 - account.momentum))
    if 0 <= (account.renewal_date - today).days <= 30:
        hazard *= 2.5  # renewal is when people reconsider
    return min(hazard, 0.5)


# --- Momentum: the hidden health of the relationship -------------------------------------


def update_momentum(account, age: int, rng) -> None:
    """Momentum drifts toward a level set by product fit, with noise and the odd shock."""
    target = 0.35 + 0.75 * account.fit - account.setback
    if age > 14:
        # Accounts that never finish setup fade. This is why the onboarding play matters.
        target -= 0.15 * (1 - setup_closure(account))
    momentum = account.momentum + 0.02 * (target - account.momentum) + rng.normal(0, 0.015)

    account.setback *= 0.99  # old damage heals slowly (half gone after about ten weeks)
    if rng.random() < 0.002:
        # A shock: the champion leaves, a reorganisation, a competitor trial.
        # Usage dips at once and keeps sliding for weeks. This is what "usage_drop" detects.
        momentum -= 0.15
        account.setback += rng.uniform(0.2, 0.4)

    if account.friction_days_left > 0:
        # A run of support problems drags the account down while it lasts.
        momentum -= 0.008
        account.friction_days_left -= 1
    elif rng.random() < 0.003 * (1.4 - account.fit):
        account.friction_days_left = int(rng.integers(8, 21))

    account.momentum = clamp(momentum, 0.05, 1.25)


# --- Product usage -----------------------------------------------------------------------


def _sign_up(world, account, today, out) -> None:
    """Day one for a new account: the admin gets the first seat and the deal is booked."""
    account.seats_assigned = 1
    admin = user_id(account, 0)
    out.add(account.account_id, admin, "user_invited", {"invited_user_id": admin, "role": "admin"})
    if account.arr > 0:
        world.add_opportunity(
            account, "new_business", "New business", "closed_won", account.arr,
            created_at=today, close_date=today,
        )  # fmt: skip


def _daily_usage(account, today, rng, out) -> np.ndarray:
    """Decide which users are active today. Returns their user numbers."""
    seats = account.seats_assigned
    weekday_factor = 1.0 if today.weekday() < 5 else 0.15
    momentum = min(account.momentum, 1.0)

    # Only part of the team really uses the product. That part shrinks when momentum falls,
    # which is what makes monthly active users drop before an account churns.
    engaged = math.ceil(seats * (0.45 + 0.5 * account.engagement) * momentum**1.3)
    engaged = min(seats, max(1, engaged))
    chance = np.full(seats, 0.004)  # everyone else almost never logs in
    chance[:engaged] = (0.25 + 0.45 * account.engagement) * np.linspace(1.3, 0.5, engaged)
    active = np.flatnonzero(rng.random(seats) < chance * weekday_factor)

    sessions = rng.integers(1, 6, size=len(active)).tolist()
    platforms = rng.integers(0, len(PLATFORMS), size=len(active)).tolist()
    for index, n_sessions, platform in zip(active.tolist(), sessions, platforms, strict=True):
        out.add(
            account.account_id, user_id(account, index), "user_active",
            {"sessions": n_sessions, "platform": PLATFORMS[platform]},
        )  # fmt: skip
    if rng.random() < 0.35 * momentum * weekday_factor:
        out.add(account.account_id, user_id(account, 0), "admin_login", {})

    account.dau_log.append(len(active))
    return active


def _feature_usage(world, account, today, active, rng, out) -> None:
    """Boards, docs, automation rules, integrations and the AI assistant."""
    n_active = len(active)
    if n_active == 0:
        if "assist" in account.products:
            account.credits_log.append(0)
        return
    limits = world.cfg["editions"][account.edition]
    account_id = account.account_id

    def someone() -> str:
        return user_id(account, int(active[rng.integers(n_active)]))

    # Boards. Teams with no Docs product but a real need for one use boards as documents.
    needs_docs = "docs" not in account.products and account.docs_need > 0.5
    doc_like_share = 0.6 if needs_docs else 0.08
    for _ in range(rng.poisson(n_active * 0.03)):
        account.n_boards += 1
        if rng.random() < doc_like_share:
            template = pick(rng, DOC_LIKE_TEMPLATES)
            account.doc_like_board_days.append(world.day_index)
        else:
            template = pick(rng, WORK_TEMPLATES)
        board = {"board_id": f"{account_id}-b{account.n_boards:04d}", "template": template}
        out.add(account_id, someone(), "board_created", board)
        account.setup_done.setdefault("board_created", today)

    if "docs" in account.products:
        for _ in range(rng.poisson(n_active * 0.05)):
            account.n_docs += 1
            doc = {
                "doc_id": f"{account_id}-d{account.n_docs:04d}",
                "word_count": int(rng.integers(80, 2500)),
            }
            out.add(account_id, someone(), "doc_published", doc)

    # Automation rules stop at the edition limit. Sitting at the limit is an upgrade signal.
    room = limits["automation_rules"] - account.n_rules
    wanted = rng.poisson(n_active * 0.015 * (0.5 + account.engagement))
    for _ in range(min(room, wanted)):
        account.n_rules += 1
        out.add(
            account_id, someone(), "automation_rule_created",
            {"rule_id": f"{account_id}-r{account.n_rules:04d}", "rules_total": account.n_rules},
        )  # fmt: skip

    # More integrations after the first one, up to the edition limit.
    has_first = "integration_connected" in account.setup_done
    if has_first and account.n_integrations < limits["integrations"]:
        if rng.random() < 0.004 * (0.5 + account.engagement):
            account.n_integrations += 1
            out.add(
                account_id, user_id(account, 0), "integration_connected",
                {"integration": pick(rng, INTEGRATIONS)},
            )  # fmt: skip

    # The AI assistant is usage-based: every call spends credits (this is "consumption").
    if "assist" in account.products:
        credits_today = 0
        for _ in range(rng.binomial(n_active, 0.08 + 0.5 * account.assist_affinity)):
            credits = int(rng.integers(1, 13))
            credits_today += credits
            out.add(
                account_id, someone(), "assist_invoked",
                {"credits_used": credits, "feature": pick(rng, ASSIST_FEATURES)},
            )  # fmt: skip
        account.credits_log.append(credits_today)


def _setup_progress(account, today, age: int, rng, out) -> None:
    """The admin may finish a setup step today.

    The chance depends on the hidden "setup_drive" and fades with account age:
    a team that has not set up SSO in its first weeks rarely does so later
    without a nudge. That fading is the gap the onboarding play is built to close.
    """
    done = account.setup_done
    drive = account.setup_drive
    unaided = self_activation(account)
    fade = max(0.08, math.exp(-age / 45))
    admin = user_id(account, 0)
    # Daily chance of each step. A first board is easy; integrations and SSO are not.
    board_chance = (0.05 + 0.5 * drive) * fade
    integration_chance = (0.002 + 0.05 * unaided * drive) * fade
    sso_chance = (0.001 + 0.035 * unaided * drive) * fade

    if "board_created" not in done and rng.random() < board_chance:
        account.n_boards += 1
        out.add(
            account.account_id, admin, "board_created",
            {"board_id": f"{account.account_id}-b{account.n_boards:04d}", "template": "kanban"},
        )  # fmt: skip
        done["board_created"] = today
    if "integration_connected" not in done and rng.random() < integration_chance:
        account.n_integrations = 1
        integration = pick(rng, INTEGRATIONS)
        out.add(account.account_id, admin, "integration_connected", {"integration": integration})
        done["integration_connected"] = today
    if "sso_configured" not in done and rng.random() < sso_chance:
        protocol = pick(rng, ["saml", "oidc"])
        out.add(account.account_id, admin, "sso_configured", {"protocol": protocol})
        done["sso_configured"] = today


def _invite_users(account, today, age: int, rng, out) -> None:
    """New seats: a burst in the first weeks, then steady growth for growing teams.

    Low-drive admins invite few people, so their accounts stay below five users
    for a long time. Those are the stalled onboardings.
    """
    unaided = self_activation(account)
    account.team_size *= 1 + 0.0035 * account.growth * min(account.momentum, 1.0)
    room = min(account.seats_licensed, round(account.team_size)) - account.seats_assigned
    if room > 0:
        early_burst = (0.03 + 1.6 * unaided) * math.exp(-age / 20)
        steady = (0.002 + 0.03 * unaided) * room
        admin = user_id(account, 0)
        for _ in range(min(room, rng.poisson(early_burst + steady))):
            new_user = user_id(account, account.seats_assigned)
            account.seats_assigned += 1
            out.add(
                account.account_id, admin, "user_invited",
                {"invited_user_id": new_user, "role": "member"},
            )  # fmt: skip
    if account.seats_assigned >= USERS_NEEDED:
        account.setup_done.setdefault("users_invited", today)


# --- Commercial changes: renewal, expansion, upgrade, churn ----------------------------


def _commercial_changes(world, account, today, age: int, rng) -> None:
    # Renewal: an opportunity opens 90 days out, may move to negotiation, closes on the day.
    if account.arr > 0:
        days_to_renewal = (account.renewal_date - today).days
        if days_to_renewal == 90:
            account.open_renewal = world.add_opportunity(
                account, "renewal", "Annual renewal", "open", account.arr,
                created_at=today, close_date=account.renewal_date,
            )  # fmt: skip
        elif days_to_renewal == 40 and account.open_renewal and rng.random() < 0.5:
            account.open_renewal["stage"] = "negotiation"
        elif days_to_renewal == 0:
            if account.open_renewal:
                account.open_renewal["stage"] = "closed_won"
                account.open_renewal["amount"] = account.arr
                account.open_renewal = None
            account.renewal_date += timedelta(days=365)

    momentum = min(account.momentum, 1.0)

    # Seat expansion: likely once nearly every licensed seat is taken.
    if seat_utilisation(account) >= 0.9:
        chance = 0.004 + 0.03 * account.growth * account.fit
    else:
        chance = 0.0002
    if rng.random() < chance * momentum:
        _expand_seats(world, account, today, rng)

    # Edition upgrade: likely once the account keeps hitting a limit of its edition.
    if account.edition != "enterprise" and at_edition_limit(world, account):
        if rng.random() < 0.005 * account.fit:
            _upgrade_edition(world, account, today, rng)

    if rng.random() < churn_hazard(account, today):
        account.status = "churned"
        account.churned_at = today
        if account.open_renewal:
            account.open_renewal["stage"] = "closed_lost"
            account.open_renewal["close_date"] = today
            account.open_renewal = None


def _expand_seats(world, account, today, rng) -> None:
    cfg = world.cfg
    old_arr = account.arr
    added = max(2, round(account.seats_licensed * rng.uniform(0.2, 0.5)))
    if account.edition == "free":
        account.edition = "standard"  # the free edition has a seat cap, so growing means paying
    account.seats_licensed += added
    account.team_size = max(account.team_size, account.seats_assigned + 1.0)  # they needed more
    account.arr = compute_arr(cfg, account.edition, account.seats_licensed, account.discount)
    _book_expansion(world, account, today, rng, f"Seat expansion (+{added})", account.arr - old_arr)


def _upgrade_edition(world, account, today, rng) -> None:
    cfg = world.cfg
    old_arr = account.arr
    account.edition = EDITION_ORDER[EDITION_ORDER.index(account.edition) + 1]
    account.arr = compute_arr(cfg, account.edition, account.seats_licensed, account.discount)
    name = f"Edition upgrade to {account.edition}"
    _book_expansion(world, account, today, rng, name, account.arr - old_arr)


def _book_expansion(world, account, today, rng, name: str, amount: int) -> None:
    opened = max(account.contract_start, today - timedelta(days=int(rng.integers(3, 21))))
    world.add_opportunity(
        account, "expansion", name, "closed_won", amount, created_at=opened, close_date=today
    )
