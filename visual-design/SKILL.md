---
name: visual-design
description: Visual design rules for clean, readable, low-fatigue interfaces. Use when creating or reviewing any UI to enforce restraint in typography weight, element density, shadows, decorative indicators, color saturation, and motion.
metadata:
  short-description: Restraint-focused visual design rules
---

Apply these principles to every UI decision — layout, typography, color, components, motion, and spacing.

## Typography

- **No undersized text.** Small labels and captions must stay legible; never let secondary text drop below a comfortable reading size.
- **No heavyweight type.** Especially for headings: prefer medium or semibold over bold/black. Use size and spacing for hierarchy, not sheer font-weight.

## Layout & Components

- **Minimize cards.** Prefer flat sections, subtle dividers, or whitespace separation. Cards are reserved for genuinely self-contained, interactive, or modal content — not for every content block.
- **No card-in-card.** Never nest a card inside another card. If grouping is needed, use padding, borders, or background tonal shifts on the outer container.
- **Reduce shadow usage.** Default to no shadow. If depth is needed, use a single, very subtle shadow at most. Never stack multiple shadow layers.

## Website Restoration

- **Inspect with CDP before recreating.** When restoring or recreating an existing website, use Chrome DevTools Protocol (CDP) to gather detailed page content and analyze the site's JavaScript and CSS before making design or implementation decisions.

## Visual Indicators

- **Avoid status dots.** Use text labels, icons, or subtle background tints instead of colored dots to convey state.

## Color

- **Lift contrast on white.** On white or near-white backgrounds, avoid very light grays (e.g., #f5f5f5, #e8e8e8). Use grays with enough contrast to be clearly visible without squinting.
- **Muted saturation by default.** Keep colors subdued unless the design explicitly calls for vibrant accents. Favor desaturated or toned-down palettes for a calm, professional feel.

## Motion

- **Purpose-driven only.** Every animation must serve a clear functional goal — guiding attention, confirming action, or smoothing state transitions. If an effect exists purely for visual flair, remove it.
- **No gratuitous hover lift.** Do not use hover-triggered translateY/shadow/scale effects on cards, buttons, or list items unless the elevation is genuinely needed to communicate interactivity that is otherwise ambiguous.
- **Restrained duration and distance.** Keep transitions short (150–250ms) and movements small. Large bouncy or elastic easing feels noisy; prefer linear or ease-out.

