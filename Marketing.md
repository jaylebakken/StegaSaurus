# Stegosaurus Marketing Overview

## Positioning

Stegosaurus is an audio watermarking and attribution system for controlled music
distribution workflows. The product direction is aimed at a practical problem:
when a protected audio file leaks, a rightsholder wants to know which authorized
copy most likely left the trusted chain.

Rather than presenting the watermark as public metadata or relying only on
platform-side takedown matching, Stegosaurus binds each exported copy to an
opaque registry handle. The audio carries recoverable attribution evidence, and
the registry stores the business context: who received the copy, when it was
issued, which source song it came from, and how the export relates to earlier
parent or child releases.

The current prototype is not a finished forensic product. Its clearest market
fit is a future production system for private, pre-release, and high-value music
distribution where source songs and authorized exports are known in advance.

## Market Context

Existing music-protection workflows usually lean on a few separate tools:

| Category | Typical use | Limitation Stegosaurus targets |
| --- | --- | --- |
| Audio fingerprinting | Find public copies of known tracks after release. | Identifies the song, not the authorized recipient copy. |
| Metadata tagging | Attach visible or file-level ownership data. | Metadata can be stripped, rewritten, or separated from audio. |
| Forensic watermarking | Trace authorized copies after leakage. | Often opaque, vendor-bound, and hard to adapt to custom registry workflows. |
| Manual leak investigation | Compare files, dates, recipients, and delivery records. | Slow, subjective, and difficult to scale across many exports. |

Stegosaurus is designed to sit between forensic watermarking and rights-management
infrastructure. Its value is not only that audio can carry a signal, but that the
signal points into an authenticated attribution workflow.

## Best Initial Customer

The strongest early market is not every audio owner. It is teams that distribute
sensitive music before public release and already know the universe of possible
recipients.

Good early users include:

- Independent labels sending pre-release masters to collaborators, reviewers,
  playlist contacts, and distributors.
- Producers or managers sharing high-value demos with artists, engineers, or
  A&R teams.
- Sync, licensing, and catalog teams sending watermarked previews to buyers.
- Internal music teams that need controlled review copies across contractors.

These users care less about open-world song identification and more about a
specific question: "This leaked file sounds like our track; which authorized copy
does it match?"

## Product Narrative

Stegosaurus can be described as a private attribution layer for music files:

1. A source song is registered locally or in a future cloud registry.
2. The system creates recipient-specific exports from the clean source.
3. Each export receives a low-level audio watermark tied to an opaque registry
   handle.
4. If a leak appears, the user selects or resolves the likely source song.
5. The tool localizes the suspicious excerpt against the registered song.
6. It verifies candidate export records and ranks the matching recipient.
7. Parent-child lineage is reconstructed from the registry, not from stacked
   watermarks in the audio.

That workflow makes the product easy to explain: Stegosaurus does not merely ask
"is this our song?" It asks "which copy of our song is this?"

## Differentiation

Stegosaurus has several product ideas that could make it distinct if hardened
into a production system:

- **Known-song attribution first.** The workflow assumes the user usually knows
  the suspected track. This avoids pretending to solve global music recognition
  and lets the system spend effort on crop localization and export matching.
- **Registry-backed identity.** The watermark carries a compact opaque handle,
  while sensitive context lives in authenticated registry records.
- **One visible watermark at a time.** Child exports can be regenerated from the
  clean master, while parent-child history is maintained in the registry. This
  reduces the risk of stacked watermarks interfering with each other.
- **Evidence pooling.** Repeated block encoding lets longer songs accumulate
  multiple independent attribution opportunities rather than depending on one
  fragile payload location.
- **Explicit abstention.** The design treats uncertainty as a first-class
  result. A production version should prefer "no accepted match" over a
  confident but weak attribution.
- **Replayable attack evaluation.** Named transformations and entropic recipes
  make robustness testing reproducible rather than anecdotal.

## Deployment Fit

