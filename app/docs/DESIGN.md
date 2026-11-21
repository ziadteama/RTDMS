# Sahi design system

Read at a glance, in a car, often at night. One token system in [`src/theme/`](../src/theme/);
screens use components, components use tokens. No hex value, font size or spacing number appears
in a screen file (check: the grep in [VALIDATION.md](VALIDATION.md)).

## Color

Fixed light/dark pairs, not Material You dynamic colors: the theme is an in-app setting (dark by
default, for night driving), alert colors must mean the same on every phone, and Reanimated needs
static colors for the state-indicator cross-fade. Dynamic color would tint the UI with the
wallpaper: decorative color, which is out.

### Neutral palette

| Token | Dark | Light | Use |
|---|---|---|---|
| `background` | `#0B0D0F` | `#F5F6F7` | screen |
| `surface` | `#14171A` | `#FFFFFF` | grouped list, live view frame |
| `surfaceRaised` | `#1C2024` | `#ECEEF0` | pressed row, secondary button, banner |
| `separator` | `#2A2F35` | `#D5DADF` | hairlines between rows |
| `text` | `#F1F3F5` | `#0E1114` | primary text |
| `textSecondary` | `#A5ADB5` | `#4D555D` | labels, values |
| `textTertiary` | `#6F7881` | `#79828B` | hints, inactive tab |
| `action` / `onAction` | `#F1F3F5` / `#0B0D0F` | `#0E1114` / `#FFFFFF` | primary button: inverted neutral, no brand hue |
| `unknown` | `#6F7881` | `#79828B` | "no data / not connected" is a state too |

### Alert scale: fusion's `AlertPattern` → color

| `AlertPattern` | Report's alert ladder | Dark | Light | Text on it |
|---|---|---|---|---|
| `none` | normal, no buzzer | `#3FB97A` green | `#1C8A52` | dark / white |
| `short_beep` | short distraction, mild gaze deviation | `#E3C14B` amber | `#8C6F00` | dark / white |
| `repeated` | long eye closure, repeated drowsiness | `#F08A3C` orange | `#B4560C` | dark / white |
| `continuous` | phone use, severe distraction | `#EF5148` red | `#C42B23` | white |
| `max` | behavioural + physiological risk | `#FF2E3A` bright red, pulses | `#B0001A` | white |

The same scale is reused, with the same meaning, for: score bands (≥ 80 green, ≥ 60 amber,
below red), HR signal quality (good / degraded / bad), detected phone use, model errors on the Pi
tab, the destructive button, and the SOS screen (`max`). Nothing else is colored.

## Type

System font (Roboto / SF): the platform's own, readable, every weight present. Numbers use
tabular figures so values do not jitter at 5 Hz. Sizes scale with the system font size.

| Token | Size / line | Weight | Use |
|---|---|---|---|
| `state` | 44 / 52 | 800 | driver state ("Drowsy") |
| `countdown` | 120 / 132 | 800, tabular | SOS countdown |
| `title` | 28 / 34 | 700 | SOS, calibration step |
| `metric` | 30 / 36 | 700, tabular | live values |
| `headline` | 20 / 26 | 600 | alert level, large buttons |
| `metricSmall` | 20 / 26 | 600, tabular | trip score, speed |
| `body` | 17 / 24 | 400 | rows, text |
| `label` | 15 / 20 | 600 | section titles, buttons |
| `caption` | 13 / 18 | 400 | units, hints |

## Spacing, radius, touch

- Spacing (4-pt grid): `xxs 2 · xs 4 · sm 8 · md 12 · lg 16 · xl 24 · xxl 32 · xxxl 48`.
  Row gap < group gap (`xl`) < section gap. Screen padding `lg`.
- Radius: `sm 8 · md 12 · lg 20 · full`; continuous corners.
- Touch targets: `min 48` dp (every control), `large 64` (in-car buttons, hold-to-SOS),
  `huge 96` ("I'm OK").

## Motion (`theme/tokens.ts` → `motion`)

Only where it carries meaning; everything respects the system "reduce motion" setting
(`useReducedMotion`). All of it runs on the UI thread (Reanimated 4 CSS transitions / worklets).

| Where | What | Spec | Reduce motion |
|---|---|---|---|
| State indicator | background color cross-fade on a state change | 250 ms, ease-out `cubicBezier(0.23, 1, 0.32, 1)` | kept (color explains the change) |
| State indicator, `max` only | opacity pulse 1 → 0.72 | 700 ms, alternate, infinite | off |
| Buttons | press scale 0.97 on press-in | 120 ms ease-out | no scale; dim to 0.7 |
| List rows | background highlight while pressed | instant | same |
| Hold-to-SOS | fill grows while held, snaps back on early release | linear 2 s (time passing); release 150 ms ease-out | same (it is information) |
| SOS / calibration | time-remaining bar | linear, full duration | same (information) |
| SOS | haptic tick each second (heavier in the last 10 s) | — | same |
| Screens | native stack push; SOS is a fade-in full-screen modal; tabs switch with no animation | platform defaults | platform handles it |

