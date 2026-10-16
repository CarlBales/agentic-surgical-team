# iOS and Android Platform Differences

React Native shares component code; it does not erase either operating
system's lifecycle, permission, process, distribution, or security model.
Review each platform independently and cite the documentation for the targeted
OS/API version.

Primary sources: Apple's [platform documentation](https://developer.apple.com/documentation/),
Android's [developer guides](https://developer.android.com/guide), and React
Native's [AppState](https://reactnative.dev/docs/appstate),
[Linking](https://reactnative.dev/docs/linking), and
[PermissionsAndroid](https://reactnative.dev/docs/permissionsandroid) pages.
## Lifecycle and process death

React components mount and unmount according to the React tree, not directly
according to an OS process lifecycle. Keep these layers separate:

| Event | iOS consequence | Android consequence | Review implication |
|---|---|---|---|
| App leaves foreground | transitions through inactive/background and is commonly suspended | activity stops; process may remain cached | pause foreground-only work; do not assume JS continues |
| App returns | process may resume or cold launch | activity may resume, recreate, or cold launch | restore from durable state, not module memory |
| Memory pressure | suspended/cached app may be terminated | process may be killed without another JS callback | persist important state before the final moment |
| UI interruption | an inactive transition may occur without full backgrounding | focus can change while app remains resumed | model focus separately when behavior depends on it |

**WRONG:** rely on a timer, unmount cleanup, or a final AppState callback to
persist irreplaceable user work. Neither OS promises JavaScript a last chance
before process termination.

**Fix:** persist recoverable state incrementally, make startup restoration
idempotent, and treat foreground transitions as reconciliation points. Keep
server operations idempotent because a request may finish while its JS caller
is suspended or may be retried after uncertain completion.

**UNIDIOMATIC:** register an AppState or native event listener on every render
without removing the prior subscription. The duplicate callbacks survive
until their owning runtime is torn down. Register in a lifecycle-aware effect
and return the documented cleanup.

Do not equate `AppState.currentState` at module initialization with a stable
answer; React Native documents that its initial value may be unavailable while
it is retrieved over the bridge. Use the API behavior documented for the
project's React Native version.
## Permissions

A permission has at least three layers: native declaration, runtime request
when the OS requires one, and behavior when access is unavailable.
### iOS

- Protected resources require the corresponding `Info.plist` purpose string.
  The text is user-visible and must describe the real use, not a placeholder.
- Some capabilities also require signed entitlements and provisioning support.
  A plist key cannot substitute for an entitlement.
- Authorization states are API-specific. Do not collapse limited, provisional,
  restricted, denied, and not-determined states into one boolean when the
  targeted framework exposes them.
- Opening Settings is a recovery path, not permission grant logic. The app must
  remain useful or explain the unavailable capability after denial.

**WRONG:** call a protected iOS API without its required purpose string. A JS
request cannot add the missing native declaration; ship a corrected binary.
### Android

- Declare permissions and components in `AndroidManifest.xml`, directly or
  through generated config.
- Permissions classified for runtime request must also be requested at the
  point of use on applicable API levels. A manifest declaration alone does not
  grant them.
- Permission behavior changes with `targetSdk` and OS API level. Review the
  exact matrix, including one-time or selected-media access where applicable,
  rather than copying a request flow from another target.
- Android 13/API 33 introduced the `POST_NOTIFICATIONS` runtime permission for
  non-exempt notifications. Cite the current Android notification-permission
  guide before applying it to a target matrix.

**WRONG:** check only `Platform.OS === "android"` before requesting a permission
whose runtime behavior also depends on API level and target SDK.

For Expo packages, app config or a config plugin commonly writes native
permission declarations; the JavaScript package performs the runtime request.
Both must match the installed SDK documentation. A plugin change requires a
new binary.
## Background execution

No mobile platform grants a general-purpose always-running JavaScript process.
### iOS

iOS normally suspends backgrounded applications. Specific background modes,
background tasks, location modes, audio modes, notification handling, and
other frameworks grant bounded or purpose-specific execution. Scheduling and
runtime are controlled by the system; completion deadlines matter.

**WRONG:** promise exact periodic execution from a JavaScript timer or a
background scheduling API. The OS may defer, coalesce, or omit work.
### Android

Android limits background services and implicit work according to OS and
target SDK. Deferrable durable work generally belongs in the platform's
scheduled-work mechanism; user-visible ongoing work may require a foreground
service and notification, with service-type and permission requirements that
vary by API level.

**WRONG:** start unrestricted background work from JS and assume it continues
after the activity or process is gone.

Use the Expo background API documented for the installed SDK. Package names
and availability have changed across SDK lines, so a remembered example from
`latest` is not evidence. Verify native registration, task definition timing,
platform support, and development-client limitations for the exact version.
## Notifications

Remote notifications join application code to APNs, FCM, entitlements,
credentials, app identity, user permission, backend token storage, and OS
delivery policy.

- iOS notification authorization and remote-notification registration are
  separate concepts. Entitlements and provisioning must match the bundle.
- Android notification channels control user-visible behavior on supported
  versions; channel identifiers become durable user settings and should not be
  casually reused for a different purpose.
- Push tokens can rotate. Associate them with app/environment/platform and
  handle refresh or rejection; do not treat a token as a permanent user ID.
- Delivery is not guaranteed, and receipt does not guarantee JavaScript ran.
  Reconcile durable state when the app opens.
- Foreground presentation, background handling, and a user's tap are distinct
  paths. Test cold, warm, foreground, denied, and disabled-channel states.

Live APNs/FCM/EAS credential or delivery state requires a surgeon-signed
read-only source or supplied export. Repository configuration alone cannot
prove registration or delivery. Report missing external evidence rather than
inventing a provider diagnosis.
## Deep links, universal links, and app links

Custom URL schemes are easy to register but are not strongly associated with
one app. Universal links and Android App Links bind HTTPS origins to an app
using both native declarations and files hosted by the web origin.

For iOS universal links, review:

- the associated-domains entitlement with the intended `applinks:` domains;
- the `apple-app-site-association` file served as Apple requires;
- app identifiers and path/component matching;
- behavior when the app is installed, foregrounded, backgrounded, or absent.

For Android App Links, review:

- manifest intent filters with the intended scheme, host, and path scope;
- `android:autoVerify="true"` where verified links are intended;
- the origin's `assetlinks.json` statements and signing-certificate identity;
- API-level and user-default behavior.

**WRONG:** add only a JavaScript route for an HTTPS URL. The OS cannot route a
universal/app link without the native declaration and valid origin association.

**WRONG:** parse an authentication callback only from a warm-link event. A
cold launch arrives through the initial-URL path. Handle both using the APIs
for the installed React Native/navigation version, deduplicate the action, and
validate the destination. Authentication state/nonce validation belongs to the
security-reviewer.

Changes to schemes, intent filters, associated domains, or entitlements require
a new binary. Changes to the hosted association files are external deployment
work and need an authorized source to verify.
## Secure local storage

AsyncStorage is persistent key-value storage, not a secret store. It does not
promise Keychain or Android Keystore protection.

**WRONG:** store bearer tokens, refresh tokens, private keys, or equivalent
reusable credentials in AsyncStorage. Use a project-approved API backed by iOS
Keychain and Android Keystore, such as the installed Expo secure-storage
package when its documented properties fit the threat model.

Review the details, not just the package name:

- accessibility while the device is locked and whether user presence is
  required;
- Android backup/restore behavior when encryption keys are device-bound;
- iOS reinstall and migration behavior; never rely on incidental persistence
  as the only account-control mechanism;
- biometric enrollment changes and invalidation behavior;
- token deletion on logout and server-side revocation;
- error behavior when the secure store is locked or unavailable.

Broad secret-handling and threat-model decisions belong to the
security-reviewer. The platform lawyer establishes what the storage mechanism
actually guarantees on the targeted OS versions.
## Performance boundaries

React Native work can occupy the JavaScript thread, UI/main thread, background
native threads, or renderer/native-module paths. New Architecture changes
transport and rendering internals; it does not make long synchronous work free.

- A long synchronous calculation or large JSON transform on the JS thread can
  delay input handling and JS-driven animation.
- Repeated renders matter when their component work matters. Identify the
  changing prop/context/state and measured cost before prescribing memoization.
- `ScrollView` renders all children. Large, variable data sets generally need a
  virtualized list such as `FlatList`, with stable keys and deliberate item
  rendering.
- `FlatList` is a `PureComponent`; items depending on state outside `data`
  need the documented invalidation input. Otherwise visible rows can remain
  stale.
- Native-module calls should avoid chatty high-volume crossings and large
  serialization where the installed architecture still incurs those costs.
- Performance claims require a release-mode measurement on representative
  hardware. A mechanism-based risk is not a measured regression.

**UNIDIOMATIC:** replace a virtualized list with a `ScrollView` for thousands
of rows because the smaller fixture looked correct. Restore virtualization and
measure the real item path.
## Accessibility boundary

React Native exposes native accessibility semantics. At minimum, inspect custom
pressables, icon-only controls, images conveying information, disabled/selected
state, modal focus, and platform-specific actions.

**WRONG:** a custom icon button has no accessible name or role, so assistive
technology cannot identify its purpose. Add the documented React Native
accessibility props or use a native-semantic component.

This role records obvious platform contract failures. The
accessibility-reviewer owns WCAG success criteria, screen-reader journeys,
focus order, dynamic announcements, contrast, text scaling, switch control,
and device testing.
## Store and policy evidence

Store requirements move independently of repository code. At a high level,
check that:

- purpose strings and permission use match actual behavior;
- privacy disclosures/data-safety declarations can be reconciled with included
  SDKs and data flows;
- account, payment, background, notification, and tracking behavior is reviewed
  against current rules where relevant;
- Android target API and iOS SDK submission requirements are checked for the
  intended submission date;
- third-party SDK manifests or privacy declarations required by the store are
  included for the exact dependency versions.

Do not invent guideline numbers, policy deadlines, rejection outcomes, or
exceptions. Cite the current official page supplied or authorized for the
order. Store submission, listing edits, staged-rollout changes, and responses
to reviewers are L3; report the evidence and let the surgeon act.
