# Saurus Style Guide

Saurus is an audio workspace for registered copies and evidence-based verification.
Its visual language is orderly, direct, and attentive: neutral work surfaces,
forest-green identity, and yellow tape at the point where attention is useful.

Open [`src/saurus_style/index.html`](../src/saurus_style/index.html) for the visual
specimen. It works directly from disk, without a server or external assets.

## Shared Source

| Resource | Purpose |
| --- | --- |
| `src/saurus_style/tokens.json` | Editable color, typography, spacing, and geometry values |
| `src/saurus_style/tokens.css` | Generated, namespaced CSS custom properties |
| `src/saurus_style/theme.css` | Opt-in web components, states, and focus treatment |
| `src/saurus_style/assets/` | Waveform stegosaurus, compact marks, and repeating tape tile |
| `src/saurus_app/theme.py` | Native Tk adapter for the same tokens |

Change the JSON, then run `python -m saurus_style.build`. Commit the generated
CSS and assets with the source. The desktop reads JSON directly; websites import
CSS. Neither runtime requires a network request, external font, or asset service.

## Identity

Use **Saurus** in running text, app titles, and navigation. Use **Stegosaurus** for
the underlying Python/research project. The primary logo is a stegosaurus drawn
as a continuous audio waveform: the creature and the signal should read as one
idea. Pair it with a typeset Saurus wordmark; do not stretch, rotate, recolor, or
separate the waveform from the animal.

- `waveform-stegosaurus.svg`: white line artwork on its deep navy field.
- `waveform-stegosaurus-line.svg`: dark monochrome line artwork for light surfaces.
- Use the primary logo at least 160px wide. At smaller sizes, use the compact
  three-bar mark in `mark.svg` or `mark-on-dark.svg` as a utility symbol.
- Keep clear space around the primary logo equal to the height of one waveform peak.
- Do not add effects, place type over the dinosaur, or crop through its head, tail,
  plates, feet, or waveform.
- Ambient waveform fields may use several thin, related signal traces. Keep them
  low contrast, behind content, and faded at the viewport edges; one green or
  yellow trace may carry emphasis without turning the pattern into decoration.
- Tape belongs in a 6-8px strip or a short attention rule. Never place text over
  stripes, turn the full screen yellow, or animate tape.

## Color Roles

| Role | Value | Use |
| --- | --- | --- |
| Ink | `#1B2420` | Text, app header, dark bands |
| Canvas / surface | `#F3F5F4` / `#FFFFFF` | Workspace / active work surface |
| Subtle / border | `#E9EEEB` / `#B6C1BA` | Quiet grouping / field boundaries |
| Signal navy | `#06283A` | Primary logo field and branded application headers |
| Muted text | `#536159` | Secondary labels and file-format hints |
| Tape | `#F4D03F` | Primary action, active step, attention accent |
| Forest | `#216247` | Identity, focus, accepted results |
| Copper | `#B86045` | Small brand accent, never a verdict |
| Success | `#216247` on `#E5F2E9` | Explicitly accepted verification or completed save |
| Attention | `#674C00` on `#FFF7CE` | Private registry guidance or no accepted match |
| Error | `#A32F36` on `#FCECEE` | Invalid input or failed operation |

Yellow is a direction cue, not a success color. Use dark text on yellow, never
white. Status text must say what happened; color alone cannot communicate a
verdict. Body text pairings meet WCAG AA's 4.5:1 contrast threshold, checked in
the application suite. This is a palette check, not an accessibility certification.

## Typography And Geometry

Use Segoe UI with a system sans-serif fallback. Use Consolas/system monospace
only for handles, paths in diagnostics, and code. No font downloads are required.
Sizes are fixed; do not scale text with viewport width or use negative tracking.

| Role | Web pixels | Native points |
| --- | --- | --- |
| Caption | 12 | 9 |
| Small / field label | 14 | 10.5 |
| Body | 16 | 12 |
| Section heading | 20 | 15 |
| View title / brand | 28 | 21 |
| Guide display | 40 | 30 |

