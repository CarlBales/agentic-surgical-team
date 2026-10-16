# TypeScript Toolchain

The toolsmith installs and wires tools. The language lawyer establishes which
configuration applies and interprets its output. At L0, every command below is
a prediction or a command for the surgeon; run it only in an L1 workspace.
Prefer repository scripts because they encode package boundaries and options.

Official references must match installed versions: the
[compiler options](https://www.typescriptlang.org/tsconfig/),
[typescript-eslint rules](https://typescript-eslint.io/rules/),
[ESLint flat configuration](https://eslint.org/docs/latest/use/configure/configuration-files),
and each runner or package manager's documentation.

## Establish the baseline

Read before running:

```text
package.json
package-lock.json | pnpm-lock.yaml | yarn.lock
packageManager field and workspace declarations
tsconfig.json plus every extends target and project reference
eslint.config.js|mjs|cjs|ts and any referenced configuration
prettier configuration and ignore files
Jest or Vitest configuration
Node.js version pins, engines, Browserslist, React Native/Hermes versions
Nx workspace and project configuration when present
```

The nearest `package.json` may not own the compiler. In a workspace, follow
the selected package manager's resolution and lockfile to the actual
`typescript` package. Record a range as a range when no exact lock resolution
is available. Do not substitute a global compiler.

Resolve the tsconfig chain in order. `extends` values can name files or
packages, and a package may expose different configuration by version. A
child overrides inherited options. Files included in the program depend on
`files`, `include`, `exclude`, references, and command-line selection; opening
a `.ts` file near a config does not prove that config compiles it.

## Type checking

Use the repository's script first, for example its `typecheck` script. When
there is no script and the baseline confirms a single project, the standard
shape is:

```bash
pnpm exec tsc --noEmit -p tsconfig.json
npm exec -- tsc --noEmit -p tsconfig.json
yarn tsc --noEmit -p tsconfig.json
```

Choose only the project's package manager; these are alternatives, not a
sequence. Do not use a command that may download a missing compiler. Even
`--noEmit` is an L1 command under the surgical-team protocol because toolchain
execution can write caches or build information.

`--noEmit` asks the compiler not to emit JavaScript, source maps, or
declarations. It does not prove that the production bundler, transpiler, or
runtime can load the result. Type-check the same project and module mode used
by the actual build.

`tsc --showConfig -p tsconfig.json` is useful at L1 for the resolved compiler
view. Compare its version with the lockfile. Do not quote its output unless it
was actually run.

## Project references and build mode

Project references split a graph into projects. Referenced projects normally
use `composite`, which constrains configuration and supports declaration and
build-information outputs. `tsc -b` operates on the graph, determines stale
projects, and can write outputs and `.tsbuildinfo`; it is not a read-only
check.

Review this graph rather than checking only the leaf package:

- every reference points in the intended dependency direction;
- imported package source agrees with the declaration output consumers see;
- root solution configs do not accidentally compile files themselves;
- output and build-information paths do not collide across packages;
- a package's test config does not leak test globals into its production
  declaration surface;
- clean-checkout builds do not depend on stale generated declarations.

Running plain `tsc --noEmit` in one package does not necessarily traverse and
validate references the way the repository's build script does. Use the
pinned compiler's documented build-mode options; do not invent a flag to make
an incompatible graph read-only.

## ESLint flat configuration and typescript-eslint

Modern ESLint flat configuration is commonly held in `eslint.config.js`,
`.mjs`, `.cjs`, or another extension supported by the installed ESLint
version. The installed typescript-eslint major determines whether the
repository imports the unified `typescript-eslint` package or separate parser
and plugin packages. Follow the checked-in style; do not rewrite a working
configuration merely because current documentation uses a newer API.

Type-aware rules require a TypeScript program or the project-service mechanism
supported by that typescript-eslint version. A wrong tsconfig root can make
files appear outside the project, consume excessive memory, or lint under a
different option set. Generated files and declaration output should be
ignored deliberately, not accidentally parsed as source.

Real, commonly relevant rules include:

| Rule | What it checks | Type information |
|---|---|---|
| `@typescript-eslint/no-floating-promises` | promise-like values whose outcome is not handled | required |
| `@typescript-eslint/no-misused-promises` | promises used where the surrounding API expects another kind of value, including selected void-return callbacks | required |
| `@typescript-eslint/no-unsafe-assignment` | `any` flowing into a typed binding | required |
| `@typescript-eslint/no-unsafe-member-access` | member access through `any` | required |
| `@typescript-eslint/no-unnecessary-type-assertion` | assertions that do not change the type | required |
| `@typescript-eslint/switch-exhaustiveness-check` | non-exhaustive switches over unions or enums | required |
| `@typescript-eslint/consistent-type-imports` | consistent explicit type-only imports | not required |

Verify rule availability and options against the installed major before
citing them. A rule name remembered from another plugin or version is not a
finding. Rule output is evidence only after an actual L1 run.

`no-floating-promises` cannot decide business ownership of intentionally
detached work. `void task()` may satisfy configured handling policy, but it
does not catch rejection. Review the runtime consequence in addition to the
lint result.

For React projects, `react-hooks/rules-of-hooks` and
`react-hooks/exhaustive-deps` belong to the React hooks plugin, not
typescript-eslint. The latter approximates closure dependencies; framework
and compiler versions still matter.

## Formatting

Prettier is a formatter, not a semantic validator. A typical check uses the
repository script or pinned executable with `prettier --check`; writing uses
`--write` and requires L1. Exact file selection and ignore rules belong to the
repository configuration.

Do not report a Prettier disagreement as **WRONG**. It is at most an enforced
project convention. Avoid running overlapping ESLint formatting rules unless
the checked-in configuration intentionally owns that integration. Formatting
preference outside an enforced convention is **TASTE**.

## Jest and Vitest

Jest and Vitest execute behavior; test strategy belongs to the tester. The
lawyer checks whether TypeScript and module semantics make the tests mean what
they claim.

- A transpiler can run `.ts` without a complete `tsc` type check. Passing
  tests do not replace the type-check command.
- Vitest commonly transforms through the Vite toolchain; transformation is
  not proof that Node-oriented declaration or module resolution succeeds.
- Jest behavior depends on its transformer, environment, and ESM/CJS setup.
  Read the pinned Jest and transformer versions before proposing flags.
- Fake timers alter scheduling. A passing timer test may not establish real
  promise, microtask, or host scheduling unless the configured runner's
  version documents it.
- Test globals should come from the selected runner's declarations and should
  not leak into production projects unintentionally.

Run the exact package script at L1. Do not swap Jest for Vitest, or vice
versa, as a language-lawyer fix; such migration belongs to the surgeon and
toolsmith.

## npm, pnpm, and Yarn

The lockfile and `packageManager` field identify both dependency resolution
and command vocabulary. Do not mix lockfiles or run a different manager: that
can rewrite resolution and repository state.

- npm workspaces, pnpm workspaces, and Yarn workspaces have different
  hoisting and linking behavior. An import that succeeds only because a
  transitive dependency is hoisted is **WRONG** when the package does not
  declare that dependency.
- pnpm's stricter layout often exposes undeclared imports hidden by a flat
  installation.
- Yarn has multiple major lines with materially different configuration and
  installation models. Read `.yarnrc.yml`, checked-in releases/plugins, and
  the `packageManager` value.
- A lockfile records resolved packages; `package.json` records the intended
  direct contract. Review both before claiming a version or dependency is
  unused.

Installation and lockfile regeneration write broadly and belong to an L1
workspace under an explicit order. Registry publication is L3 and never an
agent action.

## Nx and monorepos

Nx adds a project graph, named targets, caching, and affected-project
selection. Target names such as `typecheck` are repository-defined; never
assume one exists. Read `nx.json`, project configuration, package scripts,
and inferred-task configuration for the installed Nx version.

Check:

1. which project owns the changed file;
2. which target invokes `tsc`, ESLint, Jest, or Vitest and with which config;
3. whether project references and Nx graph edges agree;
4. whether a cache hit could be masking an undeclared input;
5. whether path aliases cross a package boundary without a publishable runtime
   mapping;
6. whether root checks cover every affected project rather than only the app.

Use the repository's documented Nx commands at L1. Cache directories and task
outputs are writes. A command copied from a different Nx major is a
**prediction**, not authoritative guidance.

## Interpreting compiler diagnostics

A diagnostic code identifies a category in a particular compiler version;
the instantiated types and effective options explain the actual failure.
Common codes include:

| Code | Typical statement | First question |
|---|---|---|
| `TS2322` | a value is not assignable to a target type | where did the source or target become too broad or narrow? |
| `TS2345` | an argument is not assignable to a parameter | is the call wrong, or does an earlier boundary lose information? |
| `TS7006` | a parameter implicitly has `any` | which contextual type or annotation is missing under the effective implicit-`any` setting? |
| `TS18048` | a value is possibly `undefined` | is absence real, or should the model establish presence earlier? |

The smallest fix is rarely `as`, `!`, or disabling a strict option. Trace the
source type backward: an unchecked parse, a widened literal, an optional
property, an index read, or a lost generic relation often caused the use-site
error.

Quote the full diagnostic and compiler version. Do not promise that a code's
wording or trigger is identical across TypeScript versions. At L0, say
"predicted TS2322 under the stated baseline" rather than claiming the compiler
ran.

## Dependency and release judgment

From repository evidence, check direct declaration, resolved version,
runtime versus development scope, duplicate major versions, module format,
type inclusion, and compatibility with the project's runtime. A package that
ships declarations may not need a separate `@types` package; mismatched copies
can create duplicate or contradictory globals.

Maintenance, vulnerability, license, and registry-provenance claims need a
signed `inputs.sources` tool or supplied report. Without one, put them under
`Unverified` and name the read-only evidence needed. Never invent a CVE or
claim a package is abandoned from memory.

Before a release, compare generated declarations and every exported entry
against the prior public surface. Generation is L1; package publication,
tagging, and forge release actions are L3 for the surgeon.
