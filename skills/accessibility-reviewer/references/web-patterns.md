# Accessible Web Patterns
Use native HTML before ARIA. The first rule of ARIA is: if a native HTML element or attribute supplies the
required semantics and behavior, use it instead of repurposing an element and adding ARIA. Source: [WAI-ARIA
Authoring Practices Guide](https://www.w3.org/WAI/ARIA/apg/practices/read-me-first/).

ARIA changes the accessibility tree. It does not add keyboard behavior, focus management, styling, validation,
submission, or pointer behavior. Review the rendered widget contract, not the presence of attributes.
## Native semantics first
| Need | Prefer | Avoid |
|---|---|---|
| action | `<button type="button">` | clickable `div`/`span` with reconstructed behavior |
| navigation | `<a href="…">` | button that manually changes location |
| text input | `<input>` with `<label>` | contenteditable/custom textbox without a stated need |
| choice | checkbox, radio, or `<select>` | generic elements with hand-built state |
| expandable details | `<details><summary>` when behavior fits | custom disclosure for styling alone |
| dialog | `<dialog>` when support/behavior fits, or a complete APG dialog | visual overlay without modal semantics/focus behavior |
| progress | `<progress>` when determinate | text percentage with no programmatic role/value |

A native element can still fail through missing names, disabled keyboard access, hidden focus, bad order, or
incorrect state. “Native” is a starting point, not a verdict.

**WRONG:** a `div role="button" tabindex="0"` responds only to click and Enter.
Native buttons also provide Space activation, disabled semantics, form
behavior, and platform mappings. Minimal fix: use `<button>`.

**UNIDIOMATIC:** a complete custom button duplicates native behavior solely to
avoid resetting browser styles. Minimal fix: style a native button.
## Accessible names and descriptions
Determine the final name using [Accessible Name and Description Computation
1.2](https://www.w3.org/TR/accname-1.2/), not a guessed precedence list. Common name sources include native
labels, element text, `aria-labelledby`, and `aria-label`; applicability and precedence depend on role and
host-language rules.

Review these failure modes:

- icon-only control with no name source;
- `aria-label` overriding useful visible descendant text;
- `aria-labelledby` referencing a missing, duplicate, or wrong ID;
- repeated controls all named “More” without programmatic context;
- placeholder used as the only form label;
- image `alt` duplicating adjacent text or describing appearance instead of
  purpose;
- decorative image left exposed, or meaningful image hidden;
- visible label absent from the accessible name, violating WCAG 2.2 SC 2.5.3
  Label in Name for controls covered by that criterion;
- title/tooltip relied on as the primary name or instruction.

A description supplements a name. It cannot repair a missing or misleading name. Hints should explain unusual
consequences, not restate the label.

**WRONG:** visible “Delete account” button named “Remove” by `aria-label`.
Speech users cannot reliably invoke the visible text. Minimal fix: remove the
override or make the accessible name begin with the visible label.
## Roles, states, and ownership
Use only roles/states/properties permitted by WAI-ARIA 1.2 and the element's host-language semantics. Verify
spelling and allowed values against the spec.

- A role is a behavioral promise. `role="menu"` promises application-menu
  keyboard interaction; it is not a styling hook for site navigation.
- Update states such as `aria-expanded`, `aria-selected`, `aria-checked`, and
  `aria-busy` from the same source of truth as visible state.
- Relationship attributes must reference IDs that exist in the rendered
  document and remain unique.
- `aria-hidden="true"` removes descendants from the accessibility tree. It must
  not contain focusable descendants.
- `role="presentation"`/`none` does not reliably neutralize focusable elements
  and should not erase required structure.
- Do not put conflicting ARIA on a native control, such as an unrelated role on
  a button, without a versioned platform reason.

**WRONG:** collapsed content is visually hidden, but a focusable child remains
in keyboard order under an `aria-hidden` ancestor. Minimal fix: remove it from
both rendering/focus or use a disclosure primitive that coordinates all three.
## Focus fundamentals
DOM order should match reading and interaction order. CSS `order`, grid placement, transforms, and portals can
make visual order diverge. Avoid positive `tabindex`; fix source order instead.

A focus indicator must be visible, and under WCAG 2.2 AA the focused component must not be entirely obscured
(SC 2.4.11). Do not remove `outline` without a replacement that survives relevant themes, zoom, and
forced-colors behavior.

Move focus only for a user-understandable context change: opening a modal, adding an error summary after
failed submission, or navigating a client-rendered route. Preserve user location for ordinary updates. On
teardown, restore focus to the invoking control or the next logical target if that control no longer exists.

Static review rarely proves focus timing with React effects and portals. Put initial focus, containment,
dismissal, and restoration under `Unverified` with exact keyboard steps.
## Dialog pattern
Follow the APG [modal dialog pattern](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/) when a custom
modal is necessary.

Contract:

1. container has dialog semantics (`dialog` or `alertdialog` as appropriate);
2. it has an accessible name, usually through visible title association;
3. modal state is exposed only when interaction is actually modal;
4. opening moves focus to a suitable element inside;
5. Tab and Shift+Tab remain within the open dialog;
6. Escape closes unless the task has an explicit, justified exception;
7. a visible close/cancel mechanism is keyboard operable;
8. closing restores focus logically;
9. background content is not reachable by pointer, keyboard, or accessibility
   navigation while modal;
10. destructive confirmation chooses initial focus deliberately; do not put it
    on the destructive action by reflex.

Large semantic content may initially focus a static heading/container with `tabindex="-1"` so screen-reader
users can read from the start. Do not set `aria-describedby` to a large structured body that should be
navigated by its own headings and lists.

**WRONG:** `aria-modal="true"` is added while background links remain operable.
The accessibility tree claims a boundary the interaction does not enforce.
Minimal fix: implement the full modal boundary or expose a non-modal dialog.
## Menu button pattern
Use a menu only for application-like commands, not ordinary site navigation. Follow the APG [menu button
pattern](https://www.w3.org/WAI/ARIA/apg/patterns/menu-button/).

- Trigger is a button with a name, `aria-haspopup="menu"`, and synchronized
  `aria-expanded`; relationship to popup follows the supported pattern.
- Opening places focus in the menu according to the activation key.
- Menu items use menu roles and roving focus or `aria-activedescendant` as the
  chosen complete pattern requires.
- Arrow keys move among items; Home/End and type-ahead behavior follow the
  selected pattern; Escape closes and restores trigger focus.
- Disabled items' focus behavior must match the adopted pattern.

**UNIDIOMATIC:** global navigation uses menu/menuitem roles and arrow-only
movement. Users expect links and normal Tab navigation. Minimal fix: semantic
navigation/list/link markup, with a disclosure button for a submenu if needed.
## Tabs pattern
Follow the APG [tabs pattern](https://www.w3.org/WAI/ARIA/apg/patterns/tabs/).

- `tablist` owns or labels the set; every `tab` names and controls one
  `tabpanel`; exactly the active tab has `aria-selected="true"` and is in the
  Tab sequence.
- Arrow keys move focus among tabs according to orientation.
- Automatic activation is appropriate only when panel display has no noticeable
  latency; otherwise focus and activation are separate and Enter/Space selects.
- Inactive panels are hidden from all users, not merely visually covered.
- If a panel has no focusable content, consider making it focusable according to
  the APG guidance so keyboard users can enter its content.

**WRONG:** every tab has `tabindex="0"`, so the component adds all tabs to the
page Tab order and omits expected arrow navigation. Minimal fix: roving
`tabindex` synchronized with selected/focused state.
## Combobox pattern
Combobox is not a generic text input with suggestions. Choose an APG [combobox
pattern](https://www.w3.org/WAI/ARIA/apg/patterns/combobox/) matching editable/select-only behavior and popup
type.

Review:

- input/control exposes `combobox`, name, expanded state, and popup relationship;
- `aria-autocomplete` is used only for the implemented completion model;
- popup role (listbox, grid, tree, or dialog) and child roles agree;
- focus either stays on the input with `aria-activedescendant`, or follows the
  selected documented model—never a mixture;
- active descendant IDs exist and point to eligible options;
- arrow, Enter, Escape, typing, selection, clearing, and blur behavior follow
  one model;
- browser autocomplete and form submission do not conflict;
- loading, no-results, errors, and selected value are announced appropriately.

**WRONG:** visual highlight changes while `aria-activedescendant` remains on the
old option. Minimal fix: update visual and accessibility active state from one
source of truth.

Combobox behavior varies materially across browsers and assistive technologies. Static review can find broken
relationships; put announcements and operation under `Unverified` for every supported combination.
## Forms, errors, and status
- Use a persistent visible label associated with each control.
- Group related choices with `fieldset`/`legend` where appropriate.
- Instructions precede the input or are programmatically associated; required
  format and state are not color-only.
- On validation, set visible error text, identify the field, associate the
  message, and preserve entered values.
- If focus moves to an error summary, each summary item should take the user to
  the field; test return flow.
- Use status/alert semantics according to urgency. Do not move focus to routine
  status messages merely to force announcement.
- Insert/update live-region content in a way supported by the target stack; an
  initially populated region may not announce as expected.

**WRONG:** a red border is the only error identification. This fails users who
cannot perceive color and supplies no text/programmatic error. Minimal fix: add
specific text and relationship, then verify announcement.

**TASTE:** `aria-label` and `aria-labelledby` compute the same stable name here,
and neither changes visible-text matching. No fix is required; match the component convention.
## CSS visibility, contrast, and motion
`display: none`, the `hidden` attribute, and `visibility: hidden` normally remove content from
layout/accessibility exposure. Visually hidden text needs a tested clip/off-screen utility that remains
available to assistive technology and does not create scroll or focus anomalies. Do not hide focusable content
off-screen.

Calculate contrast from final foreground/background/state values. Token names are not evidence. Check hover,
focus, active, disabled (disabled controls may be excepted by specific contrast criteria), error, placeholder,
high-contrast, and forced-colors behavior according to the support baseline.

Honor `prefers-reduced-motion` where repository policy or user-impact evidence requires it. WCAG 2.2 SC 2.3.3
Animation from Interactions is AAA, while A/AA requirements such as pause/stop/hide and flashing can still
apply. Avoid blanket removal of functional progress feedback.
## Manual pattern test
For each widget, record:

1. browser, OS, screen reader, zoom and preference settings;
2. entry by Tab and by screen-reader navigation;
3. exact keys/swipes for opening, moving, selecting, canceling, and leaving;
4. expected name, role, state, position/set information, and announcement;
5. focus target after every state transition and teardown;
6. pointer/touch completion and an alternative to complex gestures;
7. pass/fail for every supported combination.

At L0 these are `Unverified`; never write “works with screen readers” from source inspection.
## Characteristic AI-generated mistakes
- Adding ARIA to make markup “more accessible.” **WRONG** when it conflicts
  with native semantics; remove it unless it supplies a missing valid contract.
- Generating a custom widget but only implementing mouse behavior. **WRONG.**
  Use native HTML or implement the complete APG keyboard/focus model.
- Assigning `role="menu"` to site navigation. **WRONG** when menu behavior is
  absent; usually fix with `nav`, lists, links, and disclosure buttons.
- Sprinkling live regions around all changing text. **UNIDIOMATIC** and often
  disruptive. Announce task-relevant status with deliberate politeness/timing.
- Forcing focus on every render through an effect. **WRONG** when it steals user
  position. Move focus only at defined context changes.
- Treating `aria-hidden` as visual hiding. **WRONG** if visible/focusable content
  disappears only for assistive technology.
- Inventing ARIA values or relationships. **WRONG.** Check WAI-ARIA 1.2 and the
  pinned framework's DOM output.
- Claiming APG conformance from attribute names alone. **WRONG.** Keyboard,
  focus, state synchronization, and platform testing complete the pattern.
## Citation discipline
Use the HTML Living Standard for native semantics, WAI-ARIA 1.2 for roles and states, Accname 1.2 for naming,
WCAG 2.2 for obligations, and an explicitly dated/revision-identified APG pattern for implementation guidance.
Never turn an APG recommendation into an unnamed WCAG requirement.
