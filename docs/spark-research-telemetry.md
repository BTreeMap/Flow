# Spark anonymous research telemetry

The independent Spark prototype is deliberately **account-free**. It must not
invoke Flow registration, login, passkeys, project membership, or email. Its
research identity is a pseudonymous browser installation, not an authentication
or authorization mechanism.

## Identity strategy

Every Spark request contains four client-generated fields:

1. A random UUID stored under `flow.spark.research-installation-id.v1` in
   `localStorage`. This is the primary longitudinal anchor for one browser
   installation.
2. A ThumbmarkJS hash generated locally without a ThumbmarkJS API key. Only the
   resulting hash is sent to Flow; Thumbmark components are not sent to any
   third party.
3. ThumbmarkJS version, browser locale, and IANA timezone as diagnostic context
   for fingerprint-stability analysis.
4. A per-flow UUID and a unique client-event UUID, so flows can be reconstructed
   and retries do not duplicate analysis rows.

The server requires `FLOW_CRYPTO_MASTER_KEY`, an unpadded Base64URL encoding of
exactly 32 random bytes. BLAKE3 derives the dedicated Spark-identity key using
the fixed `flow.spark.identity-keyed-hash.v1` context, then uses BLAKE3 keyed
mode for each identifier. It stores neither raw identifier nor logs either
value. Use one stable master key for a study;
rotating it prevents future requests from linking to past participants.

Clearing site data creates a new installation identity. A changed or shared
fingerprint never automatically merges participants: fingerprint observations
remain separate so researchers can quantify instability and potential
collisions before deciding whether a stronger identity technique is needed.

The configured master key is applied to every incoming Spark request. Since raw
browser identifiers are never stored, rotating it makes the next request from
an existing installation resolve to a new pseudonymous participant; historical
interaction records remain intact but cannot be cryptographically linked.

## Stored records

| Table | Purpose |
| --- | --- |
| `spark_participants` | One row per keyed-hash browser-local installation ID. |
| `spark_fingerprint_observations` | Keyed-hash fingerprint observations, version, locale, timezone, first/last seen, and count. |
| `spark_interactions` | Immutable condition-scoped events, including generated cards, selection, timer outcome, feedback, cue, and final ratings. |

`POST /spark/generate` persists an idempotent `generation_succeeded` event with
the researcher-relevant request context and response cards. It intentionally
excludes identity inputs from the stored payload. The response carries the
study's `timer` policy (default length and the lengths offered), so the policy
in force is recorded per flow without a second endpoint or an extra round-trip.

The number of cards is derived server-side from the condition and whether a
base card is present — one for A and C, one per vibe for B and a first D
generate, and one for every remix in either adaptive condition. Clients do not
send a count.

`POST /spark/events` accepts a strict discriminated event union:

- `flow_started`
- `intake_answered` — `field` is `anchor` or `action`. The intake does **not**
  ask participants to name a vibe, so `frame` is not a valid field. It no
  longer asks a time of day either: that question offered a reminder nothing
  schedules, and its answer only reached the model as `time: Morning` in the
  context for a Spark done in the moment. Rows already carrying `field: "time"`
  remain readable — payloads are stored as JSON and the narrowed union bounds
  new requests only.
- `frame_selected` — emitted when a participant picks a card, carrying that
  card's vibe. It is a *revealed* preference (chosen after seeing concrete
  Sparks), never a stated one.
- `card_selected` — `rank` is the 1-based position within the flat list chosen
  from, 1–5. Conditions B and D both offer one Spark per vibe, so rank is
  unordered in B (the sampler is random) and meaningful in D (ranked by
  predicted fit). Join it with the `frame_selected` event emitted at the same
  moment to identify the card.
- `timer_finished` — carries `completion`, plus `duration_seconds` (the length
  the countdown was set to), `elapsed_ms` (measured from a monotonic clock, not
  by counting ticks) and `duration_source` (`study_default` or `participant`).
  All three are required: the countdown is participant-configurable, so a
  completion is not comparable across participants without the length it ran
  for, and a length is not interpretable without knowing who chose it. Rows
  written before this field existed should be read as `duration_seconds = 60`,
  `duration_source = study_default`.
- `feedback_submitted`
- `cue_selected` — the cue the participant committed to, plus their
  confidence. It carries no `reminder`: Spark offered "add to calendar" and
  "email me" and did neither, and being account-free it has no address to mail
  to. The cue is a stated intention, never a delivery instruction. Rows already
  carrying `reminder` stay readable.
- `condition_completed`

This provides condition-level evidence for delivery, choice, personalization,
selection, completion, perceived fit, action clarity, and willingness to try.

## Analysis considerations

- Treat the browser installation as the longitudinal unit for the initial
  study, not as a person-level identity.
- Measure fingerprint stability as distinct keyed-hash fingerprints per
  `spark_participants.id`, and potential duplication as distinct participants
  per keyed-hash fingerprint.
- Compare conditions only after accounting for repeated flows from the same
  installation and the flow completion rate.
- Do not use pseudonymous Spark identity for access control, the Flow
  conversation engine, invitations, memberships, or Web Push.
- Retention, consent language, and export/deletion processes remain study-level
  governance decisions and must be approved before collecting participant data.

## Participant-facing copy

The prototype's copy must not describe the study to the person in it. The rule
the Spark UI follows is that the *manipulation* must be perceivable while the
*design* must not: "shaped around what you told us" stays, because a
participant who cannot perceive personalization is not receiving the C/D
treatment; "Condition C", the names of the outcome measures, references to other
conditions, and any statement of what a condition is testing do not. Copy that
varies by condition lives in one table, `web/src/pages/spark/sparkCopy.ts`, so
it can be diffed against the protocol.

Two deliberate exceptions. The home grid still shows all four options with their
names and tags, because participants are not assigned a condition — they choose
one, and the grid is the choice. And the research-privacy paragraph on that grid
is disclosure rather than leakage; it must survive any future copy pass.

Card prose must never name a duration. The participant sets the countdown, so
"for 60 seconds" in a card contradicts the timer running beside it. The bundled
library is checked for this in `tests/test_api.py`; the researcher-maintained
Sheet carries the same rule but cannot be enforced from code.
