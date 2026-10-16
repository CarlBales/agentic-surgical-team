# React Native and Expo Pitfalls

Recurring findings, with special attention to generated code. Each entry gives
a calibrated label and the smallest useful fix. Verify APIs and configuration
against the project's installed React Native, Expo SDK, and package versions.

## Characteristic of generated code

**Browser-only UI.** JSX contains `<div>`, `<span>`, CSS class selectors, or direct `document`/DOM calls in native code. **WRONG.** Use React Native components and style/accessibility APIs, or isolate the implementation in an explicit web-only platform file.

**Invented browser globals.** Code assumes `localStorage`, service workers, `HTMLElement`, object URLs, or a complete browser `window` contract exists because the source is JavaScript. **WRONG.** Check the React Native global/API documentation for the pinned version and use a supported native abstraction.

**Node.js APIs in the client.** Generated code imports filesystem, process, network-socket, or crypto behavior from Node without a documented React Native implementation. **WRONG.** Choose a package supported by the installed runtime or move the operation to an appropriate native/server boundary. Do not add a random polyfill merely because its package name looks plausible.

**Wrong Expo SDK example.** An import, config key, permission option, or method was copied from a different SDK line. **WRONG** when the installed package does not provide it. Read the versioned Expo page and the lockfile-resolved package; never "fix" it by upgrading the SDK outside the order.

**Hallucinated config plugin.** A plausible string is added to `plugins`, but
the installed package exports no plugin or expects different arguments.
**WRONG.** Verify the package's exact version and plugin documentation. If no
plugin exists, use its documented native setup or a reviewed local plugin.

**Managed/bare conflation.** Code edits `Info.plist` or a manifest that is not
committed, or changes app config and assumes committed native projects update
automatically. **WRONG** when the build never consumes the edit. Identify who
owns `ios/` and `android/`, then change the actual source of truth.

**Destructive prebuild advice.** A generated answer proposes regenerating
native projects without checking for hand-written native code. **WRONG** when
that loses project changes; otherwise **UNIDIOMATIC** as blind advice. Diff and
classify native ownership before any regeneration, and require L1.

**Fabricated verification.** A report says the app builds, links, receives a
notification, or accepts an update without a recorded run or artifact.
Protocol violation, not a platform finding. State precisely what was read,
predicted, or run.

## Native boundary and updates

**Native package over OTA.** A dependency with Pods, Gradle code, a native
module, or a config plugin is added, followed only by an OTA publication.
**WRONG.** Build and distribute a new binary with a new compatible runtime
version before publishing JavaScript that uses it.

**Native config over OTA.** Permission strings, entitlements, schemes, intent
filters, app links, icons, launch resources, or engine settings are changed and
expected to reach installed binaries through JavaScript. **WRONG.** These are
binary inputs; ship a new signed artifact.

**Channel as compatibility gate.** One channel serves binaries with different
native capabilities under the same runtime version. **WRONG.** Separate
incompatible runtimes with correct runtime versions/fingerprints; channel names
alone do not enforce native compatibility.

**Static import guarded too late.** Code imports a new native module, then
wraps its use in `try/catch` for old binaries. **WRONG.** Module resolution can
fail before the guarded call. Ship the native runtime first or use a real,
documented compatibility boundary.

**Engine assumption.** Code or a dependency assumes browser/V8 behavior while
the app uses Hermes or JavaScriptCore. **WRONG** if the feature is unavailable;
otherwise unverified. Record the engine per platform and test against the
release runtime rather than a desktop JavaScript runtime.

**Architecture by default.** A review declares the New Architecture enabled or
disabled because that was the default in another React Native/Expo release.
**WRONG.** Read the pinned framework docs, resolved app config, and native build
settings. Mark absence as unknown when defaults cannot be established.

## Configuration and dependency drift

