---
name: reverse-engineering-products
description: >
  Analyzes existing products, services, apps, content formats, or business ideas by reverse-engineering
  the customer target, usage situation, solved phenomenon, bottleneck hypothesis, customer expectations,
  alternatives, monetization logic, retention/virality loop, weaknesses, and transferable lessons.
  Use when the user asks why a product is popular, what problem it solves, what customers expect from it,
  or how to learn from an existing business item without copying only the surface.
---

# Skill: Reverse Engineering Products

## Purpose

This skill analyzes an existing product, service, content format, or business item by reverse-engineering the problem structure underneath it.

The goal is not to describe what the product does on the surface.  
The goal is to understand:

- Who it is really for
- What situation triggers usage
- What phenomenon it resolves
- What bottleneck it attacks
- What customers actually expect
- What alternatives it replaces
- Why people pay, share, return, or churn
- What lessons can be transferred to new ideas

Core principle:

> Do not copy the visible product.  
> Copy the problem structure, customer expectation, bottleneck insight, and behavioral loop that made it work.

---

## When to Use

Use this skill when the user asks things like:

- "Why is this product popular?"
- "What problem does this product actually solve?"
- "What target customer is this business item built for?"
- "What bottleneck did this product identify?"
- "Why do customers pay for this?"
- "Is this just a trend, or is there a real problem underneath?"
- "I want to make something like this. What should I copy and what should I not copy?"
- "Analyze this app/service/product as a startup idea."

This skill is complementary to `finding-wedge-problems`:

- `reverse-engineering-products` analyzes existing products from the outside.
- `finding-wedge-problems` converts the user's own vague idea into a testable wedge problem.

---

## Operating Stance

Be skeptical of surface-level explanations.

Avoid shallow explanations like:

- "It is popular because it is fun."
- "It works because people like AI."
- "It solves convenience."
- "It went viral because of marketing."

Prefer deeper explanations like:

- "It gives users a low-risk way to talk about themselves."
- "It reduces uncertainty at a high-friction decision point."
- "It turns private anxiety into a shareable social object."
- "It monetizes the moment when curiosity peaks."
- "It attacks the delay between trying something and learning whether it worked."

Do not assume every popular product solves a deep pain. Some products solve entertainment, identity, status, relief, fantasy, or social coordination.

---

# Workflow

## Phase 1: Surface Description

Describe what the product appears to be.

Output:

```text
Surface Description:
- Category:
- Main user-facing promise:
- Core interaction:
- Pricing or monetization visible to users:
- Distribution channel:
```

Rule:

Keep this section short. It is only the surface layer.

---

## Phase 2: Identify the Likely Target Customer

Define the most reactive customer segment.

Avoid broad categories like:

- "20s users"
- "restaurants"
- "people who like productivity"
- "AI users"

Prefer behavior-specific segments:

- "SNS-active users who want a funny self-label to share with friends"
- "small delivery restaurant owners deciding which new menu item to launch"
- "solo founders who want to validate an idea before writing code"
- "team leads who repeatedly summarize customer feedback for product decisions"

Output:

```text
Likely Target Customer:
- Primary user:
- Buyer, if different:
- Most reactive subsegment:
- Why this segment reacts strongly:
- Who is probably not the target:
```

---

## Phase 3: Usage Situation

Identify the situation that triggers use.

Ask:

- What just happened before the user wants this?
- What decision, emotion, boredom, anxiety, or social moment creates demand?
- Is usage planned, impulsive, repeated, or event-driven?

Output:

```text
Usage Situation:
- Trigger moment:
- User state before use:
- Desired state after use:
- Frequency:
- Urgency:
```

---

## Phase 4: Solved Phenomenon

Classify what the product resolves. It may not be a conventional pain.

Use one or more categories:

### 1. Pain Relief
The user wants a costly or stressful problem to disappear.

### 2. Uncertainty Reduction
The user cannot decide, predict, interpret, or diagnose something.

