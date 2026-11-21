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
- Arabic: real RTL via `I18nManager.forceRTL` + reload on Android; layouts use `start`/`end`, rows
  mirror, numbers stay Western digits (as on Egyptian dashboards and the Pi's own page).

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
