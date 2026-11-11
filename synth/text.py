"""Wording for support tickets, NPS comments and mailbox replies.

Synthetic data, fictional company. Everything here is built from templates plus
noise (typos, signatures, quoted threads, mixed intent). No LLM is called, so
the generator is free, repeatable and works offline (see docs/decisions/0008).
"""

from __future__ import annotations

from synth.util import pick

SUCCESS_MAILBOX = "success@lumenlabs.example"

# --- Support tickets ---------------------------------------------------------------------

# category -> list of (subject, problem description)
TICKET_PROBLEMS = {
    "setup_sso": [
        ("SSO connection test fails", "We are trying to set up single sign-on and the connection test fails at the last step with a certificate error."),
        ("Where do I upload SSO metadata?", "Our IT team wants to turn on SSO but we cannot find where to upload the identity provider metadata file."),
        ("Users locked out after enabling SSO", "We switched on SSO this morning and now several people cannot log in at all."),
    ],
    "user_management": [
        ("Invites not arriving", "I invited six colleagues yesterday and none of them received the invitation email."),
        ("How do I bulk invite users?", "We need to add around 30 people. Is there a way to invite them in bulk instead of one by one?"),
        ("Cannot remove a former employee", "Someone left our company and I cannot find how to deactivate their seat."),
    ],
    "integrations": [
        ("Chat integration keeps disconnecting", "The chat integration disconnects every few days and we have to authorise it again."),
        ("Calendar sync not working", "Due dates from Relay Boards are not showing up in our calendar after we connected it."),
        ("Is there an integration for our code repository?", "We would like commits to show on cards. I could not find the setup guide."),
    ],
    "automation": [
        ("Automation rule did not fire", "We created a rule to move cards when they are approved, but it has not run once."),
        ("Hit the automation rule limit", "We tried to add a new rule and got a message saying we reached the limit for our plan."),
        ("Rule runs twice", "One of our automation rules sends two notifications for every card. How do we stop the duplicate?"),
    ],
    "billing": [
        ("Charged for seats we do not use", "Our last invoice shows more seats than we have people. Can you explain the charge?"),
        ("Need a copy of our invoice", "Finance is asking for last month's invoice and I cannot find it in the admin settings."),
        ("Question about renewal", "Our renewal is coming up and we want to understand our options before it goes through."),
    ],
    "performance": [
        ("Boards are very slow to load", "Since last week our larger boards take more than ten seconds to load."),
        ("Search times out", "Searching across Relay Docs often times out for our team in the afternoon."),
    ],
    "bug": [
        ("Cards disappearing from board", "Two cards vanished from our sprint board. They are not in the archive either."),
        ("Docs editor loses formatting", "When we paste a table into Relay Docs the formatting is lost every time."),
        ("Notifications sent to the wrong person", "A colleague is getting notifications for cards assigned to someone else."),
    ],
    "how_to": [
        ("How to set up a board template", "We want every new project to start from the same board layout. What is the best way to do this?"),
        ("Permissions for guests", "Can we give an external contractor access to one board only?"),
        ("Export a board", "Is it possible to export a board to a spreadsheet for a monthly report?"),
    ],
    "assist_credits": [
        ("Relay Assist credits ran out", "We ran out of Relay Assist credits in the middle of the month. How do we get more?"),
        ("How are Assist credits counted?", "I am trying to understand how many credits a summary uses so I can plan our usage."),
    ],
}  # fmt: skip

CALM_OPENERS = ["Hi team,", "Hello,", "Hi,", "Good morning,"]
ANGRY_OPENERS = [
    "This is the third time I am writing about this.",
    "I am honestly fed up.",
    "We are paying for this product and it does not work.",
    "Not happy at all.",
]
CALM_CLOSERS = [
    "Thanks in advance.",
    "Could you point me in the right direction?",
    "Any help appreciated.",
    "Thank you.",
]
ANGRY_CLOSERS = [
    "If this is not fixed this week we will look at alternatives.",
    "I need someone to call me today.",
    "This is blocking the whole team.",
    "Frankly we are considering cancelling.",
]


def make_ticket(rng, category: str, angry: bool, first_name: str) -> tuple[str, str]:
    """Return (subject, body) for a support ticket."""
    subject, problem = pick(rng, TICKET_PROBLEMS[category])
    opener = pick(rng, ANGRY_OPENERS if angry else CALM_OPENERS)
    closer = pick(rng, ANGRY_CLOSERS if angry else CALM_CLOSERS)
    body = f"{opener} {problem} {closer}\n\n{first_name}"
    if angry and rng.random() < 0.4:
        subject = subject.upper()
    return subject, body


