# Tainted — Design Brief & Aesthetics Specification (Part C)

## 1. Visual Identity & Philosophical Premise
Tainted is a forensic audit instrument, not a SaaS dashboard. The interface evokes an archival case dossier, print ledger, and precision investigative workspace.

### Core Visual Principles
- **Paper & Ink**: The interface exists on a tactile, warm unbleached paper surface with high-contrast, near-black carbon ink.
- **Three Signal Inks Only**: Color is strictly functional and scarce. Only three signal inks are permitted for state signaling:
  1. `taint` (ochre / cadmium red-orange) - indicates compromised or tainted causal chain.
  2. `reaffirm` (deep viridian / forest green) - indicates proven independent support.
  3. `suspect` (amber / raw sienna) - indicates degraded trust or calibration fault under investigation.
  All signal ink color values are read dynamically from the registry tokens, never hardcoded in UI code.
- **Typography**:
  - **Display / Headers**: Editorial Serif (`Playfair Display`, `Newsreader`, or `Cinzel` / `Merriweather`).
  - **Identities, Queries, Timestamps, Graph Entities**: Monospace (`JetBrains Mono`, `IBM Plex Mono`).
  - **Body & Data**: Restrained Grotesque (`Inter`, `Plus Jakarta Sans`, or `Geist`).
- **Layout & Structure**:
  - Asymmetric editorial grid.
  - Hairline rules (`1px` solid, low-opacity ink borders).
  - Strict absence of elevation: **Zero box-shadows, zero backdrop-filters/blur**.
  - Graph canvas occupies ~60% width with a chronological running forensic ledger column beside it and a live query audit log column.
- **Motion & Interaction**:
  - Physical, measured transitions: linear or precise ease-out transitions (`cubic-bezier(0.16, 1, 0.3, 1)`).
  - **Strictly no spring easing, bouncy physics, or celebration confetti**.
- **Evidence Stamps**:
  - Forensic rubber stamps (HOLD, REAFFIRMED, SUSPECT, ESCALATED) carrying real state, angled at subtle physical stamps with bordered borders and mono timestamps.

## 2. Banned List (Zero Tolerance)
The following elements are strictly forbidden in Part C:
1. **NO purple-to-blue / neon gradients**.
2. **NO glassmorphism / frosted glass / backdrop-blur**.
3. **NO centred hero layouts with two pill buttons**.
4. **NO three-up icon feature cards**.
5. **NO rounded-xl / rounded-2xl / pill-shaped cards everywhere** (use sharp or crisp 2px hairline radius).
6. **NO emoji used as UI icons**.
7. **NO generic SaaS stat tiles with sparklines or random percentage badges**.
8. **NO default component-library look** (no unstyled Bootstrap, Material, or plain Tailwind pre-sets).
9. **NO placeholder copy, no lorem ipsum, no fake numbers**.

## 3. Design Tokens (Paper & Ink Palette)
Tokens served dynamically via the Registry API and consumed as CSS custom properties:
- `--bg-paper`: `#F7F4EC` (Warm archival paper base)
- `--bg-paper-elevated`: `#EFECE3` (Slightly deeper paper for dossier panels)
- `--bg-paper-sunken`: `#E6E2D6` (Recessed ledger and query log)
- `--ink-primary`: `#181716` (Near-black carbon ink)
- `--ink-secondary`: `#4D4A46` (Diluted charcoal ink for secondary records)
- `--ink-muted`: `#7E7A74` (Faded stamp ink for metadata and captions)
- `--ink-border`: `#D1CDBF` (Hairline rule tint)
- `--ink-border-subtle`: `#E2DED2` (Subtle boundary line)

### Signal Inks (Registry Bound)
- `--signal-taint`: `#C23B22` (Terracotta / cadmium red-orange)
- `--signal-reaffirm`: `#1B5E20` (Deep viridian / archival green)
- `--signal-suspect`: `#B26A00` (Raw sienna / burnt amber)
- `--signal-neutral`: `#5E5852` (Dormant slate)
