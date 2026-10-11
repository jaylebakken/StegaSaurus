# Iteration 037: Registry-Only Chain Update

This suite tests a chain update rule where parent-child relationships live in
the registry, while the audio carries only one active watermark event.

## Question

Iteration 035 showed that independently encoding a child watermark on top of a
parent watermark can destroy both claims. This iteration tests the safer
alternative:

1. Preserve the clean registered master.
2. Encode each child export from that clean master.
3. Store parent-child ancestry only in the registry.
4. During verification, recover the visible event and use the registry to show
   its chain history.

## Method

The suite used `10. Lovers Rock.wav` with five retained registry events:

- `event_00_parent`
- `event_01_child_a`
- `event_02_child_b`
- `event_03_grandchild`
- `event_99_unrelated`

Each event was encoded independently from the clean source, never on top of a
previous watermarked export. Verification then checked all retained events
against each scenario.

## Results

| Scenario | Accepted event | Status |
| --- | --- | --- |
| Clean source | none | `no_event_recovered` |
| Parent visible | `event_00_parent` | `single_visible_event_recovered` |
| Child A visible | `event_01_child_a` | `single_visible_event_recovered` |
| Grandchild visible | `event_03_grandchild` | `single_visible_event_recovered` |
| Child A peak-normalized | `event_01_child_a` | `single_visible_event_recovered` |
| Child A light recorded proxy | `event_01_child_a` | `single_visible_event_recovered` |
| Child A leading crop 30s | none | `geometry_failure` |

No parent, sibling, or unrelated control event recovered from child or
grandchild audio in this retained-record test.

## Interpretation

This supports a registry-only custody-chain design. The audio should carry only
the active export event. The application can then recover that event and ask the
registry for its parent, grandparent, branch siblings, labels, and system facts.

This design avoids the destructive interference observed when child watermarks
are stacked directly over parent watermarks. It also reduces ambiguity: a leaked
child export does not need to expose the parent watermark acoustically in order
to reproduce the chain.

## Boundary

This iteration uses retained full-song geometry. The leading-crop control still
fails as `geometry_failure`, so arbitrary excerpts still need the V4
localization and fanout workflow.

## Recommendation

Use registry-only chain updates for the product workflow:

- Generate every child export from the clean registered master or a preserved
  pristine source.
- Never re-watermark an already-watermarked child as the normal custody-chain
  operation.
- Treat parent-child ancestry as registry truth, not audio truth.
- Verify one active audio event first, then expand the chain through the
  registry.

