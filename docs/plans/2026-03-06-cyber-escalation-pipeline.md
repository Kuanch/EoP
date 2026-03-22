# Cyber Escalation Pipeline Plan

**Goal:** Make the Cyber tab useful for geopolitical warning by separating generic IOC noise from events that could indicate state tension, infrastructure disruption, or conflict-adjacent cyber activity.

**Problem:** The current cyber pipeline is strong at collecting threat intelligence, but weak at answering `who is being targeted`, `which region matters`, and `does this affect war-risk scoring now`.

## Principles

- Generic IOC feeds are baseline telemetry, not escalation by default.
- Regional threat scoring should only be influenced by cyber events with geopolitical relevance.
- Confidence must be explicit. Public IOC feeds rarely prove attacker identity or victim destination.
- The first version should be rule-based and explainable before adding any LLM or external enrichment.

## Target Model

Each cyber event should carry:

- `escalation_level`: `background` | `elevated` | `strategic`
- `escalation_score`: rule-based 0-10 score
- `geo_region`: probable region or `Global`
- `target_sector`: `government` | `military` | `telecom` | `energy` | `transport` | `satellite` | `finance` | `critical_infra` | `unknown`
- `attribution_confidence`: `low` | `medium` | `high`
- `war_signal`: boolean for events strong enough to influence threat posture

## Phase 1: Rule-Based Escalation Classifier

**Files:**
- Create: `cyber_escalation.py`
- Modify: `collectors/cyber.py`
- Modify: `scoring.py`
- Modify: `static/js/cyber.js`

**Scope:**
- Detect critical-infrastructure, government, telecom, transport, and military keywords.
- Detect higher-risk patterns such as `ddos`, `wiper`, `satellite`, `gps`, `gnss`, `jam`, `outage`, `port`, `airport`, `power grid`, `telecom`, `apt`.
- Map event text to a probable region using existing geography keywords where possible.
- Keep URLhaus/C2Intel events mostly `background` unless they include strong strategic keywords.
- Expose summary counts in `/api/cyber`.
- Use only `elevated` and `strategic` events in regional cyber scoring.

## Phase 2: Threat Feed Integration

**Files:**
- Modify: `threat_engine.py`
- Modify: `collectors/cyber.py`
- Modify: `static/js/threats.js`

**Scope:**
- Add a separate threat-feed path for cyber escalation incidents.
- Surface `geo_region`, `target_sector`, and `attribution_confidence` in the Threats tab.
- Keep generic IOC events out of the high-risk geopolitical feed unless they cross an escalation threshold.

## Phase 3: Higher-Signal Sources

Potential sources to add later:

- Government CERT and national cyber advisory feeds
- NetBlocks or similar public outage reporting
- GPS/GNSS interference data
- High-confidence infrastructure disruption reporting

## First Slice Definition

This branch starts with:

1. Rule-based cyber escalation classifier
2. Collector integration and API metadata
3. Regional threat scoring change to use escalation-aware cyber events
4. Cyber tab badges and summary counts for escalations

This is intentionally conservative. It improves signal quality without claiming attribution the data cannot support.