Tk rounds points to the nearest whole number and respects system DPI scaling.
Use regular body text and semibold/bold labels. Keep headings compact inside tools.
Reserve display size for editorial pages, never a form panel or dialog.

The spacing scale is **4, 8, 12, 16, 24, 32, 48px**. Use 8px between a label and
its field, 16px between related controls, and 24-32px between workflow sections.
Web inputs and buttons are at least 44px tall. Native controls use font-aware
padding. Corners are 4px for controls and at most 8px for framed items. Native
Tk controls may be square. Full-width bands and dividers define page sections;
avoid stacks of decorative cards, nested cards, and heavy shadows.

## Workflow Components

1. **Header:** dark band, readable Saurus wordmark, concise surface name, narrow
   tape strip beneath. The logo must not compete with an action.
2. **Modes:** adjacent Encode and Decode tabs, a persistent selected treatment,
   keyboard focus, and no color-only distinction.
3. **Steps:** stable numbered squares, a short action heading, and permanently
   visible field labels. Placeholder text never stands in for a label or value.
4. **Files:** editable path and visible Choose/Browse action. File dialogs are
   always available; advertise drag-and-drop only when supported at runtime.
5. **Registry:** project and recipient are required; notes are explicitly optional.
   Keep saved-file guidance beside the output choices.
6. **Primary action:** one yellow command per active mode. Disable until required
   values are present, and say what is missing in the nearby status line.
7. **Busy:** lock the submitted fields, show progress and an explicit verb, and
   preserve the current mode until work finishes. Do not invent percent complete.
8. **Results:** lead with the outcome and the saved paths or matched record.
   Put technical diagnostics after the result, not in the action label.

Icons supplement labels for ambiguous actions. Use a consistent icon library
in a product that already has one; otherwise native labeled commands are enough.
Keep familiar icon-only tools focusable and give each an accessible name and tooltip.

## Voice And Evidence

Use a calm action or observation: **Choose a WAV**, **Add registry details**,
**Encode file**, **Copy created**, **Registry claim verified**, **No accepted match**.
Avoid jokes in errors, intimidating lab terms in primary controls, and promotional
claims in results. State the next useful action when an input is missing.

The current Decode mode verifies one retained registry claim. It does not discover
an unknown identity from an arbitrary file. An abstention is not proof that the
audio is unmarked or that another recipient is responsible. Keep that distinction
in result wording. Statistical watermark detection is a separate research path;
do not label it as attribution. Do not claim codec, DSP, crop, recording, or
perceptual robustness without naming the measured evaluation.

The WAV is the shareable output; the JSON is private retained verification state.
Say that at the save step. This local prototype is not an authenticated registry
service or production key-management system.

## Implementation

Web surfaces import `theme.css` and place `class="saurus"` on their root. Components
are opt-in (`saurus-button`, `saurus-field`, `saurus-note`, etc.), so importing the
tokens does not change unrelated layouts. Use semantic HTML, visible labels,
native keyboard behavior, `aria-invalid` on invalid fields, and live status regions.

The existing marketing site can adopt shared tokens without changing its editorial
layout. The desktop uses native Tk widgets, the shared PNG mark, token-derived
styles, and the same attention/success/error roles. A native adapter is intentional:
Tk does not consume browser CSS.

The site now imports the shared palette and mark. When serving or copying static
files, keep `saurus_site/` and `saurus_style/` beside each other; the site references
`../saurus_style/`. Opening either HTML entry point directly also works.

For narrow windows, wrap body/status text, let path fields scroll horizontally,
and scroll the form while keeping the main action reachable. Preserve field values
when switching modes. At larger sizes, add whitespace rather than oversized text.
Honor reduced motion on the web. No hover animation or motion is needed on desktop.

Before shipping a surface, inspect its empty, filled, focused, disabled, busy,
success, abstention, and error states at the smallest supported size and normal
size. Check real long filenames, keyboard navigation, visible focus, image loading,
and display scaling. Validate application behavior with the current application
suite, not archived research regressions.
