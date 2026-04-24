---
name: finding-wedge-problems
description: >
  Converts vague startup ideas, technology-first concepts, trend-driven hunches,
  and copycat product ideas into concrete, painful, testable wedge problems.
  Use when a founder has an interesting idea but lacks a clear customer problem,
  when a solution feels elegant but hollow, or when they need to diagnose customer
  friction, bottlenecks, risky assumptions, and the right MVP experiment.
---

# Skill: Finding Wedge Problems

## Purpose

This skill turns vague business ideas into concrete, testable startup problems.

Use it when the user starts from:

- An interesting technology
- A product they want to copy
- A trend that appears popular
- A vague market opportunity
- A polished idea that lacks a clear customer pain

The goal is not to make the idea sound better. The goal is to expose whether there is a real, urgent, specific problem underneath it.

Core principle:

> A startup does not begin when an idea sounds clever. It begins when a specific customer has a painful repeated friction, a costly workaround, and a testable reason to change behavior.

---

## When to Use

Use this skill when the user says things like:

- "I have a startup idea, but I’m not sure what problem it solves."
- "This technology seems interesting. Can this become a business?"
- "People seem to like X. I want to make something similar."
- "I think there is a market here, but I can’t structure it."
- "What problem does this product actually solve?"
- "How do I find the wedge problem?"
- "What MVP should I make?"
- "I don’t want to build a hollow product."

Do not jump directly to features, branding, or business model design. First diagnose the problem structure.

---

## Operating Stance

Be skeptical but constructive.

Assume the initial idea may be a solution looking for a problem. Do not shame the user for that. Instead, help them convert the hunch into a problem-discovery process.

Avoid saying:

- "This is a great idea."
- "You should build this."
- "People will love this."
- "Just make an MVP."

Prefer asking:

- "What exact decision does this improve?"
- "Who loses time, money, status, or certainty because this is unsolved?"
- "What workaround proves they already care?"
- "What is the smallest behavioral signal that would validate this?"
- "Which assumption, if false, kills the whole idea?"

---

# Workflow

## Phase 0: Detect the Starting Bias

Classify the user’s starting point.

### A. Technology-first

The user starts from a capability.

Examples:

- "AI can score taste."
- "LLMs can generate reports."
- "Computer vision can classify outfits."

Risk: The product becomes impressive but unnecessary.

Diagnostic question:

> Who currently has a painful decision that this technology would make cheaper, faster, or more reliable?

### B. Copycat-first

The user starts from another product’s popularity.

Examples:

- "SBTI is popular. I can make a similar test."
- "This app is making money. I can clone it."

Risk: They copy the surface, not the solved problem.

Diagnostic question:

> What job did the original product actually do for the user: utility, identity, entertainment, status, conversation, relief, or decision support?

### C. Trend-first

The user starts from a market wave.

Examples:

- "AI agents are hot."
- "Food tech is growing."
- "Personality tests are viral."

Risk: The market is real, but their wedge is not.

Diagnostic question:

> Where inside this trend is there repeated friction, current spending, or urgent dissatisfaction?

### D. Pain-first

The user already has a real customer pain. This is the strongest starting point.

Diagnostic question:

> Is the pain frequent, intense, currently worked around, and tied to money or behavior?

Output:

```text
Starting Bias:
- Type:
- Risk:
- What must be proven next:
```

---

## Phase 1: Convert the Idea into Problem Candidates

Generate 5-10 possible customer problems hidden under the idea.

For each candidate, fill this structure:

```text
Problem Candidate:
- Customer:
- Situation:
- Current behavior:
- Friction:
- Loss:
- Existing workaround:
- Why now:
- Evidence we have:
- Evidence missing:
```

Rules:

- Customer must be specific. Bad: "restaurants". Better: "small delivery-only restaurant owners launching new menu items".
- Situation must be concrete. Bad: "when they need insights". Better: "when they choose which menu candidate to test before spending on photos, ingredients, and ads".
- Loss must be explicit: time, money, failed launch, review damage, churn, uncertainty, labor, reputation.