### 3. Effort Reduction
The product saves time, labor, attention, or coordination cost.

### 4. Identity Expression
The product helps the user express who they are.

### 5. Social Object Creation
The product creates something people can share, discuss, compare, or react to.

### 6. Status or Signaling
The product helps the user look competent, tasteful, early, smart, attractive, disciplined, or high-status.

### 7. Emotional Relief
The product turns anxiety, loneliness, boredom, guilt, or confusion into a more manageable feeling.

### 8. Fantasy or Entertainment
The product creates amusement, immersion, curiosity, novelty, or play.

### 9. Trust or Risk Management
The product reduces fear of making a bad choice.

### 10. Workflow Control
The product gives the user a clearer process, dashboard, system, or operating rhythm.

Output:

```text
Solved Phenomenon:
- Main phenomenon:
- Secondary phenomenon:
- Evidence or clues:
- What the user would lose without this product:
```

---

## Phase 5: Bottleneck Hypothesis

Infer the bottleneck the product attacks.

Use the bottleneck types from `finding-wedge-problems` when useful:

1. Judgment Bottleneck
2. Manual Labor Bottleneck
3. Information Fragmentation Bottleneck
4. Expectation-Reality Mismatch Bottleneck
5. Quality Consistency Bottleneck
6. Learning Bottleneck
7. Scaling Bottleneck
8. Validation Delay Bottleneck

Also consider consumer/social bottlenecks:

9. Self-Expression Bottleneck
The user wants to express something about themselves but lacks an easy, acceptable format.

10. Conversation Bottleneck
People want to interact but need a low-friction topic, prompt, or social object.

11. Trust Bottleneck
The user is willing to act only if the product reduces perceived risk.

12. Taste Translation Bottleneck
The user has preferences but cannot articulate or operationalize them.

Output:

```text
Bottleneck Hypothesis:
- Bottleneck type:
- What gets stuck:
- Why existing alternatives do not fully solve it:
- How the product removes or bypasses the bottleneck:
```

---

## Phase 6: Customer Expectations

Separate what customers expect into three layers.

### Functional Expectations
What the product must do.

Examples:
- Generate a result quickly
- Save time
- Recommend something
- Produce a report
- Enable payment or booking

### Emotional Expectations
What the user wants to feel.

Examples:
- "This understands me"
- Relief
- Confidence
- Excitement
- Curiosity
- Validation
- Control

### Social Expectations
What the user wants the product to help them do with others.

Examples:
- Share a result
- Start a conversation
- Look smart
- Look funny
- Belong to a group
- Compare with friends

Output:

```text
Customer Expectations:
- Functional:
  1.
  2.
- Emotional:
  1.
  2.
- Social:
  1.
  2.

Most important expectation:
- [Functional / Emotional / Social]
```

---

## Phase 7: Existing Alternatives

Identify what users do instead.

Do not limit alternatives to direct competitors. Include substitute behaviors.

Types of alternatives:

- Direct competitors
- Manual workarounds
- Human experts
- Spreadsheets
- Search
- Social media
- Friends and group chats
- Consultants
- Doing nothing
- Guessing by gut feel
- Existing rituals or cultural practices

Output:

```text
Existing Alternatives:
- Direct alternatives:
- Indirect alternatives:
- Behavioral substitutes:
- Why users still switch or try this product:
```

---

## Phase 8: Why Now

Explain timing.

Possible timing drivers:

- New technology makes delivery cheaper or better
- Existing solution became stale or saturated
- Cultural behavior changed
- Distribution channel became available
- Regulation changed
- Consumer expectations shifted
- Market pain intensified
- Competitors educated the market

Output:

```text
Why Now:
- Timing driver:
- What changed recently:
- What would have been harder before:
- Is this durable or trend-dependent?
```

---

## Phase 9: Monetization Logic

Analyze where money can be captured.

Ask:

