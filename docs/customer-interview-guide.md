# Customer interview guide (issue #47)

**Goal:** decide whether to spend time on the Marketplace listing and review
(#37-#39), by learning if QA leads would pay for this and what must change
first. This is research, not a sales call.

**Who:** 3-5 QA leads, test managers or heads of QA who use Jira and have
Playwright (or are moving to it). **At least one in a regulated field** (medical
devices, fintech, automotive, aerospace) where traceability is audited - that is
where it is a must-have rather than a nice-to-have. 30 minutes each.

## Ground rules

- **Don't pitch first.** Spend the first 15 minutes on their world. Demo only
  at the end, and only if they ask or you have a specific question it answers.
- **Ask about the past, not the future.** "Walk me through the last time..."
  beats "Would you use...?". People say yes to hypotheticals.
- **Listen for money and pain**, not compliments. Silence after a question is
  fine; don't fill it with options.
- **Take notes in their words.** Quote them; don't summarise yet.
- Ask permission to take notes, and don't record the screen or share their
  ticket contents anywhere.

## Questions (about 25 minutes)

**1. Their setup (3 min)**
- What do you use for Jira and for tests? How big is the team and the suite?
- Playwright today, or planned? Anything else (Cypress, Selenium, manual)?

**2. How they trace requirements to tests today (8 min) - the core**
- Walk me through the last time someone asked "is this requirement tested?"
  Who asked, how long did it take, where did the answer come from?
- What tool or spreadsheet holds the links? Who keeps it up to date, and how
  often is it wrong?
- Tell me about the last time a requirement changed *after* tests were written.
  How did the team find out the tests might be stale? (Or did they not?)
- Is there an audit, a certification or a customer who requires proof of
  coverage? How often, and what happens if it is missing?

**3. What they have tried (4 min)**
- Do you use Xray, Zephyr, AIO Tests, TestRail or something else for this?
  What do you like? What makes you want to avoid it?
- What does it cost you today, in licences and in people's time?

**4. Their tickets (4 min)** - tests whether our parsing and AI check apply
- How do you write acceptance criteria? Bullets in the description, a custom
  field, Gherkin, something else? (Ask to see one - with sensitive details
  hidden.)
- How consistent is that across teams and across the last year?

**5. Value and price (4 min)**
- If something told you "this requirement's tests may no longer match it", what
  would you do with that? Who would act on it?
- Where would you want to see it: a project page, on the Jira ticket itself,
  a Slack message, a report for auditors?
- What would have to be true for you to put this in front of your team? What
  would make you say no right away? (Security review? Data leaving Jira?
  Needing an AI vendor approved?)
- Roughly what do you pay per user per month for the tools around this?
  Where does a price become "I'd have to ask finance"?

**6. Close (2 min)**
- Who else should I talk to? Can I come back with something to look at?

## After each call (10 minutes, same day)

Fill in one row per call; compare across calls only after all of them.

| | |
|---|---|
| Role / industry / team and suite size | |
| Regulated? Audit pressure? | |
| How they trace today (tool, owner, how stale) | |
| Last time a requirement changed under tests | |
| How they write acceptance criteria | |
| Tools tried / paying for, and the complaints | |
| Where they would want the result to appear | |
| Blockers named (security, AI, price, process) | |
| Price signals (their numbers, not yours) | |
| Strongest quote | |
| Would they try it? (yes / maybe / no) and why | |

## What would change the plan

| If you hear this... | ...then |
|---|---|
| Most say "we do this in a spreadsheet and it's always wrong" | Strong fit: keep going; price on pain |
| Regulated teams care, others shrug | Target regulated teams first; shape the listing around audits |
| Acceptance criteria live in custom fields / Gherkin, not the description | Fix the parser before anything else |
| They want it on the ticket, not a project page | Build the issue panel (#45) first |
| "AI vendor / data leaving Jira" is a hard no | Plan a no-AI mode and a data-handling page before the security review |
| Nobody pays beyond what they already do | Revisit free vs paid (#35); consider a free tier that earns installs |
| Fewer than 2 of 5 would try it | Pause Marketplace work (#37-#39); revisit positioning |

Record the outcome and decisions as a comment on #47.