No entrance animations, no bounce, no staggered lists, no animated tab switches.

## Icons

One set: SF Symbols on iOS and Material Symbols on Android/web through `expo-symbols`
(`src/components/icon.tsx`, bundled font, works offline). Tabs: `videocam`, `route`, `memory`,
`settings`. No emoji anywhere.

## Native controls

Switches, sliders and pickers are `@expo/ui` (Jetpack Compose on Android). Each sits in a `Host`
that gets the app's theme (not the OS one), the text direction, and a neutral seed color so
Material 3 does not tint them purple. Tabs are `NativeTabs` (the Material 3 navigation bar);
headers are native stack headers. Confirmations for irreversible actions (delete all data,
shut down the Pi) use the native alert dialog.

## Layout rules

- Grouped lists (`Section` + `Row`): one surface per group, hairline separators, no card per row,
  no borders.
- Live tab, top to bottom: banners → state indicator (what) → live view → eyes → heart → phone →
  hold-to-SOS. Above ~10 km/h (unlock below 7, hysteresis) only the state indicator, the speed
  and hold-to-SOS remain: the driving lock.
- English only (user decision 2026-11-21): no RTL, no locale switch.

## Banned (from the brief and `expo-design-system` → native slop)

Purple / blue gradients · glassmorphism · emoji as icons · hero cards · filler stats · lorem
ipsum · generic dashboard tiles · everything-centered layouts · bouncing or entrance animations ·
marketing copy · a card per row · 1 px borders everywhere · hand-rolled headers · floating pill
tab bars · decorative color. Labels are short and plain.

## App icon and splash

An open eye with a green pupil (the `none` color: awake, all good) on the dark background.
Source: [`assets/images/icon-mark.svg`](../assets/images/icon-mark.svg); every PNG is rendered
from it by `node scripts/render-icons.mjs` (adaptive foreground inside the 66 % safe zone,
monochrome layer for themed icons, splash, favicon).

## Components added in the UX redesign

The UX redesign introduces five component patterns to support the permission, status, feedback,
countdown, and warning flows. Each pattern is constructed strictly from existing design tokens; no
new hex values, type sizes, or arbitrary dimensions are introduced.

### 1. Status pill

An always-visible instrument indicator displaying system arming and Pi connectivity. Sits in screen
headers or navigation bars, and functions as an interactive touchpoint for system diagnostics.

- **Structure & Container**:
  - Background: `alert.none` (Armed), `alert.short_beep` (Not armed: speed/GPS), `surfaceRaised` (Paused or Pi offline).
  - Corner radius: `radius.sm` (8 dp) for structured instrument-panel feel (never an over-rounded pill).
  - Padding: `paddingHorizontal: spacing.md` (12 dp), `paddingVertical: spacing.xs` (4 dp).
  - Interactive touch bounds: `minHeight: touch.min` (48 dp) via `hitSlop: 12` to ensure accessibility compliance.
- **Typography & Content**:
  - Text label: `label` (15/20, weight 600).
  - Text color: `onAlert.none` (Armed), `onAlert.short_beep` (Not armed), `textSecondary` (Paused), `unknown` (Pi offline).
  - Dot indicator: `size.dot` (10 dp) in matching text color.
- **Reduce Motion**:
  - Color transitions between states use `motion.base` (250 ms, cubic-bezier ease-out).
  - No pulse animations or scaling transforms under any state.

### 2. Checklist row

A specialized row component for pre-flight permissions and OEM background battery protection.
Follows the grouped list convention (`Section` + `Row`).

- **Structure & Container**:
  - Container surface: `surface` (`#14171A` dark / `#FFFFFF` light) inside a grouped `Section`.
  - Row height: `minHeight: touch.min + spacing.sm` (56 dp).
  - Padding: `paddingHorizontal: spacing.lg` (16 dp), `paddingVertical: spacing.md` (12 dp), column gap `spacing.md` (12 dp).
  - Hairline separator: height `StyleSheet.hairlineWidth`, color `separator` (`#2A2F35` dark / `#D5DADF` light), offset `marginStart: spacing.lg`.
- **Typography & Labels**:
  - Permission / Feature label: `body` (17/24, weight 400) in `text`.
  - One-line plain reason: `caption` (13/18, weight 400) in `textSecondary`.
- **Status & Actions**:
  - Granted status: `label` (15/20, weight 600) in `alert.none`.
  - Needed / Blocked status: `Button` variant `secondary` (background `surfaceRaised`, text `text`), `minHeight: touch.min` (48 dp), `radius.md` (12 dp).
