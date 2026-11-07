# Budget Care — Product Requirements Document (v1)

Status: Draft for review · Date: November 6, 2026 · Platform: Telegram bot

## 1. Overview

**Budget Care **is a Telegram bot that helps people reach short-term savings goals (a holiday, a dream outfit, an emergency fund) by turning each goal into a pet that must be cared for. Each saving deposit is "feeding" the pet. The pet's condition reflects how consistently you show up, and the final outcome reflects how much you actually saved.

The bot tracks **deposits only**, never expenses. Goals last **at most 365 days**.

## 2. Problem Statement

People who want to save for a specific near-term goal usually fail for behavioral reasons, not mathematical ones: they forget, drift away from the habit, and have no feedback on whether they are on pace. General budgeting apps are built for lifelong financial tracking, so they are heavy, expense-focused, and easy to abandon. The alternative (a Notes app, a spreadsheet, a bank pocket) offers no reminder, no sense of progress, and no emotional stake.

Budget Care targets this gap with a lightweight chat-based habit loop: a named goal, a fixed saving rhythm, timely reminders, and a pet whose wellbeing makes consistency feel meaningful.

**Evidence status:** this problem framing is an assumption, not yet validated with users. Validation is built into the pilot (see Section 12).

## 3. Goals

**User goals**

- G1. Help a user set up a savings goal and see its schedule and per-feeding amount in under 2 minutes.
- G2. Help users keep a consistent saving rhythm (on-time feeding rate of at least 70% across active goals, a hypothesis to calibrate).
- G3. Give users a live, honest read on whether they are on pace to hit their target.

**Product goals**

- G4. Prove that the pet framing improves retention versus plain logging (pilot A/B).
- G5. Reach a goal completion (graduation) rate of at least 35% of created goals (hypothesis).

## 4. Non-Goals

- **Expense tracking or categorization.** A crowded category and a different product; deposit-only keeps the loop simple.
- **Bank, e-wallet, or payment integration.** All records are self-reported in v1. It avoids compliance and security scope.
- **Shelter popularity / trust points and social leaderboards.** A meta-game stacked on an unproven core loop; revisit after retention data (P2).
- **Editing goals.** Goal terms (name, budget, period, frequency) are fixed after creation; users can only delete. This keeps the schedule and scoring integrity simple.
- **Pet death.** The pet can become sick but never dies, so a user never has a reason to quit a goal they are still saving for.
- **Multi-currency, web app, or native app.** v1 is Telegram only and uses dollars.

## 5. Target Users

- **Goal saver.** Saves for one concrete, time-bound purchase and wants a gentle push and visible progress.
- **Emergency builder.** Wants to quickly whip up a buffer and benefits from a fixed rhythm more than from detailed analytics.
- **Multi-goal juggler.** Runs several goals at once (no limit on active pets) and needs notifications that don't become spam.

## 6. Core Concepts

| Term | Meaning |
| --- | --- |
| **Goal** | A named savings target with a budget (dollars) and a period (2 to 365 days). |
| **Pet** | The goal's avatar. Species and name are chosen by the system at creation. |
| **Feeding** | A saving record in a due period: either a deposit above $0 or "Give free food". |
| **Give free food** | A feeding worth $0 for days when the user has no money. Keeps the condition, but hurts service quality. |
| **Feeding period / cut-off** | The window a feeding belongs to, closing at 23:59 user time (see 8.2). |
| **Condition** | The pet's condition bar. Starts at 100%, drops when a feeding is missed. |
| **Care period** | Days elapsed ÷ total days. |
| **Service quality** | How well the money goal is being met. Live view is pace-based; final view is deposited ÷ target. |
| **Graduated / Expired** | Graduated: deposited ≥ target at any time. Expired: period ended below target. |

## 7. User Flow (Goal Creation)

One pass in chat, using inline buttons where possible:

1. User enters a **goal name**.
2. User enters the **budget** in dollars.
3. User enters the **period** in days (2 to 365).
4. System picks the **pet species and name** and reveals the pet.
5. System checks which **saving frequencies are valid** for this period and budget (see 8.1).
6. User picks a **frequency**: every day, every week, or every month.
7. System shows the **nominal amount per feeding**, the number of feedings, the cut-off schedule, and the cost of a missed feeding to condition.
8. System asks **notifications on or off**.
9. If on and frequency is weekly or monthly, user picks the **reminder day or date** (see 8.4).
10. System shows a **confirmation summary**; user confirms and the goal starts.
11. User logs savings (or free food); system recalculates condition, care period, and service quality continuously.
12. At the end of the period (or at graduation), system shows the **result screen**.