---

## Phase 2: Look for Friction Signals

When interviewing users or analyzing a market, look for these phrases and behaviors.

### Strong friction phrases

- "We just do it by feel."
- "You only know after trying."
- "That person is the only one who knows."
- "We use Excel for that."
- "We copy-paste it manually."
- "We ask around."
- "It depends on the manager."
- "We launch and see what happens."
- "We don’t really know why it failed."
- "Everyone hates it, but that’s just how it works."
- "It takes forever."
- "We pay someone to do that."
- "We tried tools but went back to manual."

### Workaround signals

- Manual spreadsheets
- Screenshots
- Group chats
- Repeated meetings
- Human review panels
- Consultants
- Founder/manager approval bottlenecks
- Gut-feel decisions
- Repeated failed attempts
- Shadow systems outside official tools

Output:

```text
Observed Friction Signals:
1.
2.
3.

Existing Workarounds:
1.
2.
3.

Implication:
- This suggests the real problem may be:
```

---

## Phase 3: Classify the Bottleneck

Map each problem candidate to one or more bottleneck types.

### 1. Judgment Bottleneck

A decision must be made, but the criteria are unclear.

Signals: gut-feel decisions, long debates, no shared scoring system, inconsistent decision-makers.

Example: A food brand cannot decide which recipe variation should reach consumer testing.

### 2. Manual Labor Bottleneck

Humans repeat low-leverage work.

Signals: copy-paste, manual tagging, review reading, spreadsheet consolidation.

Example: A founder manually reads hundreds of reviews to find why customers are dissatisfied.

### 3. Information Fragmentation Bottleneck

Useful information exists but is scattered.

Signals: data across apps, context lost between teams, no single view, decisions made without available evidence.

Example: Sales data, reviews, TikTok comments, and customer support complaints are never connected.

### 4. Expectation-Reality Mismatch Bottleneck

Users expect one thing and experience another.

Signals: "Not what I expected", bad reviews despite technically good product, misleading names/images/claims/positioning.

Example: A menu item gets bad reviews not because it tastes bad, but because the description creates the wrong expectation.

### 5. Quality Consistency Bottleneck

Output varies too much by person, location, time, or context.

Signals: branch inconsistency, staff-dependent quality, hard-to-train judgment, no standard operating criteria.

Example: A franchise cannot keep flavor perception consistent across locations.

### 6. Learning Bottleneck

Failures happen, but the team cannot identify why.

Signals: mixed variables, no postmortem, "we don’t know why it didn’t work", same mistake repeated.

Example: A new product launch fails, but the team cannot separate price, packaging, taste, channel, and targeting effects.

### 7. Scaling Bottleneck

A process works only because one skilled person is involved.

Signals: founder must approve, expert taste-maker required, cannot train juniors, breaks when volume increases.

Example: Only the founder knows whether a new content idea matches the brand.

### 8. Validation Delay Bottleneck

The team learns too late whether a decision was good.

Signals: "we only know after launch", expensive testing, slow feedback loop, high cost of wrong bets.

Example: A restaurant only discovers menu failure after buying ingredients, shooting photos, and running ads.

Output:

```text
Bottleneck Map:
- Candidate problem:
- Bottleneck type(s):
- Why this bottleneck matters:
- What the bottleneck blocks:
- What improves if removed:
```

---

## Phase 4: Identify the Wedge Problem

A wedge problem is the smallest painful problem that can open the door to a larger market.

Score each candidate 1-5.

| Dimension | Question | Score |
|---|---|---|
| Frequency | How often does this happen? | 1-5 |
| Intensity | How painful is it when it happens? | 1-5 |
| Current workaround | Are they already spending time, money, or effort? | 1-5 |
| Buyer clarity | Is the buyer/user identifiable? | 1-5 |
| Testability | Can we test behavior within 7-14 days? | 1-5 |
| Founder access | Can the founder reach these people? | 1-5 |
| Expansion path | If solved, does it lead to adjacent problems? | 1-5 |

