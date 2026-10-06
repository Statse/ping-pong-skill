# Deliverables

Fill each section from the rally's final version. Drop a section only when it truly has nothing to say.

## One-shot build prompt

A prompt a coding agent can execute in one session, start to finish.

```
# Build: <name>

## Goal
<one paragraph: what it is, who it is for, what "working" looks like>

## Requirements
<numbered, testable statements; behaviour, not implementation wishes>

## Tech and constraints
<stack, libraries, platform, limits; say "agent's choice" where it truly does not matter>

## Design notes
<data model, key flows, UI notes — only what the rally settled>

## Acceptance checks
<how the agent proves it is done: commands to run, behaviours to verify>

## Out of scope
<what not to build>
```

## Ticket-ready spec

A spec shaped so `/to-tickets` or `/to-issues` can cut it into tracer-bullet tickets.

```
# Spec: <name>

## Problem and goal
## Users and main flows
## Architecture
<components, boundaries, data model, external services>

## Vertical slices
<ordered; each slice is thin, end-to-end, and demoable>
1. <slice> — delivers: <user-visible result> — depends on: <slices or none>

## Acceptance criteria
<per slice>

## Decisions made in the rally
<choice + one-line reason>

## Open questions
<blocking ones first>

## Out of scope
```

## Non-code idea

Pick the form the idea will actually be used in and say which you picked: a plan with milestones, a pitch, a content outline, a creative brief, an event run-sheet. Whatever the form, include: the refined idea in one paragraph, the concrete parts, the first next step, and open questions.
