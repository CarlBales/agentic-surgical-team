# Build and Release

A release review connects source configuration to four different objects: a
native artifact, its store identity, the JavaScript runtime it embeds, and any
OTA updates it may later receive. Do not collapse these into "the Expo config."

Use the project-pinned EAS CLI and Expo SDK documentation. Starting points:
[EAS Build](https://docs.expo.dev/build/introduction/),
[`eas.json`](https://docs.expo.dev/build/eas-json/),
[EAS Submit](https://docs.expo.dev/submit/introduction/), and
[EAS Update](https://docs.expo.dev/eas-update/introduction/).

## Sources of truth

Read configuration in this order, recording conflicts rather than guessing
which one won:

1. `package.json`, package-manager declaration, and lockfile: Expo, React
   Native, EAS CLI, native packages, scripts, and dependency resolution.
2. `app.json`, `app.config.js`, or `app.config.ts`: identifiers, versions,
   plugins, updates, runtime policy, platform declarations, and environment
   branches.
3. `eas.json`: CLI compatibility constraint when present, build profiles,
   submit profiles, distribution, channels, environment selection, version
   behavior, and platform overrides.
4. `ios/`: Podfile and lock, Xcode project/settings, plist files,
   entitlements, privacy declarations, extensions, and native source.
5. `android/`: Gradle wrapper and build files, settings, version catalogs,
   manifest overlays, resources, signing indirection, variants, and source.
6. Supplied build logs, resolved-config exports, credentials metadata,
   fingerprint exports, store records, and update/channel exports.

Dynamic app config is code. The text may not reveal its resolved value without
the exact environment. At L0, trace branches statically and mark unresolved
values unknown. Do not execute the config merely to fill a report.

## Profile topology

EAS profile names are project-defined. `development`, `preview`, and
`production` are conventions, not proof of behavior. For each profile record:

| Concern | Questions |
|---|---|
| Artifact | development client, internal distribution, simulator/emulator, or store artifact? |
| Platform | shared settings, then exact iOS and Android overrides? |
| Channel | which update channel is embedded in this build? |
| Runtime | explicit runtime version or policy after config resolution? |
| Environment | which named environment and public configuration feed the build? |
| Versioning | source of marketing version, iOS build number, Android version code, and increment behavior? |
| Credentials | local/remote ownership and identity, without exposing secret material? |
| Destination | tester distribution, store upload, or artifact only? |

**WRONG:** infer that a profile named `production` is store-safe without
reading its actual distribution, channel, environment, identifiers, and
platform overrides.

**UNIDIOMATIC:** copy entire profiles for small differences so signing,
runtime, or channel settings drift. Use supported profile inheritance or a
small explicit matrix when it makes the resolved result clearer. Confirm the
feature against the project's EAS CLI version before proposing syntax.

**TASTE:** call an internal profile `preview`, `qa`, or `dogfood` when the
behavior and promotion path are unambiguous.

## Versions are different promises

Keep these fields distinct:

- the user-facing application version identifies a product release;
- the iOS build number orders builds for one bundle/version in Apple's system;
- the Android version code orders installed/store artifacts;
- the Expo runtime version identifies native compatibility for OTA updates;
- the EAS build ID identifies a build service job, not app compatibility;
- a channel routes builds to update streams, not native binaries to stores.

Automatic build-number/version-code increment can prevent duplicate store
versions, but it does not choose a correct marketing version or runtime
version. A runtime policy based on app version is safe only if every
native-compatibility change also changes that app version before any update can
reach the new binary.

**WRONG:** bump only Android `versionCode` after adding a native module while
retaining a runtime version shared with the old Android binary. Store ordering
and OTA compatibility are separate.

## Fingerprints

A fingerprint-based runtime policy uses project inputs to derive a native
runtime identity. It reduces manual version drift, especially when native
packages or generated configuration change.

Review fingerprint use with these limits:

- cite the fingerprint implementation and Expo SDK version in the project;
- compare fingerprints using an authorized generated artifact rather than
  inventing the expected hash;
- inspect exclusions, custom native files, environment-dependent config, and
  local plugins that may alter native output;
- do not assume equal fingerprints across iOS and Android or across differing
  build environments;
- a fingerprint proves selected inputs hashed equally, not that a build or
  update passed functional testing.

**WRONG:** manually override a fingerprint-derived runtime with a constant to
make an update reach more binaries. Restore compatibility isolation and ship a
new binary where necessary.

If no generated fingerprint is supplied, say that compatibility is predicted
from the visible inputs. At L1, a local fingerprint/config command may be run
only when the order authorizes project-code execution; capture the exact tool
version and output.

## Environments and secrets

Build-time values can enter dynamic app config, native resources, JavaScript,
or service-side build settings. Classify every value by where it ends up.

- A value embedded in JavaScript or native resources is recoverable from the
  app and is not a secret.
- Expo's `EXPO_PUBLIC_` convention explicitly makes a value available to client
  code. A credential under that prefix is **WRONG**.
- Different build and update environments can produce incompatible assumptions
  even with the same source commit. Record the environment used for each.
- Dynamic config that reads an absent variable should fail clearly for required
  values, not silently point production at a development service.
- Secret values must not be committed, printed in logs, copied into reports, or
  passed through public client configuration.

The repository can show variable names and selection logic. It cannot prove
current service values. Use only surgeon-signed read-only sources or redacted
exports. If a required environment mapping is unavailable, block the release
judgment rather than asking for raw secret values.

## Signing and identity

Signing material is authority, not ordinary configuration. Agents do not
create, rotate, download, upload, revoke, or expose credentials.

For iOS, establish from non-secret evidence:

- bundle identifier and any extension identifiers;
- developer team ownership;
- distribution method;
- entitlements/capabilities and their provisioning support;
- certificate/profile metadata and expiry when an authorized source supplies
  it;
- whether associated domains, push, keychain groups, or app groups match the
  intended identifiers.

For Android, establish:

- application ID and variant suffixes;
- upload-key versus app-signing-key ownership where store-managed signing is
  used;
- release signing indirection without reading passwords or key files;
- certificate identity used by Android App Links and external API allowlists;
- whether backup, debuggability, and manifest overlays resolve appropriately
  for the release variant.

**WRONG:** commit a keystore, private key, certificate password, service-account
credential, or signing export into the repository. Stop, avoid reproducing the
secret in the report, and escalate to the surgeon and security-reviewer for
containment and rotation.

## Native build boundary

A new native artifact is required for changes to:

- React Native, Expo SDK, native packages, Pods, Gradle dependencies, native
  source, or generated native modules;
- New Architecture or JavaScript engine selection;
- OS deployment/SDK targets, permissions, entitlements, manifest components,
  URL handlers, app links, extensions, icons, launch resources, or signing;
- config plugins or app-config values that alter any native output;
- bundle/application identity or store version codes.

A compatible OTA update may carry JavaScript and Metro-managed assets when the
installed runtime contains every native capability it uses and the update is
routed to the matching runtime version and platform.

Before recommending OTA, produce a binary/runtime/channel matrix. Before
recommending a binary, list every native surface changed. "Expo managed" does
not remove this distinction; it moves native generation into tooling.

## Reproducibility

A review should account for:

- one active package-manager lockfile and the package manager/version the
  project declares;
- deterministic dependency resolution, including Pods/Gradle inputs when
  native projects are committed;
- pinned or documented Node, Java, Ruby/CocoaPods, Xcode, Android SDK, and build
  image baselines where they affect the result;
- generated native projects matching app config and local plugins;
- build profile and environment named in the log;
- no untracked local native edit required for success;
- release-mode behavior on both platforms, not only a development client.

Do not call a build reproducible merely because the source commit matches. A
mutable environment, unlocked dependency, remote credential selection, or
dynamic config can change the artifact.

## Staging versus acting

At L1, the role may make a minimal configuration patch and run authorized local
checks inside the workspace. It may prepare a release matrix and write the
exact project-approved commands for the surgeon. It never:

- starts an EAS remote build or uploads project source to a build service;
- submits an artifact to App Store Connect or Google Play;
- publishes, republishes, rolls back, or changes routing for an OTA update;
- changes channels, branches, staged rollout, listings, review responses, or
  tester groups on a live service;
- creates or mutates signing credentials or service accounts.

Those are L3 actions even when a CLI makes them look routine. Common command
shapes documented by EAS include `eas build --platform <platform> --profile
<profile>`, `eas submit --platform <platform> --profile <profile>`, and
`eas update --channel <channel> --message <message>`. Do not execute them.
Before placing one in a report, verify its flags against the project-pinned EAS
CLI documentation and replace placeholders with the surgeon-approved values.

## Release review checklist

1. Pin source commit, app config input, lockfile, EAS CLI, Expo SDK, and build
   profile.
2. Resolve or obtain an authorized resolved-config artifact for the exact
   environment.
3. Map native changes to runtime-version/fingerprint changes.
4. Map profile to artifact kind, identifiers, versions, environment, channel,
   and destination for each platform.
5. Verify non-secret signing metadata and capability alignment without handling
   credentials.
6. Require local/build evidence at the authority granted; label missing runs.
7. Separate artifact creation, store submission, OTA publication, and rollout
   as distinct surgeon actions.
8. Record current policy/store checks as unverified unless official current
   evidence was supplied.
9. Give the surgeon a staged command and preconditions, never an assertion that
   an outward action happened.