**Two sources of native truth.** App config/plugin arguments and committed
native files disagree about identifiers, permissions, deployment targets, or
schemes. **WRONG** if builds consume the stale side unpredictably;
**UNIDIOMATIC** when one documented side clearly wins but dead configuration
misleads maintainers. Remove or regenerate the stale side.

**Dynamic config treated as JSON.** Review reports one branch of
`app.config.ts` as the resolved production value without the environment.
**WRONG.** Trace conditions, obtain an authorized resolved-config artifact, or
mark the value unknown.

**Public variable used as a secret.** A token or private credential is placed
in a client-visible environment variable or app config. **WRONG.** Remove it
from the client, rotate if exposed, and hand containment to the
security-reviewer and surgeon.

**Multiple lockfiles.** npm, Yarn, or pnpm locks coexist without a declared
consumer, so local, native, and remote builds can resolve different packages.
**UNIDIOMATIC**, and **WRONG** when evidence shows divergent native versions.
Choose one project-declared package manager and remove stale lockfiles under an
appropriate order.

**Metro defaults replaced.** A custom `metro.config.js` constructs an unrelated
configuration instead of extending/merging the defaults required by the
project's React Native or Expo version. **WRONG** when required asset extensions,
resolver behavior, or workspace settings disappear. Start from the documented
default config for the pinned framework, then apply the smallest override.

**Babel cargo cult.** A plugin or preset is copied from a tutorial for a
package version not installed. **WRONG** when transforms fail or ordering is
contractual; otherwise dead configuration is **UNIDIOMATIC**. Verify every
entry against the exact package docs and remove obsolete entries.

**Duplicate native package copies.** A monorepo or dependency graph installs
multiple copies of a package expected to be singleton, leading Metro and the
native linker to different instances. **WRONG** when registration or runtime
identity breaks. Align dependency ranges and workspace resolution; do not hide
the mismatch with arbitrary resolver aliases.

## Permissions and lifecycle

**Permission request without declaration.** JavaScript asks for access but the
binary lacks its plist usage description, entitlement, or Android manifest
permission. **WRONG.** Add the required native declaration through the correct
source of truth, then ship a new binary.

**Declaration without denial path.** The happy path assumes a request always
succeeds and crashes, loops, or blocks the app after denial. **WRONG.** Model
all states exposed by the exact API and preserve a usable fallback or clear
recovery path.

**Placeholder purpose string.** `Info.plist` tells the user "permission
needed" without explaining the feature and data use. **UNIDIOMATIC**, and a
store risk. Write accurate user-facing purpose text; prose refinement may go
to the editor.

**Foreground equals alive.** Code assumes backgrounding leads to an orderly
cleanup or that an in-memory store survives. **WRONG.** Persist critical state
incrementally and reconcile on launch/foreground after possible process death.

**JavaScript interval as scheduler.** A timer is used for periodic sync while
the app is backgrounded. **WRONG.** Use the documented OS/Expo background
mechanism for the installed versions and design for system-controlled timing.

**Listener accumulation.** AppState, Linking, keyboard, dimensions, or native
module listeners are added repeatedly and not removed with the documented
subscription API. **WRONG** when duplicate side effects result;
**UNIDIOMATIC** before harm is shown. Bind listener lifetime to component or
service lifetime.

## Links and notifications

**Warm-link-only handling.** Navigation listens for link events but ignores the
initial URL. **WRONG.** Handle cold and warm paths, deduplicate them, and test
foreground/background/terminated launches.

**JavaScript-only universal link.** A route exists, but associated domains,
intent filters, or origin association files are absent. **WRONG.** Configure
both native binary and web-origin trust, then ship a new binary.

**Custom scheme treated as verified identity.** Security-sensitive data is
accepted from a scheme any app may claim. **WRONG.** Prefer verified HTTPS
links where supported and validate authentication callbacks; hand protocol
threat analysis to the security-reviewer.

**Push token as user identity.** One token is stored forever or shared across
environments. **WRONG.** Treat tokens as rotating delivery addresses scoped to
app, platform, environment, and installation/account relationship.