The feeding schedule (steps 6-7) is separate from the notification settings (steps 8-9): a user with notifications off still has due dates.

## 8. Functional Requirements

### 8.1 Goal setup (P0)

- Period must be a whole number from 2 to 365; budget must be greater than $0 and is stored as integer cents.
- The system only offers frequencies that produce **at least 2 feedings** and a **nominal of at least $1**.
- **Nominal per feeding** = budget ÷ total feedings, rounded to cents; the final feeding absorbs the rounding remainder.
- Day 1 starts at the **next midnight** in the user's timezone, so nobody gets a partial first day. Users may advance their first feeding immediately upon creation (see 8.3).
- The goal's end date is always a final cut-off, even if it is not a regular due date. It counts as a feeding in the total.
- Users may create **unlimited** active goals.
- A confirmation screen shows the full schedule before the goal is created.

**Acceptance criteria**

- Given a 28-day, $70 goal starting Monday, when the user picks weekly, then the bot shows 4 feedings of $17.50 with cut-offs on 4 consecutive Sundays at 23:59.
- Given a period where a frequency would produce fewer than 2 feedings, when frequencies are offered, then that frequency is not offered.
- Given any goal, when the user has not confirmed, then no schedule or notification is created.

### 8.2 Due dates and feeding periods (P0)

| Frequency | Cut-off |
| --- | --- |
| Every day | Every day at 23:59 |
| Every week | Every Sunday at 23:59 (period runs Monday to Sunday) |
| Every month | Last date of the month at 23:59 |

- All times use the **user's timezone**, collected at first use through a required location share. A timezone change applies going forward only.
- Store the schedule as a **rule** (not fixed dates) and compute due dates at runtime. Handle month lengths and leap years.
- A deposit or free-food log made before a cut-off belongs to the current open period. A log made after a cut-off belongs to the next period; the missed period stays missed.

**Acceptance criteria**

- Given a monthly goal in February of a non-leap year, then the cut-off is February 28 at 23:59.
- Given a user in a UTC+7 timezone, when it is 23:59 local time, then the cut-off job runs for that user and not at 23:59 server time.

### 8.3 Feeding and logging (P0)

- **Feeding** = any deposit above $0, or "Give free food" ($0), logged in an open period.
- **Advance first feeding (Day 0):** Users can immediately feed their pet on the day of goal creation (H+0), before Day 1 officially starts at midnight. A deposit (> $0) or "Give free food" ($0) logged between goal creation and Day 1 start counts directly as the feeding for Period 0 (`is_feeding = True`). This satisfies the pet immediately, while the first cut-off remains at the end of Day 1 (23:59 tomorrow), preventing any pre-midnight missed penalty rush. Subsequent deposits on Day 0 count as extra deposits (`is_feeding = False`).
- Only the **first** log in a period counts as the feeding for condition. Later logs in the same period are **extra deposits**: they add money to the total but are not another feeding.
- **Every dollar** counts toward total deposited. When deposited reaches or exceeds the target, the pet **graduates**; overflow is stored as surplus.
- Free food keeps condition but adds $0, so it lowers service quality. There is no cap on free food (quality already reflects it).
- Amount input accepts "10", "$10", and "10.50". Invalid input gets a clear error and no state change.
- With one active goal, logging goes straight to it. With several, the bot shows inline buttons to pick the pet.
- **`/undo`** reverses the last record within 24 hours, to protect against typos (e.g. 1000 instead of 100), because goals cannot be edited.
- Deposits sent to a graduated, expired, or deleted goal are rejected with a friendly message.

**Acceptance criteria**

- Given a newly created goal before Day 1 starts, when the user logs a deposit or taps "Give free food", then it is accepted as the feeding for Period 0, feeding the pet immediately.
- Given an open period with no log, when the user logs $5, then the feeding is recorded and condition is unchanged.
- Given the user already fed this period, when they log $3 more, then total deposited rises by $3 and the feeding count does not change.
- Given deposited reaches the target mid-period, then the pet graduates immediately and future notifications are cancelled.
- Given the user taps "Give free food", then condition is kept and service quality is calculated with $0 for that feeding.