Decision rule:

- 26-35: strong wedge candidate
- 20-25: test if access is easy
- 14-19: weak; needs sharpening
- Under 14: probably not a wedge

Output:

```text
Ranked Wedge Candidates:
1. [Problem] — Score:
2. [Problem] — Score:
3. [Problem] — Score:

Recommended Wedge:
- Customer:
- Situation:
- Pain:
- Workaround:
- Why this is the first wedge:
```

---

## Phase 5: Extract the Riskiest Assumptions

For the selected wedge, list assumptions in four categories.

### Desirability

Do they want this?

Examples: users feel this problem strongly, recognize it without education, and will change behavior for a better solution.

### Viability

Can this become a business?

Examples: the buyer has budget, the problem happens often enough, and the value is worth more than the cost of delivery.

### Feasibility

Can we deliver it?

Examples: the required data is obtainable, the output can be useful without full automation, and the solution can be delivered manually at first.

### Distribution

Can we reach them?

Examples: the founder has access to the target customer, the audience exists in reachable communities, and the sales cycle is not too long for the stage.

Output:

```text
Assumption Map:
| Assumption | Category | Importance | Confidence | Evidence | Test |
```

Then choose the #1 riskiest assumption:

```text
Riskiest Assumption:
If this is false, the idea dies because:
```

---

## Phase 6: Choose the Right MVP Type

Do not default to building software. Choose the MVP based on the riskiest assumption.

### If testing interest

Use: landing page, waitlist, fake door, smoke test ad, community post.

Metrics: click rate, email signup, DM requests, waitlist conversion, reply quality.

### If testing willingness to pay

Use: paid pre-order, payment button, paid pilot offer, manual paid report.

Metrics: payment attempt, actual payment, budget discussion, repeat purchase, referral.

### If testing solution usefulness

Use: concierge MVP, manual service, PDF/report MVP, Wizard of Oz MVP.

Metrics: does the user use the output, does it change a decision, do they ask for another one, do they share it internally, would they be upset if it disappeared.

### If testing workflow

Use: clickable prototype, no-code prototype, one-feature MVP, chatbot demo.

Metrics: completion rate, drop-off, time to value, repeat usage, confusion points.

### If testing channel

Use: content MVP, newsletter, community thread, small ad campaign, direct outreach.

Metrics: response rate, comment quality, conversion by message, qualified leads.

Output:

```text
MVP Selection:
- Riskiest assumption:
- MVP type:
- Why this MVP:
- What it will prove:
- What it will not prove:
```

---

## Phase 7: Design the Experiment

Every MVP must have a pass/fail threshold.

Template:

```text
Experiment:
- Hypothesis:
  We believe [customer] will [behavior] because [reason].

- Target:
  [Specific customer segment]

- Artifact:
  [Landing page / manual report / prototype / offer / interview script]

- Acquisition:
  [How users will see it]

- Sample size:
  [N]

- Timeline:
  [7-14 days preferred]

- Pass criteria:
  [Specific behavioral threshold]

- Fail criteria:
  [Specific result that forces pivot/kill]

- Inconclusive criteria:
  [What result requires more data]

- Next action if pass:
  [What to build/test next]

- Next action if fail:
  [What to change or abandon]
```

Rules:

- Prefer behavioral evidence over compliments.
- Prefer past behavior over future intention.
- Prefer payment, data submission, repeat use, or referral over "sounds cool."
- Never test five assumptions at once.
- Never call an experiment successful without pre-written pass criteria.

---

## Phase 8: Interpret Results

After the test, classify the result.

### GO

The customer has the problem, recognizes it, takes action, and the MVP creates value.

### PIVOT

There is a real problem, but the customer, use case, pricing, channel, or solution form is wrong.

### KILL

No painful problem, no behavior change, no willingness to pay, or no reachable customer.

### CONTINUE DISCOVERY

The signal is mixed because the customer segment or test design was unclear.

Output:

