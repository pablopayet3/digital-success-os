# 0032: In the live demo, a handoff reaches the CRM as it happens

Status: accepted (19 November 2026, the owner's request for the case-study interview).
Synthetic data, fictional company.

## Context

The CRM sync (ADR 0019) sends open tasks to the CRM when someone runs a command. It has
run for real, but nobody watching the demo sees the jump between systems: the handoff
happens on one screen, and the CRM only learns about it later, by hand. For a demonstration
of a motion that spans several systems, the moment a handoff appears in the CRM is the
proof that matters.

## Options

1. **Keep the command.** Honest, and invisible.
2. **Send every handoff to the CRM, always**, from the engine itself. The simulation creates
   dozens of tasks a day, which would flood a developer org and its API limits, and the
   hosted demo would need CRM credentials.
3. **Send only the handoffs a person creates in the live demo, and only when the app is
   started for it**, from a computer that is signed in to the CRM.

## Decision

Option 3.

- `run.py app --crm` sets `DSO_CRM_LIVE=true`. `crm_sync.live_enabled()` is true only then,
  and never on the hosted demo (`DSO_HOSTED`).
- When the Live demo page hands a customer to a person, `crm_sync.send_task_now` sends
  that task at once: the account is created or updated, the task is created on it (never
  twice: the task id in the subject is the key, as in ADR 0019). The page says so, with a
  link to the task in the CRM.
- When a person closes the task in the Human console, `crm_sync.complete_task_now` marks it
  completed in the CRM and adds the outcome to its description. The return signal reaches
  the CRM too.
- A failure is shown on screen in one sentence and never stops the demo.
- The browser sign-in held by the vendor's command-line tool is now tried first when it
  is named, ahead of any password left in `.env`, because it stores no secret in the
  project and newer orgs refuse the password sign-in. On Windows the tool is also looked
  for in the npm folder under APPDATA, which an app's own path may lack.

## Consequences

- The demonstration shows one real jump between systems: a handoff in the app, a task in
  the CRM a few seconds later, completed there when a person closes it.
- It works only from the owner's computer, signed in to the CRM. A rehearsal from a
  launcher with a stripped-down environment failed to reach the sign-in tool; started
  from a normal terminal, it worked (19 November 2026: task created on the account,
  status read back from the CRM).
- Each rehearsal leaves a task in the CRM and rows in the local store (`scenario =
  'live_demo'`). Remove the local rows afterwards, as for screenshots.

## Revised 26 November 2026: the hosted demo, for the presenter only

The owner asked for nothing to run locally on the day: one hosted link for the whole
demonstration. The two reasons above for keeping the hosted demo out of the CRM are kept,
and answered instead of avoided:

- **Credentials on the host.** The hosted app signs in with the CRM's own way for one
  system to reach another (a connected app: consumer key and secret, OAuth client
  credentials, already supported by `connect`). The owner creates it in the org and types
  the values into the host's dashboard. They are never in the repository.
- **A public link.** `live_enabled(presenter)` is true on the host only for a presenter:
  someone who signed in on the Live demo page with the admin password, or to the Human
  console as Admin (`ui.presenter`). A public visitor sees every step on screen and in the
  Human console, and nothing they do reaches the CRM.
- **A cap.** On the host at most `HOSTED_DAILY_CAP` (40) new demo tasks a day reach the CRM
  (`DSO_CRM_DAILY_CAP` overrides it). The count is asked of the CRM itself, so a restart
  cannot reset it. Every task already says it is synthetic data from a fictional company.

To switch it on, the host's app service needs `DSO_CRM_LIVE=true`,
`SALESFORCE_CONSUMER_KEY`, `SALESFORCE_CONSUMER_SECRET` and `SALESFORCE_DOMAIN`.

## Revisit if

The handoffs of the simulation itself should reach the CRM: batch them through the
existing sync, within the org's API limits.