- Does payment happen before, during, or after the value moment?
- Is the buyer paying for utility, relief, status, identity, entertainment, risk reduction, or time savings?
- Is monetization tied to a peak curiosity moment, repeated workflow, urgent pain, or business ROI?

Output:

```text
Monetization Logic:
- Free value:
- Paid value:
- Payment trigger:
- Pricing logic:
- Willingness-to-pay strength:
- Weakness in monetization:
```

---

## Phase 10: Retention and Virality Loop

Analyze whether the product is one-off, repeated, viral, or workflow-embedded.

Possible loops:

### Utility Loop
The product becomes part of a recurring workflow.

### Social Sharing Loop
Users share outputs and bring new users.

### Identity Loop
Users return because the product reinforces self-understanding or personal narrative.

### Data Improvement Loop
More usage improves recommendations, personalization, or model performance.

### Marketplace Loop
More supply improves demand, and more demand attracts supply.

### Status Loop
Users return to maintain progress, ranking, streaks, or reputation.

Output:

```text
Retention / Virality Loop:
- Primary loop:
- How a new user arrives:
- What makes them share or return:
- What breaks the loop:
- One-off risk:
```

---

## Phase 11: Weakness and Illusion

Identify what looks strong on the surface but may be weak underneath.

Common illusions:

- Viral does not mean durable.
- Likes do not mean willingness to pay.
- A cool technology does not mean a painful problem.
- A large market does not mean reachable customers.
- A detailed report does not mean users value depth.
- High novelty can decay quickly.
- Copying format without copying context fails.
- Strong free usage may not convert to paid.

Output:

```text
Weakness / Illusion:
- Surface strength:
- Possible hidden weakness:
- Evidence needed:
- What would make this fail:
```

---

## Phase 12: Transferable Lessons

Extract lessons for the user’s own idea.

Separate:

### Copy the Structure
The deeper mechanism worth learning.

Examples:
- Shareable self-label
- Manual report before automation
- Result card as social object
- Paid deep dive after free curiosity
- Workflow wedge before platform expansion
- Reducing validation delay

### Do Not Copy the Surface
The visible feature that may not transfer.

Examples:
- Personality test format
- AI branding
- Dashboard UI
- Subscription pricing
- Viral result names

Output:

```text
Lessons for My Own Idea:
- What to copy structurally:
- What not to copy superficially:
- What assumption to test before borrowing this pattern:
- Best MVP inspired by this product:
```

---

# Final Output Format

When analyzing a product, always produce:

## 1. Surface Description
What the product appears to be.

## 2. Likely Target Customer
Who reacts most strongly and why.

## 3. Usage Situation
When and why the user reaches for it.

## 4. Solved Phenomenon
The actual user need, desire, pain, social function, or emotional job.

## 5. Bottleneck Hypothesis
The specific bottleneck this product attacks.

## 6. Customer Expectations
Functional, emotional, and social expectations.

## 7. Existing Alternatives
Direct competitors and substitute behaviors.

## 8. Why Now
Why this product can work in the current environment.

## 9. Monetization Logic
Why and when users pay.

## 10. Retention / Virality Loop
Why users return or share.

## 11. Weakness / Illusion
What may be misleading about its apparent success.

## 12. Lessons for My Own Idea
What to borrow structurally and what not to copy.

---

# Example: SBTI-style Personality Test

## 1. Surface Description

A humorous personality test inspired by MBTI-style formats.

## 2. Likely Target Customer

SNS-active users who want a funny, low-risk self-label to share with friends.

## 3. Usage Situation

A user sees a friend’s result, becomes curious, takes the test quickly, and shares their own result for comparison and conversation.

## 4. Solved Phenomenon

Not primarily scientific diagnosis. It solves lightweight self-expression, identity entertainment, and social conversation creation.

## 5. Bottleneck Hypothesis

MBTI became familiar and somewhat serious. Users need a fresh, funny, socially acceptable way to talk about themselves without being too vulnerable.

