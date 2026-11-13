# Try it yourself: the whole loop in five minutes

Synthetic data, fictional company. "Lumen Labs" and its product "Relay" do not exist.
This page is for someone who was given the link and wants to test the system by hand,
not watch a demo of it.

**The app:** https://digital-success-os-app.onrender.com
(free hosting: the first page can take a minute to wake up)

**Sign-in details** for the Human console are sent to you separately. There is one
password per role: CSM, Sales and Admin. They are never written in this repository.

When you open the app, a guided tour starts: thirteen short windows. The second draws
the whole chain with the team on each step. The others explain each page: the tool at a
real company, who uses it, what this demo is built with, and what the role does there.
It takes six minutes, and you can close it at any point. The button "Guided tour" in
the sidebar starts it again.

Everything below can be done on the hosted app. Nothing you do there can break
anything: it is a shared demo, and an admin can reset it.

## 1. Make the system hand you a task (2 minutes)

1. Open **Live demo**. The blue box shows a signal firing on a real account in the data,
   the play that signal triggers, and whether this account is treated or held out.
2. Press **Run the story**. The account's admin asks how to invite the team; the agent
   answers from the help centre. Then the admin asks what ten more seats would cost.
3. The agent does not answer that. A rule written in code hands it to Sales before any
   model is asked, and a task is created. Note its number (for example `CTA-00087`).

The line at the top of every page says who answers as the agent. With a key in the
host's settings it is the real model, within a small budget. Without one, the replies
come from a labelled stand-in (keyword rules), so
that the public demo needs no key and costs nothing. The real model's answers to the same
story are in the recording at the top of the README, and the real model's evaluation is
on the Agents page.

## 2. Pick the task up as the person it was sent to (2 minutes)

1. Open **Human console**. Choose the role **Sales** and enter its password.
2. Open your task. This is the handoff packet: why it is on your desk, the customer's own
   words, what the agent already did, the account at a glance, a recommended next step.
3. Under **Close the task**, choose `expansion_opportunity` and press **Resolve**. The
   outcome is the return signal: it tells the journey what to do next.

## 3. See that the system remembers (1 minute)

Open **Accounts**, find the account from step 1, and scroll to "What the system did, and
why". Your task and its outcome are there, next to every play, every touch and every
decision about the account, including the times it was deliberately left alone. The
conversation itself is at the top of the list on the **Agents** page, with the tools the
agent called and what it looked up.

## Things worth trying to break

On the Live demo page, press **Start over** and type your own message.

| Try this | What should happen |
|---|---|
| `I want a refund` | Handed to a person: money questions never reach a model |
| `What does the Premium edition cost?` | Handed to Sales, not to the support queue |
| `Can I talk to someone?` | Handed to a person at once, marked high priority |
| `This is useless. Nothing works and I am sick of it!` | Frustration is detected and a person takes over |
| Sign in to the console as **CSM** instead of Sales | Different queues: each role sees only the work it owns |
| Close a task as `agent_should_have_handled` | It lands in the review queue (Agents page) as a draft test case for the agent |

## Where to look next

| Page | The question it answers |
|---|---|
| Plays and experiments | Did each play move its metric, against accounts deliberately held out? |
| Pilot | Is the pilot ready, answered from live data? What would adding the next segment do? |
| Data quality | What did the pipeline reject, and do the tests and the data contract pass? |
| Agents | How did the real model score on 44 fixed cases, across three prompt versions? |
| Operating model | Who owns what, how changes are made, and why each design decision was taken |

## The API

Open https://digital-success-os-api.onrender.com/docs. Reading needs nothing: try
`GET /export/crm` and `GET /export/cs-platform`. Writing (an event, a mailbox reply, a
task outcome) needs a token, sent with the sign-in details if you asked for it.

## If you are the admin

Sign in to the Human console as **Admin**. "Reset the demo data" removes everything
visitors created or closed and restores the starting state. Use it before handing the
link to the next person.

## To run all of it on your own machine

The README has the three commands. Locally the agent's replies are the real model's,
replayed from stored responses, with no key and no network.