**Notification receipt assumed.** Business state depends on a push handler
always running. **WRONG.** Notifications are hints; reconcile durable state
from its authority when the app next runs.

## Storage and privacy

**Tokens in AsyncStorage.** Bearer or refresh tokens are written to generic
persistent storage. **WRONG.** Use a reviewed Keychain/Keystore-backed facility
and define logout, revocation, lock-state, backup, and migration behavior.

**Secure-store label without properties.** A package is declared safe without
checking accessibility class, authentication requirement, backup behavior, or
invalidation. **UNIDIOMATIC.** State the exact platform guarantees and the
remaining threat assumptions.

**Sensitive diagnostics.** Push tokens, authorization headers, deep-link
credentials, or secure-store values are logged for debugging. **WRONG.** Remove
or redact them and assess existing exposure with the security-reviewer.

## Performance and rendering

**Large `ScrollView`.** Thousands of rows are rendered at once because the
fixture was small. **UNIDIOMATIC**, and a likely memory/startup cost. Use a
virtualized list and measure a release build on representative devices.

**Virtualized list inside same-axis scrolling.** A `FlatList` is nested in a
plain `ScrollView` with the same orientation, defeating windowing and commonly
triggering a React Native warning. **UNIDIOMATIC.** Give the virtualized list
ownership of that scroll axis and move surrounding content into list headers
or footers.

**Index keys for mutable rows.** Reordering or insertion reuses component state
for the wrong item. **WRONG** when state can attach to another record;
otherwise **UNIDIOMATIC**. Use a stable domain identifier.

**Stale `FlatList` rows.** Row rendering depends on state outside `data`, but no
documented invalidation input changes. **WRONG.** Pass the relevant immutable
value through the list's supported invalidation mechanism or include it in
item data.

**Heavy synchronous JS.** Parsing, transformation, compression, or iteration
blocks input and animation on the JS thread. **WRONG** when it violates a
required interaction; otherwise a mechanism-based performance risk. Chunk,
move, or redesign the work using APIs supported by the pinned runtime, then
measure.

**Memoize everything.** Generated code wraps every value and callback without
evidence, increasing complexity and sometimes doing more comparison work.
**UNIDIOMATIC.** Find the actual rerender cause, stabilize only meaningful
boundaries, and profile a release build.

**Dynamic asset path.** A runtime-computed `require` path is expected to make
Metro discover arbitrary bundled images. **WRONG.** Use statically discoverable
asset references or a documented remote-asset path.

**Debug performance presented as release performance.** Development tooling,
logging, and assertions distort results. **WRONG** as a claimed measurement.
Report build mode, device, scenario, and observed metric.

## Accessibility triage

**Unlabeled icon control.** A custom pressable exposes no accessible name,
role, state, or action. **WRONG.** Add the documented semantics or use a native
semantic control.

**Platform parity assumed.** A prop is tested with one screen reader and
claimed correct on both OSes. **WRONG** as evidence. Record the observed
platform only and hand full assistive-technology coverage to the
accessibility-reviewer.

## Calibration traps

**Preference as law.** Tabs versus spaces in config, profile names, or whether
generated native projects are committed can be **TASTE** when behavior is
clear and reproducible. State it once and stop.

**Unmeasured speed claim.** "Hermes is faster," "the New Architecture fixes
jank," or "memoization improves performance" without the app's measurement is
not a finding. Name the mechanism and missing benchmark instead.

**Store folklore as a rule.** A predicted rejection, policy deadline, or review
exception is repeated without current official evidence. Put it under
`Unverified`; never invent a guideline number or deadline.

**Fix by upgrading everything.** A compatibility defect prompts an Expo SDK,
React Native, navigation, and native dependency migration. Outside mandate and
high risk. Give the smallest version-compatible fix and offer the migration as
a surgeon decision, not a required patch.