Bottleneck type:

- Self-Expression Bottleneck
- Conversation Bottleneck
- Social Object Creation

## 6. Customer Expectations

Functional:

- Fast test
- Immediate result
- Clear type label
- Optional deep report

Emotional:

- "This gets me"
- Amusement
- Validation
- Curiosity

Social:

- Share with friends
- Compare results
- Start conversation

## 7. Existing Alternatives

- MBTI
- Astrology
- Tarot
- Meme quizzes
- Instagram story prompts
- Friend group personality talk

## 8. Why Now

MBTI is familiar but saturated. Users still want identity labels, but need novelty and humor. Social platforms reward shareable result cards.

## 9. Monetization Logic

Free test creates curiosity. Paid report monetizes the peak moment when the user wants a longer, more flattering, more detailed self-narrative.

## 10. Retention / Virality Loop

Result card sharing brings friends. Friends take the test to compare. The product spreads through social identity comparison, not repeated utility.

## 11. Weakness / Illusion

Virality may be short-lived. Free completion does not guarantee paid conversion. Novelty can decay quickly.

## 12. Lessons for My Own Idea

Copy structurally:

- Shareable self-label
- Fast free test
- Result card as social object
- Paid deep report after curiosity peaks

Do not copy superficially:

- MBTI-like format without a fresh social context
- Long reports if users only want shareable fun
- Scientific positioning if the real job is identity entertainment

Best MVP:

Landing page + 3 sample result cards + fake door/payment button to test curiosity, sharing, and paid-report intent.

---

# Example: AI Startup Idea Validator

## 1. Surface Description

An AI tool that scores startup ideas and produces validation reports.

## 2. Likely Target Customer

Solo founders, indie hackers, and early builders who are afraid of wasting months building something nobody wants.

## 3. Usage Situation

The user has an idea but lacks confidence. They want an external judgment before committing time, money, or identity to the project.

## 4. Solved Phenomenon

Uncertainty reduction and emotional relief. The user wants to feel less alone and less delusional before building.

## 5. Bottleneck Hypothesis

The bottleneck is not idea generation. The bottleneck is deciding whether an idea deserves work before evidence exists.

Bottleneck types:

- Judgment Bottleneck
- Validation Delay Bottleneck
- Emotional Relief

## 6. Customer Expectations

Functional:

- Scorecard
- Risks
- Next action
- Competitor overview

Emotional:

- Confidence
- Relief
- Feeling less foolish
- Sense of progress

Social:

- Shareable memo
- Something to show a cofounder, investor, or friend

## 7. Existing Alternatives

- Asking ChatGPT
- Asking friends
- Posting on Reddit
- Reading startup advice
- Building anyway
- Paying a consultant

## 8. Why Now

LLMs make structured analysis cheap and instant. More solo founders are building with AI, which increases the need for fast pre-build judgment.

## 9. Monetization Logic

Users may pay for deeper research, competitor analysis, investor-style scorecards, or concrete MVP experiments.

## 10. Retention / Virality Loop

Retention may come from repeated idea evaluation. Virality comes from sharing scores, reports, or harsh verdicts.

## 11. Weakness / Illusion

A polished scorecard can create false confidence. Without real customer evidence, the tool may only produce plausible analysis.

## 12. Lessons for My Own Idea

Copy structurally:

- Turn vague anxiety into a structured decision artifact
- Give one concrete next action
- Identify the riskiest assumption

Do not copy superficially:

- VC-style scoring without real behavioral evidence
- Long reports that feel authoritative but do not change action

Best MVP:

Manual analysis of 10 founders’ ideas with a structured memo. Measure whether they take the recommended next action, ask for more, or pay for a deeper report.

---

# Final Principle

Do not ask only:

> "What does this product do?"

Ask:

> "What customer situation made this product necessary, what bottleneck did it remove, what expectation did it satisfy, and what behavioral loop made it spread or monetize?"
