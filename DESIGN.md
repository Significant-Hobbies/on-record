---
name: High Signal Podcasts
description: An editorial evidence ledger for attributable podcast claims.
colors:
  ink: "#181713"
  muted-ink: "#625e55"
  paper: "#f1eadb"
  paper-light: "#f8f4ea"
  paper-deep: "#e5dac5"
  rule: "#cfc2aa"
  evidence-rust: "#8d301f"
  evidence-rust-dark: "#6d2115"
  archival-green: "#294536"
  brass: "#ad7938"
typography:
  display:
    fontFamily: "Iowan Old Style, Baskerville, Palatino Linotype, Palatino, serif"
    fontSize: "clamp(3rem, 6.4vw, 6.6rem)"
    fontWeight: 500
    lineHeight: 0.94
    letterSpacing: "-0.025em"
  body:
    fontFamily: "Iowan Old Style, Baskerville, Palatino Linotype, Palatino, serif"
    fontSize: "1.04rem"
    fontWeight: 400
    lineHeight: 1.58
  label:
    fontFamily: "Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"
    fontSize: "0.7rem"
    fontWeight: 750
    lineHeight: 1.58
    letterSpacing: "0.14em"
rounded:
  square: "0"
  pill: "999px"
spacing:
  xs: "0.45rem"
  sm: "0.7rem"
  md: "1.2rem"
  lg: "2rem"
  section: "clamp(3rem, 7vw, 6rem)"
components:
  button-primary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper-light}"
    rounded: "{rounded.square}"
    padding: "0.78rem 1rem"
  evidence-card:
    backgroundColor: "{colors.paper-light}"
    textColor: "{colors.ink}"
    rounded: "{rounded.square}"
    padding: "1.3rem"
---

# Design System: High Signal Podcasts

## Overview

**Creative North Star: “The Evidence Ledger”**

The interface should feel like a carefully annotated research folio: quiet paper,
precise rules, numbered records, and a visible trail back to the source. Editorial
warmth earns attention, while explicit speaker, quote, date, episode, publisher,
and source fields earn trust.

**Key Characteristics:** claim-first hierarchy; archival paper texture; restrained
rust, green, and brass accents; square evidence containers; compact folio labels;
real proof before explanation.

## Colors

Warm paper neutrals carry the reading surface. Ink owns hierarchy, evidence rust
owns actions and keyboard focus, archival green marks status and labels, and brass
appears only as a material accent.

**The Evidence Color Rule.** Accent color marks action, provenance, or status. It
must not become decorative confetti.

## Typography

**Display and Body:** Iowan Old Style with Baskerville and Palatino fallbacks.

**Labels and Controls:** Inter with the native UI sans-serif stack.

Large serif headlines make the page feel published rather than generated. Compact,
uppercase sans-serif labels distinguish metadata and controls from quoted speech.
Body copy stays near 65–75 characters per line when the layout permits.

## Layout

The content container is 76rem wide with a 1rem minimum gutter. The homepage uses
an asymmetric evidence-led hero, four-column corpus accounting, and three-column
proof cards. At 880px the hero and methodology stack; at 620px actions, proof,
statistics, and people become single-column. Every interactive target remains at
least 44px tall.

## Elevation & Depth

Most surfaces are flat and separated by one-pixel ink or paper rules. The featured
evidence card alone may use the ambient `0 24px 70px rgba(53, 42, 24, 0.12)` shadow
and a translucent brass tape mark to suggest a retained source document.

## Shapes

Evidence cards, inputs, and buttons are square. Rounded pills are reserved for
compact navigation state; they are not a general card language.

## Components

### Evidence receipts

Show real quoted words with the speaker, date or timestamp, episode, publisher, and
source action. Missing values must use honest fallback language, never invented
specifics.

### Buttons and links

Primary buttons use ink on light paper; secondary buttons remain transparent with
an ink border. Hover lifts by two pixels. Keyboard focus uses a three-pixel opaque
evidence-rust outline with a three-pixel offset.

### Cards

Cards use square corners, paper-toned backgrounds, a single rule border, and tight
folio metadata. Proof-card quotes may clamp visually, but their source actions must
remain available.

## Do's and Don'ts

- **Do** put a real source-backed claim near the first product promise.
- **Do** use labels such as Speaker, When, Episode, and Publisher consistently.
- **Do** preserve generous editorial whitespace and clear reading order.
- **Don't** turn the site into a podcast player, transcript dump, or generic SaaS dashboard.
- **Don't** publish an interpretation without its verbatim evidence trail.
- **Don't** use rounded cards, gradients, or bright accent fields as decoration.
