"""Accounts and contacts: who exists in the world, and their hidden traits.

Synthetic data, fictional company. Customer names are invented words, so they
cannot be mistaken for real businesses. Every email uses the reserved
".example" domain.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import numpy as np

from synth.util import clamp, pick, weighted_pick

# Invented company names: one piece from each list, for example "Velora Logistics".
STEM_A = [
    "Vel", "Tor", "Quin", "Bram", "Zan", "Lor", "Mer", "Cav", "Dov", "Fen",
    "Hal", "Jor", "Kel", "Nor", "Pell", "Rav", "Sor", "Tev", "Ul", "Wex",
    "Yor", "Arv", "Bex", "Drin", "Eld", "Garr", "Hest", "Isk", "Lund", "Osk",
]  # fmt: skip
STEM_B = [
    "avo", "enta", "exo", "ora", "une", "ivo", "anda", "eth",
    "olo", "ium", "yx", "essa", "arro", "isko", "omi", "uvia",
]  # fmt: skip
NAME_SUFFIX = [
    "Logistics", "Health", "Foods", "Studios", "Robotics", "Freight", "Clinics",
    "Media", "Energy", "Supply", "Analytics", "Systems", "Partners", "Works",
    "Education", "Retail", "Finance", "Builders", "Travel", "Software",
]  # fmt: skip

INDUSTRIES = [
    "software", "healthcare", "logistics", "retail", "education",
    "finance", "manufacturing", "media", "nonprofit", "professional_services",
]  # fmt: skip
REGIONS = {"AMER": 0.50, "EMEA": 0.35, "APAC": 0.15}

ROLES = {
    "admin": ["IT Manager", "Operations Lead", "Workspace Admin", "Head of IT", "Systems Admin"],
    "billing": ["Finance Manager", "Accounts Payable", "Office Manager"],
    "champion": ["Head of Product", "Engineering Manager", "Program Director", "Team Lead"],
    "end_user": ["Project Manager", "Designer", "Engineer", "Analyst", "Coordinator"],
}

# How likely each persona is to have given consent to marketing email.
CONSENT_BY_PERSONA = {
    "admin": {"opted_in": 0.92, "unknown": 0.05, "opted_out": 0.03},
    "champion": {"opted_in": 0.80, "unknown": 0.15, "opted_out": 0.05},
    "billing": {"opted_in": 0.55, "unknown": 0.35, "opted_out": 0.10},
    "end_user": {"opted_in": 0.50, "unknown": 0.38, "opted_out": 0.12},
}
# How much each persona reads our email, compared with the account's overall engagement.
EMAIL_INTEREST = {"admin": 1.0, "champion": 1.2, "billing": 0.5, "end_user": 0.6}

ASSIST_OWNERSHIP = {"free": 0.0, "standard": 0.25, "premium": 0.50, "enterprise": 0.70}


@dataclass
class Contact:
    contact_id: str
    account_id: str
    full_name: str
    email: str
    persona: str  # admin | billing | champion | end_user
    role: str
    consent_status: str  # opted_in | opted_out | unknown
    email_valid: bool
    product_user_id: str | None  # links the CRM contact to a product user, when known
    last_engaged_at: datetime | None
    # Hidden (never exported to the landing files):
    affinity: float  # how likely this person is to open and click our emails
    has_left: bool  # left the company, but the CRM does not know yet


@dataclass
class Account:
    # What the CRM knows
    account_id: str
    name: str
    domain: str
    segment: str  # smb | mid | enterprise
    coverage_tier: str  # high_touch | pooled | uncovered
    edition: str  # free | standard | premium | enterprise
    products: list[str]  # boards, docs, assist
    seats_licensed: int
    discount: float
    arr: int
    contract_start: date
    renewal_date: date
    region: str
    industry: str
    account_owner: str
    csm: str | None
    # Hidden traits, each between 0 and 1. They drive everything the account does.
    engagement: float  # how much this team uses software like ours
    fit: float  # how well the product fits their needs
    growth: float  # how fast the team is growing
    docs_need: float  # how much they need a knowledge base
    setup_drive: float  # how likely the admin is to finish setup unaided
    assist_affinity: float  # how much they use the AI assistant
    # Hidden state: goes up and down over time. Low momentum comes before churn.
    momentum: float
    team_size: float  # how many people should have a seat; grows for growing teams
    setback: float = 0.0  # lasting damage from a shock (champion left, reorganisation)
    friction_days_left: int = 0  # days left in a run of support problems
    # Visible state
    status: str = "active"  # active | churned
    churned_at: date | None = None
    seats_assigned: int = 0
    setup_done: dict = field(default_factory=dict)  # setup step -> date completed
    n_boards: int = 0
    n_docs: int = 0
    n_rules: int = 0
    n_integrations: int = 0
    contacts: list = field(default_factory=list)
    open_renewal: dict | None = None
    # Short histories kept for the generation report
    dau_log: list = field(default_factory=list)
    credits_log: list = field(default_factory=list)
    doc_like_board_days: list = field(default_factory=list)


def compute_arr(cfg: dict, edition: str, seats: int, discount: float) -> int:
    """Annual recurring revenue: seats x list price x negotiated discount."""
    return round(seats * cfg["editions"][edition]["price_per_seat_year"] * discount)


def next_renewal(contract_start: date, on_or_after: date) -> date:
    """Contracts renew every 365 days. Find the first renewal date not in the past."""
    renewal = contract_start + timedelta(days=365)
    while renewal < on_or_after:
        renewal += timedelta(days=365)
    return renewal


def user_id(account: Account, index: int) -> str:
    """Product user ids look like A0042-u003. User 0 is always the first admin."""
    return f"{account.account_id}-u{index:03d}"


def build_population(world, rng: np.random.Generator, fake) -> None:
    """Create every account and contact, including accounts that sign up later."""
    cfg = world.cfg
    n_accounts = cfg["volumes"]["accounts"]
    start = world.start_date
    total_days = cfg["calendar"]["history_days"] + cfg["calendar"]["pilot_days"]

    reps = [fake.name() for _ in range(12)]
    csms = [fake.name() for _ in range(6)]
    name_ids = rng.choice(len(STEM_A) * len(STEM_B) * len(NAME_SUFFIX), n_accounts, replace=False)

    for i in range(n_accounts):
        name = _company_name(int(name_ids[i]))
        segment = weighted_pick(rng, {s: v["share"] for s, v in cfg["segments"].items()})
        seg_cfg = cfg["segments"][segment]
        coverage = weighted_pick(rng, seg_cfg["coverage"])
        edition = weighted_pick(rng, cfg["edition_mix"][segment])

        established = rng.random() < cfg["volumes"]["share_established"]
        if established:
            contract_start = start - timedelta(days=int(rng.integers(30, 900)))
        else:
            contract_start = start + timedelta(days=int(rng.integers(0, total_days)))

        # The three hidden traits from the brief, plus three smaller ones derived for realism.
        engagement = float(rng.beta(2.0, 2.0))
        fit = float(rng.beta(1.6, 1.6))
        growth = float(rng.beta(1.6, 2.2))
        setup_drive = clamp(0.6 * engagement + 0.4 * fit + rng.normal(0, 0.12), 0.02, 0.98)

        seats = int(rng.integers(seg_cfg["seats"][0], seg_cfg["seats"][1] + 1))
        if edition == "free":
            seats = min(seats, cfg["editions"]["free"]["max_seats"])
        products = ["boards"]
        if rng.random() < 0.55:
            products.append("docs")
        if rng.random() < ASSIST_OWNERSHIP[edition]:
            products.append("assist")
        discount = round(float(rng.uniform(0.8, 1.0)), 2)

        account = Account(
            account_id=f"A{i + 1:04d}",
            name=name,
            domain=re.sub(r"[^a-z]+", "-", name.lower()) + ".example",
            segment=segment,
            coverage_tier=coverage,
            edition=edition,
            products=products,
            seats_licensed=seats,
            discount=discount,
            arr=compute_arr(cfg, edition, seats, discount),
            contract_start=contract_start,
            renewal_date=next_renewal(contract_start, max(start, contract_start)),
            region=weighted_pick(rng, REGIONS),
            industry=pick(rng, INDUSTRIES),
            account_owner=pick(rng, reps),
            csm=_csm_for(coverage, rng, csms),
            engagement=engagement,
            fit=fit,
            growth=growth,
            docs_need=float(rng.beta(2.0, 2.0)),
            setup_drive=setup_drive,
            assist_affinity=clamp(engagement + rng.normal(0, 0.2), 0.0, 1.0),
            momentum=0.95,  # new accounts start keen; established ones are set just below
            # New customers buy roughly the seats they need, with some room to grow.
            team_size=max(5.0, seats * clamp(0.5 + 0.4 * growth + rng.normal(0, 0.12), 0.3, 1.0)),
        )
        account.contacts = _build_contacts(world, account, rng, fake)
        if established:
            _give_history(world, account, rng)
        world.accounts.append(account)


def _company_name(n: int) -> str:
    suffix = NAME_SUFFIX[n % len(NAME_SUFFIX)]
    n //= len(NAME_SUFFIX)
    return f"{STEM_A[n // len(STEM_B)]}{STEM_B[n % len(STEM_B)]} {suffix}"


def _csm_for(coverage: str, rng, csms: list[str]) -> str | None:
    if coverage == "high_touch":
        return pick(rng, csms)
    if coverage == "pooled":
        return "Scaled CS Pool"
    return None  # uncovered: digital and agentic only


def _build_contacts(world, account: Account, rng, fake) -> list[Contact]:
    """Two to twelve people per account. About 2% of accounts have no admin tagged at all."""
    n_contacts = int(clamp(round(2 + rng.gamma(2.0, 1.5)), 2, 12))
    personas = ["end_user"] if rng.random() < 0.02 else ["admin"]
    if rng.random() < 0.45:
        personas.append("admin")
    if rng.random() < 0.60:
        personas.append("billing")
    if rng.random() < 0.50:
        personas.append("champion")
    personas = (personas + ["end_user"] * n_contacts)[:n_contacts]

    contacts, used_emails, next_user = [], set(), 0
    for persona in personas:
        first, last = fake.first_name(), fake.last_name()
        local = re.sub(r"[^a-z.]", "", f"{first}.{last}".lower())
        email = f"{local}@{account.domain}"
        if email in used_emails:
            email = f"{local}{len(used_emails)}@{account.domain}"
        used_emails.add(email)

        # Admins and champions are product users; so are about half of the end users.
        product_user = None
        if persona in ("admin", "champion") or (persona == "end_user" and rng.random() < 0.5):
            product_user = user_id(account, next_user)
            next_user += 1

        interest = account.engagement * EMAIL_INTEREST[persona] + rng.normal(0, 0.15)
        contacts.append(
            Contact(
                contact_id=world.next_id("C"),
                account_id=account.account_id,
                full_name=f"{first} {last}",
                email=email,
                persona=persona,
                role=pick(rng, ROLES[persona]),
                consent_status=weighted_pick(rng, CONSENT_BY_PERSONA[persona]),
                email_valid=bool(rng.random() < (0.96 if persona == "admin" else 0.94)),
                product_user_id=product_user,
                last_engaged_at=None,
                affinity=clamp(interest, 0.02, 0.98),
                has_left=bool(rng.random() < 0.03),
            )
        )
    return contacts


def _give_history(world, account: Account, rng) -> None:
    """Accounts that signed up before day one already have users, setup and a contract."""
    cfg = world.cfg
    start = world.start_date
    limits = cfg["editions"][account.edition]

    # Momentum sits near the level set by product fit (see behavior.update_momentum).
    account.momentum = clamp(0.35 + 0.75 * account.fit + rng.normal(0, 0.1), 0.1, 1.2)
    drive = account.setup_drive
    if rng.random() < 0.2 + 1.6 * drive:
        account.seats_assigned = min(account.seats_licensed, round(account.team_size))
    else:
        account.seats_assigned = int(rng.integers(1, 5))  # the team never really came on board
    account.n_boards = int(rng.integers(3, 40))
    account.n_rules = min(limits["automation_rules"], int(rng.integers(0, 13) * account.engagement))

    days_since_signup = (start - account.contract_start).days

    def some_day_after_signup() -> date:
        days = int(rng.integers(0, min(60, days_since_signup)))
        return account.contract_start + timedelta(days=days)

    done = {}
    if rng.random() < 0.98:
        done["board_created"] = some_day_after_signup()
    if account.seats_assigned >= 5:
        done["users_invited"] = some_day_after_signup()
    if rng.random() < 0.25 + 0.7 * drive:
        done["integration_connected"] = some_day_after_signup()
        account.n_integrations = min(limits["integrations"], 1 + int(rng.random() < 0.25))
    if rng.random() < 0.10 + 0.7 * drive:
        done["sso_configured"] = some_day_after_signup()
    account.setup_done = done

    # Telemetry from before day one, so the pipeline can see that setup happened.
    admin = user_id(account, 0)
    for index in range(account.seats_assigned):
        role = "admin" if index == 0 else "member"
        world.add_backfill_event(
            account, admin, "user_invited", some_day_after_signup(),
            {"invited_user_id": user_id(account, index), "role": role},
        )  # fmt: skip
    if "board_created" in done:
        world.add_backfill_event(
            account, admin, "board_created", done["board_created"],
            {"board_id": f"{account.account_id}-b0001", "template": "kanban"},
        )  # fmt: skip
    if "integration_connected" in done:
        world.add_backfill_event(
            account, admin, "integration_connected", done["integration_connected"],
            {"integration": "chat"},
        )  # fmt: skip
    if "sso_configured" in done:
        world.add_backfill_event(
            account, admin, "sso_configured", done["sso_configured"], {"protocol": "saml"}
        )

    # Some contacts engaged with earlier emails.
    for contact in account.contacts:
        if rng.random() < contact.affinity:
            days_ago = int(rng.integers(1, 120))
            contact.last_engaged_at = datetime(start.year, start.month, start.day) - timedelta(
                days=days_ago, hours=int(rng.integers(1, 10))
            )

    # The original deal, and a renewal already in flight if it is due within 90 days.
    if account.arr > 0:
        world.add_opportunity(
            account, "new_business", "New business", "closed_won", account.arr,
            created_at=account.contract_start - timedelta(days=int(rng.integers(5, 45))),
            close_date=account.contract_start,
        )  # fmt: skip
        days_to_renewal = (account.renewal_date - start).days
        if days_to_renewal <= 90:
            stage = "negotiation" if days_to_renewal <= 40 and rng.random() < 0.5 else "open"
            account.open_renewal = world.add_opportunity(
                account, "renewal", "Annual renewal", stage, account.arr,
                created_at=account.renewal_date - timedelta(days=90),
                close_date=account.renewal_date,
            )  # fmt: skip
