# Five-minute demo script

**Show:** a requirement that quietly went stale, caught by the tool - and an AI
check that a requirement's individual criteria really have tests.
**Use:** the demo Jira project KAN on `pwtrace.atlassian.net`, Traceability tab.

## Before you start (5 minutes, do not skip)

- [ ] **Warm it up:** open the Traceability tab and click through all three tabs
      once. The first load after idle can take ~18 seconds.
- [ ] Coverage shows **KAN-4 as covered** (not suspect). If it is suspect, click
      Mark reviewed first.
- [ ] Open **KAN-4 in a second browser tab**, ready to edit the description.
- [ ] Know the slow part: **Analyze gaps takes about 20 seconds** (a real AI
      call). Start it early and talk while it runs.
- [ ] Afterwards: remove your edit from KAN-4's description and click Mark reviewed.

## The story (say this)

> "Teams write tests for a requirement, then the requirement changes and
> nobody notices the tests no longer match. Every tool tells you *a* test is
> linked. This tells you whether it's still the *right* test."

## Steps

**1. Test Inventory (30 s)**
Show the table: real test titles, pass/fail, the trend dots, a flaky badge, and
Jira keys as links. *"These come from the Playwright run itself, so it works
however the tests were written."*

**2. Requirement Coverage (45 s)**
Show 13 requirements: 10 covered, 3 uncovered (Task 1, Task 2, a scratch issue).
*"Everything red has no test at all. That's the question auditors ask."*

**3. The stale requirement (90 s) - the main moment**
Switch to the KAN-4 tab. Edit one word in the description and save (for example,
add a clause to the user-story sentence). Return to Coverage, reload, and wait
up to a minute. KAN-4 flips to **suspect**. Click KAN-4, then **Show 1 link**:
read the plain-language note about what changed.
*"No webhook, no script - Jira told us. It stays suspect until a person looks.
That's on purpose: it never clears itself."*
Click **Mark reviewed**: it returns to covered with a review timestamp.

**4. Gap analysis (60 s)**
With KAN-4 selected, click **Analyze gaps** and talk while it runs. Read one
result: each acceptance criterion is judged separately, with the specific
assertion that covers it - and the reasoning notes where a test only partly
proves a criterion.
*"Not 'a test is linked' - 'this criterion is covered by this assertion'."*

**5. Close (30 s)**
Show the Settings tab: *"Your CI uploads results with one key generated here;
that's the whole setup. No Jira credentials to give us."* Then stop and ask them
how this compares to how they do it today (see the interview guide).

## Say this if asked

| Question | Honest answer |
|---|---|
| Is it on the Marketplace? | Not yet. It runs as a development install; listing depends on feedback like theirs. |
| Which tests? | Playwright. Hand-written, generated and BDD (.feature) tests; no-code layers on top of Playwright are not supported. |
| Does it write to Jira? | No. It only reads, and only what the app is given access to. |
| Where does AI run, and what does it see? | Requirement text and test titles/assertions go to Anthropic's API for the change note and the gap check. Everything else is plain code. |
| Multi-customer? | Each Jira install's data is isolated, proven by tests; there is one live install so far. |
| Can it handle our criteria format? | Today it reads a heading plus bullet list in the description. Ask to see theirs. |

## Know the limits

- Gap analysis is slow (~20 s) and could time out on a large ticket (#50).
- The first load after idle can be slow; keep it warm before a demo.
- Do not demo a second customer or the Marketplace flow - neither exists yet.
