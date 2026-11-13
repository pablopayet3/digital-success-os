# 0026: The hosted app is kept awake by a scheduled request

Status: accepted (13 November 2026, after the phases). Synthetic data, fictional company.

## Context

The hosted app runs on the host's free plan. The host stops a free service after 15
minutes without a visitor and starts it again on the next request. That start takes about
a minute: on 13 November 2026 the first request after a quiet period took 72 seconds.

The first person to open the link is usually a reviewer who has just been sent it. A
blank page for a minute reads as a broken link, and the README's warning ("the first load
can take a minute") is read after the wait, if it is read at all.

Two limits apply. The cost rules allow free tiers only. And the host gives one workspace
750 running hours a month, shared by the app and the API: when they are used up, it
suspends every free service until the next month. A sleeping service uses no hours.

## Options

1. **Leave it and warn the reader.** What the README did until now. No cost, and a poor
   first impression.
2. **A paid instance that never sleeps.** Against the cost rules.
3. **A request every few minutes, all day and all night.** The app alone would then run
   744 hours in a 31-day month. With the API's hours added, the allowance runs out before
   the month ends and the host suspends both services.
4. **A request every few minutes during the hours a reviewer is likely to open the
   link**, sent by a GitHub Actions schedule. Sixteen hours a day is 496 hours in the
   longest month.
5. **An outside monitoring service that requests the page.** The same effect, with one
   more account to create and to explain.

## Decision

Option 4: `.github/workflows/keep-awake.yml`.

- **When.** Every five minutes from 06:00 to 22:00 US Eastern Standard Time, every day.
  The schedule is written in UTC (11:00 to 03:00), so in summer it runs from 07:00 to
  23:00 on the clock.
- **What.** One request for the app's front page, the address a visitor opens. The host
  counts any request from outside as a visit.
- **Only the app.** Nobody opens the API first, and its share of the hours is needed.
- **Five minutes apart.** GitHub says a scheduled run can start late, or be dropped when
  it is busy, most often at the start of an hour. With five minutes between requests, one
  missed request still leaves the next inside the host's 15 minutes. The schedule also
  avoids minute 0.
- **Three minutes to answer.** If the app was asleep, the request itself wakes it up, so
  the next visitor does not wait.
- **A bad answer is a warning, not a failed run.** A failed scheduled run sends an email,
  and twelve an hour would be noise while the host is having trouble. This workflow keeps
  the app awake. It is not the monitor.
- **A test guards the allowance.** `tests/test_keep_awake.py` fails if the schedule would
  run the app more than 550 hours in a 31-day month (which leaves 200 for the API and for
  visits at other hours), or if two requests in a row would not fit in the host's 15
  minutes.

## Consequences

- A visitor between 06:00 and 22:00 Eastern finds the app running. At other hours the
  first page still takes about a minute. The README and the reviewer guide say so.
- It narrows the wait; it does not remove it for certain. If GitHub starts several runs
  late in a row, the app can sleep for a few minutes until the late request wakes it.
- About 190 very short runs a day. GitHub does not charge for them in a public repository.
- GitHub turns scheduled workflows off after 60 days without activity in a public
  repository. The app then goes back to sleeping until the workflow is enabled again in
  the Actions tab.
- To stop it: the Actions tab, "Keep the hosted app awake", "Disable workflow".

## Revisit if

- Nobody is reviewing the demo any more: disable the workflow.
- Reviewers are in other time zones: change the hour field of the one cron line. The test
  says how many hours fit.
- The same workspace hosts another free service: the 750 hours are shared with it.
