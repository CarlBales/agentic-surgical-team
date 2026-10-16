# React Native Accessibility Review
React Native maps JavaScript props to native accessibility APIs; it does not produce one platform-neutral
accessibility tree. Establish the pinned React Native version, iOS and Android targets, navigation/modal
libraries, and custom component wrappers before judging an API.

Use the matching [React Native accessibility documentation](https://reactnative.dev/docs/accessibility),
[Apple accessibility documentation](https://developer.apple.com/accessibility/), and [Android accessibility
guidance](https://developer.android.com/guide/topics/ui/accessibility). Do not cite the current React Native
site as proof for an older pinned release.
## What static review can establish
Source can establish that a prop is present or absent, which branch updates it, and whether visible state and
accessibility state share data. It can sometimes prove a missing role/name or hidden-background error.

Source alone does not establish:

- final native accessibility elements after wrapper/view flattening;
- VoiceOver versus TalkBack role and announcement mapping;
- swipe order, grouping, rotor/local-context behavior, or focus timing;
- whether programmatic focus runs after native mount/layout;
- modal background exclusion;
- label/hint phrasing in platform speech;
- dynamic announcement timing and interruption;
- touch-target size after layout, scaling, or device density.

Put these under `Unverified` with separate iOS/VoiceOver and Android/TalkBack steps. Simulator evidence is not
physical-device evidence; identify which was used.
## Core props
Verify every prop against the pinned version. These are common contracts, not a complete API list.
### `accessible`
Marks a view as an accessibility element/focusable grouping according to platform mapping. Grouping can cause
children to be presented as one element and can hide useful child navigation. Many touchable controls are
accessible by default; adding the prop everywhere is not harmless.

**WRONG:** a card is `accessible={true}` and contains separately actionable
children that no longer receive accessibility focus on a target platform.
Minimal fix: expose the actions separately or make the grouped card the single
real action, then test both platforms.
### `accessibilityLabel`
Provides the element's accessible name. Prefer visible text/native inference when it produces the intended
name; an explicit label can drift from visible copy and break voice control expectations.

- Name the purpose, not the control type: “Save draft,” not “Save draft button.”
- Include visible label text for WCAG 2.2 SC 2.5.3 where applicable.
- Do not concatenate volatile state into the label when
  `accessibilityState` expresses it.
- Localize through the same supported system as visible strings.

**WRONG:** visible “Pay now” control has `accessibilityLabel="Submit"`. Minimal
fix: use the visible text as the name or begin with it.
### `accessibilityRole`
Exposes the semantic role supported by the pinned React Native/platform version. A role is a behavior promise:
a “button” must activate as a button, a “header” must actually head content, and a “link” must navigate as
expected. Never invent a role string from web ARIA memory.

**WRONG:** a pressable toggle exposes only `button` while checked/selected state
is not represented. Minimal fix: choose the supported role/state contract for
the exact component and version, then verify announcements on both platforms.
### `accessibilityState`
Represents state such as disabled, selected, checked, busy, or expanded when supported. Derive it from the
same state as visuals and interaction. An element announced disabled must also reject activation; a visually
selected item must update its accessibility state in the same transition.

**WRONG:** `accessibilityState={{ expanded: true }}` is a constant while the
panel collapses. Minimal fix: bind it to the actual expanded state.
### `accessibilityHint`
Describes the result of an action when the label alone does not make that result clear. It is not a second
label, state channel, or instruction dump. VoiceOver users can disable hints, so essential information cannot
live only there.

**UNIDIOMATIC:** every button has “Double tap to activate.” Platform assistive
technology already teaches activation. Minimal fix: remove generic hints and
keep only consequence-specific guidance.
### `importantForAccessibility`
This Android-oriented prop controls whether a view and/or descendants are important for accessibility;
supported values and behavior are versioned. `no-hide-descendants` is a strong subtree exclusion. Review it on
overlays, duplicated labels, decorative containers, and hidden routes, and do not assume an iOS effect.

**WRONG:** an inactive route remains visible to TalkBack because only opacity or
pointer handling changed. Minimal fix: remove/hide the route in native
accessibility exposure using the version-supported navigation/view mechanism.
### `accessibilityViewIsModal`
This iOS prop tells VoiceOver to ignore sibling views while focusing the marked view. It does not render an
overlay, block touches, contain keyboard focus, move initial focus, close on request, or provide an Android
modal boundary.

**WRONG:** code sets `accessibilityViewIsModal` and claims a cross-platform
accessible modal, with background controls still reachable on Android. Minimal
fix: implement each platform's complete modal/background isolation and test it.
## Grouping and reading order
Native accessibility order often follows native view hierarchy and platform heuristics, not merely JSX order.
Absolute positioning, portals, navigation stacks, overlays, conditional mounts, and grouped parents change it.

Review:

- one focusable element per real action unless a composite pattern requires
  otherwise;
- child actions not swallowed by an accessible parent;
- duplicated parent and child labels not announced twice;
- decorative images excluded without excluding meaningful siblings;
- headings exposed at real section starts;
- list item position/context when platform/component support supplies it;
- hidden routes, drawers, sheets, and loading overlays excluded appropriately;
- visual order aligned with swipe/read order.

**UNIDIOMATIC:** a row and its only child button are both accessibility elements
with the same action/name. The cost is duplicate stops. Minimal fix: expose one
semantic action.

Static JSX order is not proof. Add separate swipe-through tests for VoiceOver and TalkBack.
## Pressables and custom controls
A `Pressable`/touchable needs:

1. accessible name;
2. supported role;
3. state and value when relevant;
4. disabled behavior synchronized with semantics;
5. activation through accessibility action;
6. adequate target dimensions/spacing under the stated baseline;
7. visible focus for platforms/input modes that expose it;
8. no nested competing press target unless intentionally separate.

Do not recreate switches, checkboxes, text inputs, or adjustable controls from a plain view when a maintained
native/component-library primitive meets the need. Custom adjustable controls require platform actions and
value announcements that static review cannot prove.

**WRONG:** visual disabled styling changes opacity, but `onPress` still runs and
no disabled accessibility state is supplied. Minimal fix: bind visual,
interaction, and `accessibilityState.disabled` to one source of truth.
## Modals, sheets, drawers, and navigation
For every overlay or route transition, trace:

- triggering element and its native handle/lifetime;
- mount/open point and intended initial accessibility focus;
- title/name and modal semantics;
- background pointer and accessibility exclusion on each platform;
- close/cancel/back gesture and hardware Back handling where applicable;
- destructive-action focus choice;
- focus restoration after close;
- nested overlay behavior;
- screen transition announcement/title behavior.

Programmatic accessibility focus APIs are timing-sensitive and versioned. Verify that the target exists in the
native tree and avoid repeatedly forcing focus on rerender. A focus call in source is evidence of intent, not
success.

**WRONG:** closing a sheet unmounts its trigger and sends focus to an arbitrary
screen root, making the user restart navigation. Minimal fix: restore to the
next logical surviving control and verify on both platforms.
## Dynamic status, errors, and busy state
Loading, success, validation error, cart count, and route changes may require an announcement without stealing
focus. React Native's supported live-region and announcement APIs differ by version/platform; verify exact
APIs before naming a fix.

- Expose busy state on the relevant region/control when supported.
- Do not announce every progress tick.
- Associate input errors through the platform/version-supported mechanism and
  ensure error text is reachable in order.
- Keep entered values after validation.
- Move focus only when task recovery benefits, such as an error summary or the
  first invalid field under an established pattern.
- Do not encode state only in a long changing label.

**WRONG:** an async save reports failure only with a transient red toast that is
not focused or announced. Minimal fix: expose a persistent reachable error and a
supported announcement/status mechanism, then test interruption and timing.
## Motion and user settings
Review animations, parallax, auto-advance, shake-to-act, haptics paired with visual-only feedback, and
transitions. Querying a reduced-motion setting is not enough; every animation path must honor the resulting
policy without removing essential progress or state feedback.

WCAG 2.2 SC 2.3.3 Animation from Interactions is AAA, not AA. Motion may still implicate A/AA criteria for
flashing, pause/stop/hide, motion actuation, or a project/platform requirement. Label the actual authority.

**UNIDIOMATIC:** reduced motion replaces a transition with no state-change cue.
Minimal fix: use an immediate or low-motion transition while preserving focus,
status, and visible feedback.

**TASTE:** two concise hints describe the same non-obvious consequence and both
localize correctly. No accessibility fix is required; follow the product voice.
## Touch targets
WCAG 2.2 SC 2.5.8 Target Size (Minimum) uses a 24-by-24 CSS-pixel measure and exceptions for web content.
Apple and Android platform guidance uses its own point/dp conventions. Do not silently convert one standard
into another.

For native review, cite the project's platform guideline/version and inspect layout, hit slop, spacing,
overlap, scaling, and adjacent targets. A large visual parent does not enlarge the hit target unless event
handling does. Static style numbers remain unverified after responsive layout and font scaling.
## VoiceOver test procedure
For each changed task on every supported iOS form factor:

1. enable VoiceOver in target OS settings and identify device/simulator and OS;
2. enter from a known route and navigate by left/right swipe;
3. record order and every relevant name, role, state, value, and hint;
4. use double-tap and any required adjustable/custom actions;
5. open overlays; verify initial focus, background exclusion, dismissal, and
   restoration;
6. trigger loading, validation, error, success, and disabled states; record
   announcements and interruption;
7. use relevant rotor navigation, including headings/links where exposed;
8. enable larger text and reduced motion, repeat layout/task checks;
9. state expected and observed result for each step.

Do not infer TalkBack from this result.
## TalkBack test procedure
For each changed task on every supported Android form factor:

1. enable TalkBack and identify device/emulator, Android API/OS, and app build;
2. enter from a known route and swipe forward/back through all elements;
3. record order and every relevant name, role, state, value, and hint;
4. activate, adjust, and use any exposed accessibility actions;
5. open overlays; verify initial focus, background exclusion, Back/dismissal,
   and restoration;
6. trigger loading, validation, error, success, and disabled states; record
   announcements and interruption;
7. exercise heading/control navigation when supported by the tested version;
8. enable large font/display size and remove animations/reduced motion settings,
   then repeat the task;
9. state expected and observed result for each step.

Do not infer VoiceOver from this result. Differences are findings only when they break the stated
task/standard, not merely because speech wording differs.
## Characteristic AI-generated mistakes
- Copying web `aria-*` attributes into a React Native version that does not
  support them. **WRONG.** Use props documented for the pinned release.
- Adding `accessible={true}` to every container. **WRONG** when grouping hides
  child actions; otherwise noisy and **UNIDIOMATIC**. Group deliberately.
- Putting role, state, and hint into one long `accessibilityLabel`.
  **UNIDIOMATIC** and often stale. Use supported semantic channels.
- Assuming one prop has identical iOS/Android behavior. **WRONG.** Cite mappings
  and test both screen readers.
- Treating `accessibilityViewIsModal` as a focus trap and Android solution.
  **WRONG.** Complete each platform's modal contract.
- Calling a focus API on every render. **WRONG** when it steals focus or loops.
  Tie it to a defined transition and verify native timing.
- Inventing a role, action, or prop from a future/current version. **WRONG.**
  Check the repository pin and versioned docs.
- Reporting “screen-reader compatible” from snapshots or unit tests. **WRONG.**
  Keep exact VoiceOver and TalkBack task runs under `Unverified`.
- Adding generic hints to every control. **UNIDIOMATIC.** Hints describe
  non-obvious consequences and may be disabled.
## Finding shape
A React Native finding names the component and head line, pinned RN/platform version, affected task,
source-state path, one label, smallest fix, platform citation, and separate VoiceOver/TalkBack verification
steps. A static review verdict never claims the native accessibility tree or announcements passed.
