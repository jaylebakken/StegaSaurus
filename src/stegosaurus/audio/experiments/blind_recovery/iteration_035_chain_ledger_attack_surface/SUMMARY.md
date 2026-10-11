# Iteration 035 - Chain Ledger Attack Surface

## Goal

Design a chain-ledger registry model and stress-test whether independent child
watermark updates can support a usable custody chain without decreasing
robustness or increasing misattribution risk.

The intended product idea is valuable:

```text
song lifecycle -> parent/child custody events -> verification reconstructs
which registry events are supported by audio evidence
```

But the registry must distinguish system-observed facts from user-supplied
labels, and the audio layer must not turn chain updates into a denial or false
attribution surface.

## Ledger Design

Each chain event is append-only and parent-linked:

```text
event_id
parent_event_id
handle_hex
trust_level
system_fact
user_label
```

System fact fields:

```text
event_id
parent_event_id
handle_hex
trust_level
system_fact
```

User-supplied fields:

```text
user_label
```

Trust levels:

```text
system_created
system_verified
imported_signed
imported_untrusted
user_label_only
```

Policy:

```text
Verification may identify a registry event. User labels remain context, not
absolute proof of fault.
```

So the product should say:

```text
Matched system-created event event_01, user label "Mixer preview"
```

not:

```text
Mixer leaked the file
```

## Stress Matrix

The experiment used `10. Lovers Rock.wav`, sequentially embedded chain events,
then verified every retained event record against the final audio.

| Scenario | Transform | Recovered events | Latest recovered | Min RS cost | Status |
| --- | --- | ---: | --- | ---: | --- |
| chain length 1 | clean | 1 | yes | 1 | latest recovered |
| chain length 1 | peak normalized | 1 | yes | 2 | latest recovered |
| chain length 1 | light recorded proxy | 1 | yes | 6 | latest recovered |
| chain length 1 | leading crop 30s | 0 | no | 37 | no event recovered |
| chain length 2 | clean | 0 | no | 18 | independent update destroyed evidence |
| chain length 2 | peak normalized | 0 | no | 17 | no event recovered |
| chain length 2 | light recorded proxy | 0 | no | 24 | no event recovered |
| chain length 3 | clean | 0 | no | 19 | independent update destroyed evidence |

## Interpretation

The ledger model is useful, but independent child re-watermarking is not a safe
encoder strategy yet.

Key bottlenecks:

1. A single retained full-song event can survive clean, peak-normalized, and
   light recorded-proxy verification in this geometry.
2. A simple leading crop breaks retained-record verification, confirming that
   crop geometry remains a major capacity/geometry bottleneck.
3. A second independent child event destroys recoverability even before crop or
   distress is applied.
4. No wrong event recovered in this stress pass, so the immediate failure is
   denial-of-attribution rather than false attribution.

## Attack Surface

Independent updates currently behave like overwrite attacks:

```text
parent event -> child event
```

does not produce:

```text
recoverable parent + recoverable child
```

and does not reliably produce:

```text
recoverable latest child
```

Instead, it often produces:

```text
no recoverable chain event
```

That is too severe for a product chain encoder.

## Product Guidance

Do build the ledger:

```text
append-only chain events
parent-child links
system facts separate from user labels
trust levels
verification wording that avoids blame overclaims
```

Do not yet ship independent child re-watermarking as the audio-chain update
mechanism.

## Next Experiment

Iteration 036 should test safer update strategies:

1. Same-handle reinforcement instead of independent child handles.
2. Partitioned carrier regions for parent and child events.
3. Shorter block schedules that assign different custody events to different
   time regions instead of overlaying them.
4. Tamper classification: distinguish `no watermark` from `conflicting
   overwritten watermark-like evidence`.
5. Branch controls: parent -> child A and parent -> child B should not let one
   branch claim evidence from the other.

The working hypothesis is that the ledger should represent the lifecycle now,
while the encoder should move toward partitioned or same-claim reinforcement
rather than independent overlays.