### 8.4 Notifications (P0)

Notifications are an in-bot setting (Telegram has no permission prompt). If off, nothing is sent and the pet is only visibly hungry when the user opens the bot.

| Frequency | Reminder | Follow-up (if not fed) |
| --- | --- | --- |
| Every day | 10:00 | 19:00 same day |
| Every week | 10:00 on the picked day | 10:00 next day |
| Every month | 10:00 on the picked date (1-28) or last date | 19:00 next day |

- **Edge rule:** if the reminder day is the cut-off day (Sunday for weekly, last date for monthly) or the next-day follow-up would land after the cut-off (e.g. monthly pick of 28 in a non-leap February), the follow-up is replaced by a **19:00 early warning the day before** the cut-off.&#32;
- Reminders and follow-ups are **skipped if the period is already fed**, and everything stops when the goal graduates, expires, or is deleted.
- Users with multiple pets get **one digest per time slot** ("2 pets are hungry"), not one message per pet.
- Send times use small random jitter to stay within Telegram rate limits. If a user blocks the bot (HTTP 403), their jobs pause.
- Reminder day/date, notification on/off, and timezone are **editable** after creation (they are not goal terms).

**Acceptance criteria**

- Given a daily goal with notifications on and no feeding by 19:00, then exactly one follow-up is sent that day.
- Given a user with 3 hungry pets at 10:00, then they receive one message listing all three.
- Given the user fed at 09:00, then no 10:00 reminder or follow-up is sent for that period.

### 8.5 Scoring (P0)

All values are **derived from an event ledger and the computed schedule**, not from stored counters, so downtime or reschedules cannot corrupt state.

- **Condition** = 100% − (missed feedings × 100 ÷ total feedings). Floors at 0%. Drops only at a cut-off (never while a period is still open). In v1 there is **no recovery**. Final value = on-time feedings ÷ total feedings.
- **Care period** = days elapsed ÷ total days.
- **Service quality (live)** = deposited ÷ (target × care period), capped at 100%. Shown as 100% while care period is 0.
- **Service quality (final)** = deposited ÷ target, capped at 100%.
- The cost of one missed feeding (in % of condition) is shown at goal creation and in the goal view.

**Mood stages** (art scope per species): four images per species, chosen by condition: 100%, at least 75%, at least 50%, and at least 25%. Below 25% keeps the lowest image. The pet never dies; at 0% it stays sick but alive.

**Acceptance criteria**

- Given a goal with 4 feedings and one missed cut-off, then condition is 75%.
- Given the period is still open and unfed, then condition has not dropped yet and the pet shows as "hungry".
- Given a $70 goal over 28 days, when 14 days have passed with $35 deposited, then live service quality is 100%.
- Given deposited exceeds the target, then service quality displays 100% and the extra is shown as surplus.

### 8.6 Goal end states and result screen (P0)

- **Graduated:** deposited ≥ target at any time. Early completion is treated the same as on-time completion (no special event).
- **Expired:** period ended below target. The pet stays alive; the goal is closed.
- The result screen shows: final service quality, final condition, days taken, total deposited, surplus, number of free foods, and the pet's final mood or title (e.g. "Well cared for", "Struggled but made it").
- Pet reveal (species and name) happens at goal creation.

### 8.7 Goal management (P0)

- `/goals` lists active goals and the archive of finished goals (graduated or expired) with pet, mood, condition, service quality, and next cut-off.
- Deleting a goal requires a confirmation and cancels all its notifications.
- Goal terms are **not editable** (see Non-Goals).

### 8.8 Commands (P0)

`/start`, `/newgoal`, `/feed` (log a deposit or free food), `/goals`, `/undo`, `/settings`, `/delete`.

## 9. User Stories

**Goal saver**

- As a goal saver, I want to name a goal, set a budget and period, and see my per-feeding amount so that I know exactly what is expected of me.
- As a goal saver, I want a reminder on my saving day so that I don't forget.
- As a goal saver, I want to log "Give free food" when I have no money so that one tight day doesn't break my streak and I stay honest.
- As a goal saver, I want to see live whether I am on pace so that I can catch up before the deadline.

**Emergency builder**

- As an emergency builder, I want my pet to graduate the moment I hit my target so that I'm not forced to keep logging.
- As an emergency builder, I want to add extra deposits outside my set day so that I can reach the goal faster.