# --- NPS comments ------------------------------------------------------------------------

NPS_COMMENTS = {
    "promoter": [
        "Relay Boards has become the place where our team plans everything. Setup was quick.",
        "Love the automation rules, they save us hours every week.",
        "Great product and the docs are clear. Would recommend.",
        "Relay Assist summaries are surprisingly good. The team uses them daily.",
        "Easy to roll out to the whole company. Support answered fast when we needed them.",
        "Simple, fast, does what we need.",
    ],
    "passive": [
        "It works fine for us but we only use the basics.",
        "Good tool. Setting up SSO took longer than expected.",
        "Decent, although the integrations could be easier to configure.",
        "Does the job. Pricing for extra seats feels a bit high.",
        "We like Boards. Have not had time to try the rest.",
        "Okay overall. Search could be better.",
    ],
    "detractor": [
        "We never managed to get the team onto it. Too much setup and nobody helped us.",
        "Performance has been poor for weeks and support has not fixed it.",
        "We are paying for seats we do not use. Considering alternatives.",
        "Could not get SSO working, so half the team gave up.",
        "The automation limit on our plan makes it hard to justify.",
        "Honestly disappointed. We open tickets and wait days for an answer.",
        "Too complicated for a small team like ours.",
    ],
}


def make_nps_comment(rng, score: int) -> str:
    """About two in three respondents leave a comment."""
    if rng.random() < 0.35:
        return ""
    band = "promoter" if score >= 9 else "passive" if score >= 7 else "detractor"
    return pick(rng, NPS_COMMENTS[band])


# --- Mailbox replies ---------------------------------------------------------------------

# intent -> list of (body, sentiment, second intent mixed in or None, hard to classify?)
REPLIES = {
    "out_of_office": [
        ("Thank you for your email. I am out of the office until {return_day} with limited access to email. For anything urgent please contact {colleague}.", "neutral", None, False),
        ("I am on annual leave and will reply when I am back on {return_day}.", "neutral", None, False),
        ("I am currently travelling and will respond as soon as I can.", "neutral", None, False),
        ("Bonjour, je suis absent du bureau jusqu'au {return_day}. Je répondrai à votre message à mon retour.", "neutral", None, True),
        ("Ich bin bis {return_day} nicht im Büro und habe keinen Zugriff auf meine E-Mails.", "neutral", None, True),
        ("I am out until {return_day}. If this is about scheduling the review meeting, please book time with {colleague}.", "neutral", "meeting_request", True),
    ],
    "unsubscribe": [
        ("Please remove me from this mailing list.", "neutral", None, False),
        ("Unsubscribe", "neutral", None, False),
        ("stop sending me these", "negative", None, False),
        ("I do not need these emails anymore, please take me off the list. Thanks.", "neutral", None, False),
        ("Not relevant to my role, I work in finance. Can you stop these? {colleague} is the right person.", "neutral", None, True),
        ("Please take me off this list. Also, the last update broke our board filters and nobody has replied to my ticket.", "negative", "complaint", True),
    ],
    "left_company": [
        ("{name} no longer works at {company}. Please contact {colleague} instead.", "neutral", None, False),
        ("This mailbox is no longer monitored. {name} has left {company}.", "neutral", None, False),
        ("Delivery has failed: the recipient's mailbox is disabled.", "neutral", None, False),
        ("I have left {company} as of last month. For Relay questions please reach out to {colleague}.", "neutral", None, False),
        ("Hi, {first} moved on last month and I have picked up this inbox. I am not sure who looks after Relay for us now. What do you need?", "neutral", None, True),
    ],
    "product_question": [
        ("Thanks for this. How do we connect our calendar so due dates show up there?", "neutral", None, False),
        ("Quick question: can guests be limited to a single board?", "neutral", None, False),
        ("Is there a way to bulk invite users? We have about {n} people to add.", "neutral", None, False),
        ("Where do I find the SSO settings? Our IT team is asking.", "neutral", None, False),
        ("Does Relay Assist work on Docs pages as well as boards?", "neutral", None, False),
        ("How do automation rules work with recurring cards?", "neutral", None, False),
        ("Is SSO included in our plan or do we need Premium for that?", "neutral", "buying_intent", True),
        ("we tried the thing you mention in step 2 and nothing happens?? is that normal", "negative", None, True),
    ],
    "buying_intent": [
        ("We need {n} more seats for a new team starting next month. What is the process?", "positive", None, False),
        ("Can you send pricing for Premium? We are hitting the automation rule limit.", "neutral", None, False),
        ("We would like to add Relay Docs for the whole company. Who do I talk to?", "positive", None, False),
        ("What would it cost to move from Standard to Premium for {n} users?", "neutral", None, False),
        ("Our Assist credits keep running out. Is there a bigger package?", "neutral", None, False),
        ("Quick question, what happens if we go over our seat count? We are onboarding about {n} people in the next few weeks.", "neutral", "product_question", True),
        ("Before our renewal I would like to understand what Enterprise would give us compared with what we have.", "neutral", None, True),
    ],
    "complaint": [
        ("This is the third email I get about features while our boards have been slow for two weeks. Fix that first.", "negative", None, False),
        ("We have had an open ticket for ten days and no answer. This is not acceptable.", "negative", None, False),
        ("Honestly we are thinking of cancelling. The team finds it confusing and nobody has helped us get set up.", "negative", None, False),
        ("Your automation rules keep failing and we lost a day of work because of it.", "negative", None, False),
        ("Thanks for the update. To be honest we have stopped using automation because it kept failing, so this is not much use to us right now.", "negative", None, True),
        ("We are paying for {n} seats and barely half are used because setup was so painful. I want to talk to someone about reducing our plan.", "negative", "meeting_request", True),
    ],
    "meeting_request": [
        ("Could we set up a 30 minute call next week to go through this?", "neutral", None, False),
        ("Can someone walk our admins through the setup? Thursday afternoon works for us.", "neutral", None, False),
        ("I would like to book a session with someone from your team. What times do you have?", "positive", None, False),
        ("Happy to chat. Do you have a calendar link?", "positive", None, False),
        ("Is there someone I can talk to about how other companies our size use this?", "neutral", None, True),
    ],
}  # fmt: skip

