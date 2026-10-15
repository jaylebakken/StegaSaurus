# Evidence Language

Saurus keeps technical evidence, registry context, and conclusions separate.
These phrases are product contracts for desktop, API, review, and reports.
Production legal/policy readiness is recorded separately in
`src/saurus_pilot/legal_policy.py`; it requires counsel approval across
evidence language, discovery source policy, client alerts/notices, opt-out and
corrections, and retention/deletion before the production gate can pass.

| Evidence class | Supported wording | Unsupported wording |
| --- | --- | --- |
| System fact | "Export event `E` was created by Saurus at time `T`." | "The recipient received or opened the file." |
| User label | "Event `E` has the user label `Mixer preview`." | "The mixer performed this action." |
| Song candidate | "Public audio is a candidate match for registered song `S`." | "This is certainly the client's song." |
| Watermark match | "Audio evidence matched registered export event `E` under profile `P`." | "The named recipient leaked the song." |
| Rejected claim | "The selected export claim did not match the available evidence." | "The audio is definitely unwatermarked." |
| Abstention | "Saurus could not reach an accepted result from this audio." | "No registered copy is present." |
| Lineage | "Event `E` is recorded as a child of event `P` in the registry." | "The audio independently proves every ancestor event." |

## Rules

- Always display the evidence class, profile/version, and accepted, rejected, or
  abstained outcome.
- Recipient names, notes, and parent links are registry context, not audio proof.
- A crawler result stops at `song candidate` until a separate authorized
  attribution workflow runs.
- A short or transformed public preview may be useful for song discovery while
  being unusable for watermark verification. Report `song candidate only`.
- External action requires human review and the policy defined for that client;
  no crawler or decoder result triggers an accusation automatically.