**Multi-goal juggler**

- As a juggler, I want one daily digest across all my pets so that notifications don't become spam.
- As a juggler, I want to pick which pet I'm feeding with one tap so that logging stays fast.

**Edge cases**

- As a user who mistyped an amount, I want to undo my last record so that a typo doesn't ruin my goal.
- As a user whose goal ended below target, I want to see a clear result so that I understand what happened and can start again.
- As a user who traveled to another timezone, I want to change my timezone so that cut-offs match my real day.

## 10. Priorities Summary

**P0 (must ship in v1):** everything in Section 8, including goal setup, schedule, feeding logic, notifications, scoring, end states, `/undo`, goal list and delete, and event logging for analytics.

**P1 (fast follow):**

- Partial recovery of condition after a miss (only if data shows drop-off after misses).
- Surplus handling and shortcuts such as "feed all hungry pets".
- Shareable result card.
- Soft-archive of deleted goals.

**P2 (design for, do not build):**

- Shelter popularity / trust points and social or group accountability.
- Species tied to goal size and length (small quick goal = hamster, long goal = tortoise).
- Multi-currency and localization.
- Graduated-pets collection; richer mood events.

## 11. Non-Functional Requirements

- **Data model:** event ledger of goal creation, feedings, deposits, undo, and cut-off events. Scores are computed from the ledger.
- **Idempotent jobs:** cut-off and notification jobs can safely run twice.
- **Time:** all scheduling is timezone-aware per user; store UTC internally.
- **Money:** integer cents everywhere; no floating-point arithmetic.
- **Telegram limits:** respect rate limits (about 1 message per second per chat), handle blocked users, and use jitter on send times.
- **Privacy:** store only what is needed (user id, timezone, goals, records). Provide a way to delete all data.
- **Analytics events:** instrument from day one (goal created, feeding logged, free food used, reminder sent/opened, goal graduated/expired, blocked).

## 12. Success Metrics

Targets are hypotheses to calibrate after the pilot.

**Leading (days to weeks)**

- Onboarding completion: at least 70% of users who run `/newgoal` confirm a goal.
- First feeding in the first period: at least 60% of new goals.
- On-time feeding rate: at least 70% of due feedings.
- Notification opt-in: at least 80%; bot block rate below 10%.
- Day-7 and day-21 retention of active goals (day-7 target 50%).

**Lagging (weeks to months)**

- Goal graduation rate: at least 35% (stretch: 50%).
- Median condition at end of goal.
- Free-food rate (high rates may signal unrealistic goal sizing).

**Pilot experiment (3 weeks, 10-20 friends):** use a stub with `/newgoal`, `/feed`, and the reminder. Split users: half get the pet framing, half get plain "log a deposit". If retention is equal at day 14, the pet is decoration, not a driver, and the design should change before building more.

## 13. Worked Example

**Goal:** Lombok trip, $70, 28 days, weekly, starting Monday, November 9, 2026.

- Cut-offs: Sundays Nov 15, 22, 29, and Dec 6 at 23:59, so **4 feedings of $17.50**. Each missed feeding costs 25% condition.
- Week 1: user deposits $17.50. Condition 100%, quality 100%, on pace.
- Week 2: user uses free food. Condition 100%; live quality at day 14 = $17.50 ÷ ($70 × 14/28) = 50%.
- Week 3: user misses the period. At the cut-off, condition drops to 75%.
- Week 4: user deposits $52.50 (extra). Total $70, so the pet graduates; the condition stays 75% and final quality is 100%. The result screen shows a "made it" title.

## 14. Open Questions

One question remains open; everything raised earlier is decided and folded into the sections above.

- **Condition recovery (data):** add partial recovery of condition only after pilot data on post-miss drop-off.

## 15. Timeline and Phasing (suggested, no hard deadlines)

- **Phase 0, Pilot stub (about 3 weeks run):** `/newgoal`, `/feed`, daily reminder, event logging; run the pet vs. plain-logging experiment.
- **Phase 1, v1 build:** full P0 scope. Dependencies: pet art (species and mood images), timezone handling, scheduler.
- **Phase 2:** P1 items, driven by pilot and early retention data.
- **Phase 3:** evaluate P2 (popularity layer, social accountability) only if day-21 retention supports it.

**Scope guardrail:** any addition to v1 must come with a removal or a timeline extension; new ideas go to a parking lot.