The most natural future deployment is a hybrid local/cloud system:

| Component | Future role |
| --- | --- |
| Local desktop app | Import source audio, create exports, listen to results, and inspect leak matches. |
| Registry service | Store song records, export handles, recipient metadata, parent-child lineage, and audit logs. |
| Key service | Protect watermark secrets outside ordinary user-accessible storage. |
| Verification service | Run heavier recovery workflows, compare candidate exports, and produce signed reports. |
| Integration API | Connect export creation to delivery tools, label CRMs, data rooms, or distributor workflows. |

For smaller teams, a local-first edition could provide immediate value: create
recipient-specific WAV exports, retain a private registry file, and run known-song
verification manually when a leak appears.

For labels and enterprise teams, the larger opportunity is a managed registry:
every watermarked delivery becomes a traceable event in the song lifecycle.

## Pricing And Packaging Ideas

Possible packaging can follow customer maturity:

| Tier | Buyer | Product shape |
| --- | --- | --- |
| Studio | Producers, managers, small labels | Local app, limited registered songs, local registry, manual verification. |
| Label | Indie labels and catalog teams | Shared registry, recipient management, batch exports, audit logs. |
| Enterprise | larger labels, distributors, sync platforms | API access, key-management integration, signed verification reports, policy controls. |
| Evaluation | security or rights teams | Benchmark suite, attack recipes, quality reports, and integration sandbox. |

Pricing should follow protected workflow volume rather than raw audio duration:
registered songs, monthly exports, registry users, verification runs, and audit
retention are more natural value metrics than minutes of audio alone.

## Sales Message

Short version:

> Stegosaurus helps music teams create recipient-specific audio exports and
> identify which authorized copy a leaked excerpt most closely matches.

More complete version:

> Stegosaurus is a private audio attribution layer for high-value music
> distribution. It embeds registry-backed attribution evidence into exported WAV
> files, then uses known-song localization, block-level evidence pooling, and
> retained export records to match leaked excerpts back to authorized recipients.

Careful technical qualifier:

> The current prototype demonstrates the workflow under named local evaluations.
> Production claims about codecs, recorded audio, arbitrary edits, perceptual
> transparency, and adversarial robustness require broader validation.

## Why Now

Music collaboration has become more distributed. Tracks move through more hands
before release: producers, vocalists, engineers, managers, marketing teams,
playlist contacts, distributors, sync buyers, and reviewers. At the same time,
leaks can spread instantly and may come from small cropped excerpts rather than a
full untouched WAV.

This creates demand for a tool that is practical, private, and workflow-aware.
The strongest product wedge is not universal copyright enforcement. It is
controlled distribution: helping teams send audio with accountability before the
track is public.

## Roadmap To Market Readiness

Before Stegosaurus should be positioned as a production forensic watermark, it
needs evidence and infrastructure beyond the current prototype:

1. Validate on a licensed corpus of modern pop, rap, vocal, and dense
   instrumental material.
2. Measure audio quality with objective metrics and blinded listening.
3. Pre-register attack suites for crops, compression, resampling, filtering,
   gain changes, light recorded-proxy transforms, and combined distress.
4. Establish false-positive and false-attribution rates with controls.
5. Build durable registry storage with authentication, audit logs, key
   separation, and access controls.
6. Produce signed verification reports suitable for internal investigation.
7. Compare against named commercial, classical, learned, or fingerprint-based
   baselines on the same corpus and attack matrix.

## Bottom Line

Stegosaurus fits the market as a future attribution and chain-of-custody layer
for controlled audio distribution. Its likely first wedge is pre-release music:
not "find every copy of every song on the internet," but "given this leaked
excerpt from a known track, identify the authorized export it most likely came
from."

That is a focused, valuable problem. It also matches the architecture already
emerging in the prototype: source registration, recipient-specific exports,
known-song localization, export fanout verification, registry-backed lineage,
and explicit uncertainty when the evidence is not strong enough.
