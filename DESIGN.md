---
name: Finovaunt
description: A restrained visual system for an AWS FinOps workspace.
colors:
  primary: "#532d77"
  primary-hover: "#40205f"
  selected: "#eae1f4"
  canvas: "#f2f1f5"
  surface: "#ffffff"
  rail: "#eae8f0"
  ink: "#222133"
  muted: "#555269"
  line: "#dcd9e5"
typography:
  headline:
    fontFamily: '"Atkinson Hyperlegible Next", system-ui, -apple-system, "Segoe UI", sans-serif'
    fontWeight: 650
    lineHeight: 1.12
    letterSpacing: "-0.04em"
  title:
    fontSize: "18px"
  body:
    fontSize: "16px"
  label:
    fontSize: "14px"
    fontWeight: 650
rounded:
  control: "7px"
  mark: "8px"
  panel: "10px"
spacing:
  small: "8px"
  medium: "16px"
  large: "24px"
  section: "28px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.surface}"
    rounded: "{rounded.control}"
    padding: "9px 13px"
  button-outline:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "9px 13px"
  input:
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "12px 13px"
  nav-current:
    backgroundColor: "{colors.selected}"
    rounded: "{rounded.control}"
    padding: "8px 10px"
  evidence-panel:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.panel}"
---

# Design System: Finovaunt

## Overview

Finovaunt uses a quiet palette, clear account scope, and compact evidence displays. Sign-in shares the workspace palette and layered mark.

**Key characteristics**

- Cool neutral surfaces and a plum accent.
- One navigation rail across dashboard and administration.
- Compact, aligned data with room around the main task.

## Colors

Plum marks primary actions and focus. Lilac marks selections. Use white panels, muted labels, and hairline boundaries.

Sources are [workspace tokens](frontend/src/workspace.css) and the [overview charts](frontend/src/FinovauntOverview.tsx).

## Typography

Use locally hosted Atkinson Hyperlegible Next with a system sans fallback. Page headings scale from 26px to 36px, body copy uses 16px, and data and metadata use 14px and 13px. Set costs and counts in tabular figures.

## Layout

The rail is 204px on desktop, 184px at 1020px, and 60px at 760px. At 760px, the toolbar wraps and sign-in becomes one column. Form inputs use 16px text.

Use independent overview columns at 1050px and wider. Stack the columns at narrower widths. Keep overview panels visible and tables in local scroll containers.

## Elevation & Depth

Use tonal surfaces and full, one-pixel borders. Use dividers for collapsed supporting evidence.

## Shapes

Use 7px corners for controls, 8px for the brand mark, and 10px for panels. Avatars are circular.

## Components

- Mark the current destination with a tint and `aria-current="page"`.
- Use filled plum for the primary action and an outline for secondary actions.
- Label fields above their controls. Keep requirements and feedback nearby.
- Pair charts with units and evidence panels with collection status.
- Give icon-only controls accessible names. Preserve keyboard focus and reduced-motion support.

## Do's and Don'ts

- Keep the current destination visible across dashboard and admin views.
- Align numeric values and give tables enough room to scroll locally.
- Keep state labels visible wherever color communicates meaning.
- Avoid decorative badges, gradients, and heavy shadows on workspace controls.
