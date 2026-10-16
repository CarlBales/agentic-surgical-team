# Native Boundary and Updates

A React Native release has two separately delivered parts: an installed native
binary and a JavaScript/assets bundle. Correct update judgment starts by naming
which side owns every changed capability.

Authoritative starting points are Expo's
[runtime-version documentation](https://docs.expo.dev/eas-update/runtime-versions/),
[deployment model](https://docs.expo.dev/eas-update/deployment/), and
[config-plugin documentation](https://docs.expo.dev/config-plugins/introduction/).
Use the pages for the project's installed Expo SDK, not an unqualified latest
example.

## The installed runtime

The binary fixes more than the React Native version. It contains:

- the iOS executable, frameworks, CocoaPods, deployment target, entitlements,
  `Info.plist`, URL handlers, extensions, and code-signing identity;
- the Android application, native libraries, Gradle-selected SDK levels,
  manifest components and permissions, resources, package identity, and
  signing lineage;
- React Native's renderer and native-module system, the selected JavaScript
  engine, and New Architecture state;
- every native module and every native method exposed to JavaScript;
- an embedded JavaScript/assets update used on first launch or as recovery,
  according to the installed `expo-updates` configuration.

An OTA update can replace compatible JavaScript and assets. It cannot add code
to the executable, alter signed entitlements, add manifest components, link a
library, switch engines, or change a deployment target. A JavaScript bundle
that assumes any such change is not an incomplete rollout; it is incompatible
with the installed runtime.

## The runtime-version promise

`runtimeVersion` is a compatibility contract. An update is eligible only when
its platform and runtime version match within the update stream reached by the
build's channel/branch routing. Therefore:

- a **channel** selects a stream of updates for a build;
- a **runtime version** says which native runtime can execute those updates;
- a matching channel does not override a runtime mismatch;
- two binaries may share a runtime version only when their JavaScript-visible
  native behavior is compatible in both directions needed by the rollout.

**WRONG:** keep one constant runtime version across a native-module addition,
then publish JavaScript that imports the module. Old binaries can receive code
that calls a symbol they do not contain.

**Fix:** build a new binary with a new runtime version, direct compatible
updates to it, and retain a compatible update for binaries on the old runtime.
If mixed-binary rollout is intentional, feature-detect only when the native API
provides a real, documented detection mechanism; a `try/catch` around a static
import is not one.

Runtime-version policies derive the value from another source:

- a native-version or app-version policy is only as safe as the team's rule
  for incrementing that version on every compatibility change;
- an SDK-version policy groups by Expo SDK, but application native changes can
  occur without changing the Expo SDK;
- a fingerprint policy derives compatibility from project inputs that affect
  the native runtime and is generally safer for frequent native changes;
- an explicit string is valid when release automation changes it reliably and
  the mapping is documented.

Do not remember policy names or semantics from another SDK line. Read the
installed SDK's app-config schema and runtime-version page. If the configured
policy cannot be verified, report it as unknown rather than silently treating
it as an explicit value.

## Classifying changes

Use this table as a first pass, then verify the installed package and config:

| Change | OTA-only release? | Reason |
|---|---|---|
| JavaScript business logic using existing native APIs | Usually eligible | No binary capability changed |
| Images, fonts, or other Metro-managed assets supported by the installed runtime | Usually eligible | Delivered with the update bundle |
| Pure-JavaScript dependency with no plugin or native package | Usually eligible | Bundle-only, subject to engine support |
| Add or upgrade a package containing native iOS/Android code | **No** | Native code must be linked into a new binary |
| Add or change a config plugin that mutates native output | **No** | Plugin effects occur during native generation/build |
| Change `Info.plist`, entitlements, `AndroidManifest.xml`, resources, or Gradle/Pod configuration | **No** | These are installed and often signed native state |
| Change permissions, URL schemes, universal/app links, extensions, icons, or launch resources | **No** | OS registration belongs to the binary |
| Change React Native or Expo SDK | **No** | Native framework changes |
| Switch Hermes/JSC or New Architecture state | **No** | Runtime implementation changes |
| Change only a remote endpoint read from existing runtime configuration | Possibly | Verify the value is not compiled into native config and is safe to expose |

"Usually" is deliberate. A JS-only package can still depend on a newer Hermes
feature, changed global, asset transformer, or native peer. Read its supported
React Native/Expo matrix and lockfile-resolved version.

## Config plugins and prebuild

Expo app config is input. Config plugins transform that input into native
projects during prebuild or an EAS native build. The resulting native files,
not the plugin declaration alone, are what iOS and Android execute.

Review a plugin in this order:

1. Identify the exact installed plugin package and version. Some libraries
   include a plugin; others require a separate package or manual setup.
2. Read the project's static or dynamic app config and the plugin arguments.
3. Name the native surfaces it mutates: plist keys, entitlements, Podfile,
   Xcode settings, manifest entries, Gradle files, resources, or source files.
4. Check whether the native directories are generated, committed, or manually
   maintained. The same plugin declaration has different operational meaning
   in each workflow.
5. Verify that repeated generation is intended to be idempotent. Duplicate
   manifest nodes, URL types, build phases, or Gradle entries indicate a
   brittle plugin.
6. Treat any plugin or argument change that affects native output as requiring
   a new binary and a compatible runtime-version change.

**WRONG:** add a camera permission plugin, publish an OTA update, and expect the
old binary to acquire its usage description or manifest permission.

**UNIDIOMATIC:** keep generated native projects in source control while also
hand-editing the same keys and offering no documented regeneration boundary.
The app can build differently locally and remotely. Choose a source of truth,
or document which native customizations must be re-applied by a local plugin.

**TASTE:** commit generated native directories versus regenerate them in the
build, when both workflows are deliberate, reproducible, and preserve custom
native code. Do not turn workflow preference into a defect.

A dynamic `app.config.ts` is executable configuration. Static reading may show
branches but not the resolved value because environment variables, helper
modules, or filesystem state participate. At L0, do not evaluate it. Report the
condition and ask for an L1 resolved-config artifact when the answer controls a
finding.

## Native modules and architecture

A package in `dependencies` is not proof that its native half is installed.
Check, as applicable:

- whether the package actually contains a native module or config plugin;
- whether autolinking sees the intended package and platform;
- whether CocoaPods and Gradle resolved the same lockfile version as Metro;
- manual native setup required by the package's documentation;
- New Architecture support for the exact package version;
- code generation, generated specifications, and build settings required by
  TurboModules or Fabric components;
- app extensions or multiple Android variants that need separate linkage.

**WRONG:** import a native package in JavaScript because it appears in
`package.json`, while the shipped binary predates its installation.

**UNIDIOMATIC:** disable the New Architecture globally to accommodate one
unverified package without checking the package's supported version and the
framework baseline. State the compatibility evidence and the smallest change;
the surgeon owns the migration decision.

Engine changes also cross the binary boundary. Hermes and JavaScriptCore do
not promise identical support or performance for every JavaScript feature and
native integration. Record the engine per platform, and verify a package's
engine assumptions rather than treating "JavaScript" as one runtime.

## Update rollout review

For each EAS build profile and release population, write a small matrix:

| Binary/profile | Platform | Native fingerprint or defining inputs | Runtime version | Channel | Compatible update |
|---|---|---|---|---|---|
| supplied value | iOS/Android | supplied value or unknown | supplied value | supplied value | update/group or unknown |

Then ask:

- Can every binary on the channel execute every update that routing may expose
  to its runtime version?
- Did a native-affecting change also change the runtime version before update
  publication?
- Does the update use an API absent from any still-active binary with the same
  runtime version?
- Is the embedded update usable if no remote update is available or a launch
  fails?
- Are platform-specific updates built for the correct platform and engine?
- Is rollback/recovery described without pretending it can remove already
  installed native code or repair a bad binary configuration?

Live channel mappings and deployed update groups require authorized read-only
sources or supplied exports. Repository `eas.json` proves intended build
configuration, not current service state. If rollout safety depends on live
state and no source is supplied, **BLOCK** rather than guess.

## Verification boundaries

At L0, read `package.json`, lockfiles, app config source, `eas.json`, native
projects, and supplied build/update exports. Label resolved config, generated
native output, fingerprints, and bundle compatibility as predictions where no
authorized artifact establishes them.

At L1 in a workspace, an order may authorize local config resolution,
dependency diagnostics, native generation, or a local build. These operations
write files and may execute package code. Preserve the before/after diff and
report the exact command and output. Never publish an update or start a remote
build to "verify" compatibility. Publication and remote release actions are
for the surgeon.