- **Reduce Motion**:
  - Instant background highlight on press (`surfaceRaised`); no press-scale spring (`transform: [{ scale: 1 }]`, dim to `0.7` opacity).

### 3. Feedback chip

A low-profile feedback trigger attached to alert banners, incident review screens, and the SOS
countdown to record false positives locally.

- **Structure & Container**:
  - Background: `surfaceRaised` (`#1C2024` dark / `#ECEEF0` light).
  - Corner radius: `radius.sm` (8 dp).
  - Padding: `paddingHorizontal: spacing.md` (12 dp), `paddingVertical: spacing.sm` (8 dp).
  - Touch target: enforced `minHeight: touch.min` (48 dp) and `hitSlop: 8`.
- **Typography & Content**:
  - Text: `label` (15/20, weight 600) in `text` (idle) or `onAction` (selected).
  - Leading icon: size 18 dp in `textSecondary`.
- **Selection State**:
  - Selected / Pressed: background switches to `action`, text switches to `onAction`.
- **Reduce Motion**:
  - Press feedback replaces 3% scale transform with a discrete opacity dim to `0.7` over `motion.fast` (120 ms).

### 4. Countdown variants (Stage 1 vs Stage 2)

Two distinct emergency countdown surfaces separating initial driver cancellation from emergency dispatch.

#### Stage 1: Crash & SOS Countdown
- **Canvas & Background**:
  - Full-screen modal background: `alert.max` (`#FF2E3A` dark / `#B0001A` light).
  - Primary text and icon color: `onAlert.max` (`#FFFFFF`).
- **Typography**:
  - Title: `title` (28/34, weight 700).
  - Subtitle / prompt: `headline` (20/26, weight 600).
  - Numeric timer: `countdown` (120/132, weight 800, tabular figures).
- **Progress Bar**:
  - Height 10 dp, track color `rgba(255, 255, 255, 0.25)`, fill color `onAlert.max` (`#FFFFFF`).
- **Actions**:
  - "I'm OK" primary dismissal button: `Button` variant `primary`, size `xl` (`minHeight: touch.huge` 96 dp), radius `radius.md` (12 dp), background `action`, text `onAction`.
  - "False alarm" chip: `FeedbackChip`, `touch.min` (48 dp), background `surfaceRaised`.
  - "Send now" secondary button: `Button` variant `ghost`, `touch.min` (48 dp).
- **Reduce Motion**:
  - Progress bar advances in 1-second discrete steps rather than fluid linear interpolation.
  - Background pulse on `alert.max` is disabled.

#### Stage 2: Emergency Call Staging ("Calling 123 in 15 s")
- **Canvas & Background**:
  - Screen background: neutral `background` (`#0B0D0F` dark / `#F5F6F7` light).
  - Card container: `surface` (`#14171A` dark / `#FFFFFF` light), radius `radius.md` (12 dp), padding `spacing.lg` (16 dp).
- **Typography**:
  - Stage header: `headline` (20/26, weight 600) in `text`.
  - Numeric timer: `state` (44/52, weight 800, tabular figures) in `alert.max`.
  - Motion status notice: `caption` (13/18, weight 400) in `textSecondary`.
- **Actions**:
  - "Cancel call" primary button: `Button` variant `destructive`, size `lg` (`minHeight: touch.large` 64 dp), radius `radius.md` (12 dp), background `alert.continuous`, text `onAlert.continuous`.
  - "Call now" manual trigger: `Button` variant `secondary`, `touch.min` (48 dp).
- **Reduce Motion**:
  - Timer decrements numerically with zero layout transition; cancel button uses opacity dim on press.

### 5. Warning banner variant (Camera covered / Calibration lost)

A high-visibility, non-dismissible warning banner positioned on the Live screen when camera
tracking is occluded or lost.

- **Structure & Container**:
  - Background: `surfaceRaised` (`#1C2024` dark / `#ECEEF0` light).
  - Corner radius: `radius.md` (12 dp), continuous curve.
  - Padding: `padding: spacing.md` (12 dp), gap `spacing.md` (12 dp).
  - Leading accent bar: width 4 dp, vertical alignment full stretch, color `alert.continuous` (Camera covered / danger) or `alert.short_beep` (Calibration lost / warning).
- **Typography & Content**:
  - Icon: size 22 dp in matching accent color.
  - Warning title: `label` (15/20, weight 600) in `text`.
  - Descriptive guidance: `caption` (13/18, weight 400) in `textSecondary`.
  - Recovery action: inline `Button` variant `secondary`, `minHeight: touch.min` (48 dp), `radius.sm` (8 dp).
- **Reduce Motion**:
  - Static display; no pulsing or flashing accent lines.