AUTOMATIC = {"out_of_office", "left_company"}  # sent by a machine: no greeting, typos or signature
GREETINGS = ["Hi,", "Hello team,", "Hey,", "Hi there,"]
RETURN_DAYS = ["Monday", "the 14th", "next week", "the 2nd", "Thursday"]


def make_reply(rng, intent: str, ctx: dict) -> dict:
    """Build one inbound reply to a journey email.

    `ctx` carries the names to fill in: name, first, company, role, colleague, subject.
    Returns the subject and body, plus the answer key for the classifier evaluation.
    """
    template, sentiment, second_intent, hard = pick(rng, REPLIES[intent])
    body = template.format(
        n=int(rng.integers(5, 41)), return_day=pick(rng, RETURN_DAYS), **ctx
    )

    if intent in AUTOMATIC and not hard:
        prefix = "Automatic reply: " if intent == "out_of_office" else "Undeliverable: "
        subject = prefix + ctx["subject"]
    else:
        subject = "Re: " + ctx["subject"]
        if rng.random() < 0.5:
            body = f"{pick(rng, GREETINGS)}\n\n{body}"
        if rng.random() < 0.15:
            body = _add_typos(rng, body)
        if rng.random() < 0.10:
            body = body.lower()
        body += _signature(rng, ctx)
        if rng.random() < 0.3:
            body += _quoted_original(ctx)
    return {
        "subject": subject,
        "body": body,
        "intent": intent,
        "sentiment": sentiment,
        "secondary_intent": second_intent,
        "is_hard": hard,
    }


def _add_typos(rng, text: str) -> str:
    """Swap two neighbouring letters in up to two words."""
    words = text.split(" ")
    for _ in range(2):
        i = int(rng.integers(len(words)))
        word = words[i]
        if len(word) > 4 and word.isalpha():
            j = int(rng.integers(1, len(word) - 2))
            words[i] = word[:j] + word[j + 1] + word[j] + word[j + 2 :]
    return " ".join(words)


def _signature(rng, ctx: dict) -> str:
    roll = rng.random()
    if roll < 0.35:
        return f"\n\nThanks,\n{ctx['first']}"
    if roll < 0.60:
        return f"\n\n--\n{ctx['name']}\n{ctx['role']} | {ctx['company']}"
    if roll < 0.75:
        return "\n\nSent from my phone"
    return ""


def _quoted_original(ctx: dict) -> str:
    return (
        f"\n\nOn {ctx['sent_day']}, Lumen Labs Success <{SUCCESS_MAILBOX}> wrote:"
        f"\n> {ctx['subject']}\n> Hi {ctx['first']}, here is the latest from the Relay team..."
    )
