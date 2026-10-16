# WCAG 2.2 Code-Review Checklist

Use WCAG 2.2 Level AA as the conformance baseline. A and AA success criteria
are obligations; AAA criteria and advisory techniques are not AA requirements.
Cite the normative [WCAG 2.2](https://www.w3.org/TR/WCAG22/) criterion by
number and name. The
[Understanding documents](https://www.w3.org/WAI/WCAG22/Understanding/) are
informative explanations, not additional requirements.

Code review can prove some failures. It cannot prove whole-page conformance.
For every item record **Static**, **Unverified**, or **Not affected**; never
convert “not visible in the diff” into a pass.

## Perceivable

| SC | Static evidence to inspect | Usually needs rendered/manual evidence |
|---|---|---|
| **1.1.1 Non-text Content (A)** | Images, SVGs, icon buttons, canvas, generated content; meaningful alternatives and decorative exclusion | Whether the alternative communicates equivalent purpose in context |
| **1.2.1–1.2.5 Time-based Media (A/AA)** | Captions, transcript/audio-description tracks and player controls referenced by source | Accuracy, synchronization, and completeness of alternatives |
| **1.3.1 Info and Relationships (A)** | Native headings, lists, tables, labels, fieldsets/legends, regions; programmatic relationships | Accessibility-tree output after framework rendering |
| **1.3.2 Meaningful Sequence (A)** | DOM/native order versus CSS reordering, portals, absolute positioning | Reading and focus sequence in the rendered UI |
| **1.3.3 Sensory Characteristics (A)** | Instructions relying only on shape, color, location, orientation, or sound | Whether the whole task supplies another identifier |
| **1.3.4 Orientation (AA)** | Forced portrait/landscape configuration or CSS orientation lock | Whether a stated essential exception applies |
| **1.3.5 Identify Input Purpose (AA)** | Appropriate HTML input purpose/autocomplete tokens for user-data fields | Browser/platform support and resulting autofill behavior |
| **1.4.1 Use of Color (A)** | Status or instructions encoded only by a color token | Rendered states and non-color cues |
| **1.4.2 Audio Control (A)** | Auto-playing audio lasting over three seconds and visible controls | Timing and independent volume/pause operation |
| **1.4.3 Contrast (Minimum) (AA)** | Final known foreground/background tokens and states; calculate ratios | Gradients, images, opacity, compositing, anti-aliasing, unknown themes |
| **1.4.4 Resize Text (AA)** | Fixed clipping, disabled zoom, text-sized containers | Task completion at 200% text resize |
| **1.4.5 Images of Text (AA)** | Text embedded in images where not essential/customizable | Exception applicability |
| **1.4.10 Reflow (AA)** | Fixed widths, `min-width`, overflow, viewport units, two-axis layouts | Reflow at 320 CSS px or equivalent 400% zoom condition |
| **1.4.11 Non-text Contrast (AA)** | Known boundaries, focus indicators, icons, and state colors | Final adjacent colors in every state |
| **1.4.12 Text Spacing (AA)** | Clipping/height rules likely to fail user-overridden spacing | Content loss with WCAG-specified spacing overrides |
| **1.4.13 Content on Hover or Focus (AA)** | Hover/focus popover dismissal, hoverability, persistence logic | Pointer and keyboard behavior/timing |

For SC 1.4.3, normal text needs at least **4.5:1**; large-scale text needs
**3:1**. Large-scale is at least 18 point regular or 14 point bold (about
24 CSS px or 18.66 CSS px bold under CSS's 96 px/in reference). Do not round a
failing ratio up. Incidental, inactive, logo, and other criterion exceptions
must be supported by context, not assumed.

For SC 1.4.11, required visual information for controls and graphical objects
normally needs **3:1** against adjacent colors. Do not demand a visible border
when shape/state is already distinguishable by another conforming visual cue.

## Operable

| SC | Static evidence to inspect | Usually needs rendered/manual evidence |
|---|---|---|
| **2.1.1 Keyboard (A)** | Native controls; keyboard handlers for custom controls; no pointer-only path | Every task with keyboard/switch-equivalent input |
| **2.1.2 No Keyboard Trap (A)** | Modal/editor escape and focus-containment code | Entry, traversal, and documented exit behavior |
| **2.1.4 Character Key Shortcuts (A)** | Single-character shortcuts and disable/remap/focus conditions | Behavior in text entry and speech input |
| **2.2.1 Timing Adjustable (A)** | Timeouts, session warnings, extension controls and exceptions | Actual timing and preservation of data |
| **2.2.2 Pause, Stop, Hide (A)** | Auto-updating/moving content and pause controls | Timing, movement, and control operation |
| **2.3.1 Three Flashes or Below Threshold (A)** | Deliberate flash animation or rapid alternating styles | Flash area/rate analysis from rendered media |
| **2.4.1 Bypass Blocks (A)** | Skip link, landmarks, heading structure, repeated navigation abstraction | Skip target focus and repeated-page behavior |
| **2.4.2 Page Titled (A)** | Route/document title assignment | Title updates and usefulness after navigation |
| **2.4.3 Focus Order (A)** | DOM/native order, positive `tabindex`, portals, focus calls | Logical sequence through every state |
| **2.4.4 Link Purpose (In Context) (A)** | Link text plus programmatic context | Ambiguous repeated links in rendered context |
| **2.4.5 Multiple Ways (AA)** | Navigation, search, sitemap/index mechanisms for page sets | Applicability and route coverage |
| **2.4.6 Headings and Labels (AA)** | Descriptive source labels/headings | Whether they describe rendered purpose/topic |
| **2.4.7 Focus Visible (AA)** | Removed outlines, focus styles, state selectors | Indicator visibility for every keyboard control |
| **2.4.11 Focus Not Obscured (Minimum) (AA)** | Sticky headers/footers, overlays, scroll/focus code | Focused component not entirely hidden in task flow |
| **2.5.1 Pointer Gestures (A)** | Multipoint/path gestures and single-pointer alternative | Full gesture operation on target devices |
| **2.5.2 Pointer Cancellation (A)** | Activation on down-event, cancel/undo logic | Accidental activation behavior |
| **2.5.3 Label in Name (A)** | Visible text included in computed accessible name | Final name computation and speech-input match |
| **2.5.4 Motion Actuation (A)** | Shake/tilt/device-motion actions and UI alternative/disable path | Platform sensor behavior |
| **2.5.7 Dragging Movements (AA)** | Drag-only sorting/sliders/maps and non-drag alternative | Pointer completion without dragging |
| **2.5.8 Target Size (Minimum) (AA)** | CSS/native dimensions and spacing when final units are known | Rendered 24-by-24 CSS-pixel target or spacing/exception |

SC 2.5.8 permits exceptions; do not report every inline link or browser-native
control as failing. Evaluate spacing, equivalent controls, user-agent control,
essential presentation, and legal/technical exceptions from the criterion.

Positive `tabindex` creates an alternate keyboard order and is usually
**WRONG** when it conflicts with meaningful sequence. `tabindex="0"` makes an
element focusable; it does not add button semantics, activation, name, or state.

## Understandable

| SC | Static evidence to inspect | Usually needs rendered/manual evidence |
|---|---|---|
| **3.1.1 Language of Page (A)** | Root `lang` or platform language metadata | Correct language for generated document |
| **3.1.2 Language of Parts (AA)** | Markup for passages whose language changes | Pronunciation with supported assistive tech |
| **3.2.1 On Focus (A)** | Focus handlers causing navigation, submission, or context change | Actual focus behavior |
| **3.2.2 On Input (A)** | Change handlers causing unexpected context change without warning | Task behavior for controls and forms |
| **3.2.3 Consistent Navigation (AA)** | Shared navigation component/order | Consistency across the page set |
| **3.2.4 Consistent Identification (AA)** | Same-function controls and icon/name mappings | Rendered identification across pages |
| **3.2.6 Consistent Help (A)** | Repeated help mechanisms and ordering | Page-set applicability and consistency |
| **3.3.1 Error Identification (A)** | Error state, text, summary, and field association | Errors are detected and described during submission |
| **3.3.2 Labels or Instructions (A)** | Persistent labels, formats, required/group instructions | Sufficiency for completing the task |
| **3.3.3 Error Suggestion (AA)** | Corrective suggestions where known | Applicability and usefulness |
| **3.3.4 Error Prevention (Legal, Financial, Data) (AA)** | Review/confirm/reverse mechanisms for covered submissions | End-to-end availability and preserved values |
| **3.3.7 Redundant Entry (A)** | Repeated same-process data requests and auto-population/selection | Exceptions and end-to-end process boundaries |
| **3.3.8 Accessible Authentication (Minimum) (AA)** | Cognitive-function tests, paste blocking, password-manager barriers, alternatives | End-to-end auth including third parties |

Do not interpret SC 3.3.8 as banning passwords. The failure is requiring a
cognitive-function test without an allowed alternative/assistance mechanism;
copy/paste and password managers can be relevant support.

## Robust

| SC | Static evidence to inspect | Usually needs rendered/manual evidence |
|---|---|---|
| **4.1.2 Name, Role, Value (A)** | Native semantics; ARIA roles, names, states, properties, and change code | Final accessibility tree and state announcements |
| **4.1.3 Status Messages (AA)** | Live-region/status semantics and update placement | Timely announcement without moving focus |

SC **4.1.1 Parsing** was removed in WCAG 2.2. Invalid markup still matters when
it breaks another criterion, especially 1.3.1 or 4.1.2; do not cite retired
4.1.1 as a WCAG 2.2 failure.

## Static finding patterns

**WRONG — 1.1.1 / 4.1.2.** An icon-only native button has no text, image
alternative, `aria-label`, `aria-labelledby`, or other possible name source.
Minimal fix: provide a stable name matching the visible purpose.

**WRONG — 2.1.1.** A clickable `div` has only `onClick`, no native control and
no keyboard behavior. Minimal fix: use `button`; do not reproduce its semantics
with role, focus, and key handlers unless native HTML cannot meet the need.

**WRONG — 1.4.3.** Complete token values establish 3.8:1 for normal body text
in a required state. Minimal fix: change a foreground/background token to reach
4.5:1, then verify all themes and states.

**UNIDIOMATIC.** A valid heading hierarchy skips levels for visual sizing while
CSS can style the semantically correct heading. The concrete cost is confusing
structural navigation. Minimal fix: choose heading levels by document outline.

**TASTE.** Two heading phrasings describe the section equally and expose the
same structure. Accessibility does not choose the editorial voice.

## Manual evidence template

Put each unresolved behavior under `Unverified`:

```
Platform/browser/AT:
Starting state and data:
Input sequence (Tab, Shift+Tab, arrows, swipe, activation, zoom):
Expected focus/role/name/state/announcement or visual result:
Pass condition:
Observed result: not run at L0
```

Use keyboard alone, browser zoom/reflow, high-contrast or forced-colors modes
when supported, reduced-motion preference, VoiceOver, and TalkBack according to
the order's support matrix. One combination does not prove another.

## Characteristic AI-generated mistakes

- Citing a made-up criterion or wrong level. **WRONG.** Verify WCAG 2.2 number,
  name, level, normative text, and exceptions.
- Calling an APG pattern or technique “required by WCAG.” **WRONG.** Cite the
  actual success criterion; pattern/technique is implementation guidance.
- Declaring contrast from token names such as `gray-500`. **WRONG.** Require
  final colors, backgrounds, opacity, themes, and state.
- Treating an `aria-label` as an automatic fix. **WRONG** when it conflicts
  with visible text or hides useful descendant naming. Compute the final name.
- Reporting every missing reduced-motion branch as AA failure under 2.3.3.
  **WRONG.** SC 2.3.3 is AAA; another A/AA criterion or platform practice may
  still apply.
- Equating scanner success with conformance. **WRONG.** Automated checks cover
  only detectable rules; preserve exact manual tasks under `Unverified`.
- Writing “test with a screen reader” without steps. **UNIDIOMATIC.** Name the
  platform, AT, navigation sequence, expected output, and pass condition.
