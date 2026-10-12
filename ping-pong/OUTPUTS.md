# Deliverables

One rally returns one outcome. Default to **Refined idea**; use one of the shapes below
only when the brief asks for it, and follow the brief over any template here. Fill each
section from the rally's final version, the owner brief and the standing decisions.
Drop a section only when it truly has nothing to say.

## Refined idea (default)

The idea itself, standalone, in the language of the brief. No template picker, no
interview, no build prompt or ticket spec unless the brief asked for one.

```
# <name>

<one paragraph: what it is, who it is for, why it is worth doing>

<the concrete parts the rally settled: structure, mechanics, scope, trade-offs>

## First next step
<the one thing to do next>

## Open questions
<only the ones genuinely still open; omit the section when there are none>
```

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

## Another requested form

When the brief names a form this file does not cover, write that form. Pick the shape the idea will actually be used in and say which you picked: a plan with milestones, a pitch, a content outline, a creative brief, an event run-sheet. Whatever the form, include: the refined idea in one paragraph, the concrete parts, the first next step, and open questions.