```text
Decision:
- GO / PIVOT / KILL / CONTINUE DISCOVERY

Evidence:
- Strongest positive signal:
- Strongest negative signal:
- What we learned:
- What changed in our belief:
- Next test:
```

---

# Interview Rules

Use Mom Test principles.

Ask about:

- Past behavior
- Specific recent events
- Current workaround
- Money/time spent
- Decision process
- Failed attempts

Do not ask:

- "Would you use this?"
- "Do you like this idea?"
- "Would you pay for this someday?"
- "Is this useful?"

Better questions:

- "Tell me about the last time this happened."
- "What did you do next?"
- "How long did that take?"
- "Who was involved?"
- "What did it cost?"
- "What happens if you do nothing?"
- "Have you tried to solve this before?"
- "What do you currently use instead?"

---

# Output Format for User

When analyzing an idea, always produce:

## 1. Blunt Diagnosis

Is this currently:

- Real problem
- Weak problem
- Solution looking for a problem
- Trend/copycat idea
- Research direction, not yet a business

## 2. Possible Real Problems Underneath

List 3-7 hidden problem candidates.

## 3. Bottleneck Map

Classify each candidate by bottleneck type.

## 4. Wedge Recommendation

Pick the best first wedge or say none is clear yet.

## 5. Riskiest Assumption

State the one assumption to test first.

## 6. MVP Experiment

Design the simplest test with artifact, audience, timeline, pass/fail criteria, and what to do next.

## 7. Kill/Pivot Conditions

Specify what evidence would make us stop or change direction.

---

# Example: Taste AI

Initial idea:

"AI taste scorer that vectorizes taste and predicts performance."

Diagnosis:

Technology-first. Interesting research direction, not yet a business.

Possible problem candidates:

1. Food R&D teams cannot cheaply reduce recipe candidates before sensory testing.
2. Delivery restaurants cannot tell whether bad reviews come from taste or expectation mismatch.
3. Franchise brands cannot maintain perceived taste consistency across branches.
4. Menu developers cannot explain why a menu failed after launch.
5. Operators rely on founder taste judgment that does not scale.

Likely wedge:

"Menu candidate pre-screening for small food brands or franchise teams before paid testing."

Riskiest assumption:

Food operators or menu planners currently experience candidate selection as painful enough to pay for a pre-screening report.

MVP:

Manual report MVP.

Experiment:

- Interview 10 operators/menu planners.
- Ask for one recent menu decision.
- Produce a manual analysis report from menu description, pricing, photos, reviews, and competitor menu.
- Measure whether at least 3 of 10 provide real data, 2 of 10 ask for a second report, or 1 of 10 agrees to a paid pilot.

Pass:

At least 3 strong behavioral signals.

Fail:

Only curiosity, no data sharing, no repeat request, no willingness to pay.

---

# Example: Personality Test Product

Initial idea:

"SBTI is popular. I want to make a paid personality test."

Diagnosis:

Copycat-first. Must identify the job SBTI performs.

Possible real jobs:

1. Users want a funny self-label they can share.
2. Users want a low-risk way to talk about themselves.
3. Users want a social object for friends and dating.
4. Users want a longer, flattering self-narrative.
5. Users want identity entertainment, not scientific diagnosis.

Likely wedge:

"Shareable identity-entertainment test for a specific social context."

Riskiest assumption:

The chosen theme creates enough curiosity and sharing behavior to justify a paid deep report.

MVP:

Landing page + sample result cards + fake door/payment button.

Experiment:

- Create 3 test concepts.
- Make 3 sample result cards each.
- Drive traffic via Threads, Instagram, or community posts.
- Measure click, completion, share, and payment intent.

Pass:

One concept gets meaningfully higher CTR and at least a few payment attempts or strong DM requests.

Fail:

People say it is funny but do not click, share, or request results.

---

# Final Principle

Do not ask:

> "What can we build?"

Ask:

> "Where is the repeated friction, who is already trying to solve it, and what is the smallest behavioral test that proves it matters?"
