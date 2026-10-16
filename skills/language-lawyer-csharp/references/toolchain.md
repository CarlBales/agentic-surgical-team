# C# and .NET Toolchain

The toolsmith installs and wires the toolchain. The language lawyer establishes
which toolchain the repository selected, interprets its diagnostics, and
recommends the smallest language-level change. Commands that restore, build,
test, format, or analyze write artifacts and require L1 in the order's
workspace.

Use documentation for the observed versions:
[.NET CLI](https://learn.microsoft.com/en-us/dotnet/core/tools/),
[MSBuild](https://learn.microsoft.com/en-us/visualstudio/msbuild/msbuild),
[Roslyn/.NET analyzers](https://learn.microsoft.com/en-us/dotnet/fundamentals/code-analysis/overview),
and [NuGet](https://learn.microsoft.com/en-us/nuget/).

## Establish the effective baseline

Read before running anything:

- `global.json`: requested SDK version, `rollForward`, and prerelease policy;
- `.csproj`: SDK, `TargetFramework`/`TargetFrameworks`, `LangVersion`,
  `Nullable`, warning and analyzer properties, package references;
- `Directory.Build.props` and `Directory.Build.targets`: shared properties
  and targets found by walking parent directories;
- `Directory.Packages.props`: central package versions and central-management
  policy;
- `.editorconfig` and generated `.globalconfig`: diagnostic severities and
  code-style settings;
- `.sln`: the project set and solution configurations, not a substitute for
  each project's properties;
- `packages.lock.json`, `packages.config`, `NuGet.config`, and package source
  mapping when present;
- CI command lines supplied by the order: command-line properties can override
  project defaults.

MSBuild properties are evaluated, imported, and conditional. A text search for
one `TargetFramework` is not proof of the effective value. Conditions may vary
by configuration, platform, target framework, and operating system.

Later project/SDK logic can override early `Directory.Build.props`; late
`Directory.Build.targets` can override project values. Name the winner.

At L0, report pins and declarations as observed and selected versions as
unverified unless a read-only command is explicitly allowed. At L1, useful
baseline commands include:

```text
dotnet --info
dotnet --list-sdks
dotnet --list-runtimes
dotnet msbuild -version
```

Run from the repository context so `global.json` SDK resolution is the same as
the build. Quote actual output; do not infer an installed SDK from a pin.

## Target frameworks and language versions

A target framework moniker controls the reference assemblies and runtime/API
surface. A language version controls accepted C# syntax and semantics. They
are related defaults, not the same setting.

- `net48` targets .NET Framework 4.8 and its reference assemblies.
- `netstandard2.0` promises the .NET Standard 2.0 API surface, not one runtime.
- `net8.0` targets .NET 8; platform-qualified TFMs add platform APIs.
- `TargetFrameworks` compiles once per TFM. Conditional symbols and package
  assets can make each compilation different.

If `LangVersion` is absent, use Microsoft's documented default for that TFM.
Do not recommend `latest`: builds can silently accept new syntax when the SDK
changes. `preview` deliberately opts into unsupported-final-shape risk and
must be reported.

An API present in the installed runtime is irrelevant if it is absent from
the target's reference assemblies. Verify APIs in the versioned .NET API
reference or by an authorized compilation for every target.

## Build and test commands

Choose the repository's entry point; do not invent a solution-wide command
when the order names one project.

```text
dotnet restore <solution-or-project>
dotnet build <solution-or-project> --no-restore
dotnet test <solution-or-project> --no-build
dotnet pack <project> --no-build
```

These are examples, not automatic instructions. `--no-restore` is valid only
after a compatible restore; `--no-build` is valid only after the requested
configuration and TFM were built. Configuration, runtime identifier, and
custom properties must match CI.

`dotnet test --no-build` still runs code and may write test results, coverage,
logs, or temporary files. It is L1. Test strategy belongs to the tester; the
lawyer interprets language/compiler behavior exposed by a test.

For non-SDK-style .NET Framework projects, Visual Studio MSBuild and targeting
packs on Windows may be required. `dotnet build` is not a universal replacement
for old project systems, classic ASP.NET web projects, COM tooling, or custom
MSBuild tasks. Report that environmental requirement; do not rewrite the
project to make the local machine convenient.

MSBuild preprocessing can expose imports and winning property definitions, but
it writes an output file. Under L1, use the version's documented preprocess
switch and keep the output in the workspace. A binary log also writes a file
and may contain environment paths or command-line properties; treat it as
potentially sensitive evidence.

## Compiler diagnostics

C# compiler warnings use `CS` identifiers. Cite the official entry and the
exact compiler baseline.

- [`CS8602`](https://learn.microsoft.com/en-us/dotnet/csharp/language-reference/compiler-messages/nullable-warnings):
  nullable flow analysis sees a possible dereference of null. Inspect the
  path; `!` only suppresses analysis.
- [`CS4014`](https://learn.microsoft.com/en-us/dotnet/csharp/language-reference/compiler-messages/cs4014):
  a task-returning call is not awaited. Determine whether deliberate task
  ownership exists.

`TreatWarningsAsErrors` applies to C# compiler warnings handled by the compiler
task. MSBuild command-line warning promotion can have broader effects. Also
read `WarningsAsErrors`, `WarningsNotAsErrors`, and `NoWarn`; a clean build
under a suppression is not evidence that the underlying contract is sound.

Do not identify a warning from memory when the message and version are
missing. Ask for the exact ID and first diagnostic, because later errors are
often cascades.

## Roslyn and .NET analyzers

Three sources commonly contribute diagnostics:

1. compiler diagnostics built into Roslyn;
2. .NET code-quality analyzers supplied by the SDK;
3. analyzer packages referenced by the project, including source generators.

Effective severity can come from `.editorconfig`, `.globalconfig`, MSBuild
properties, command-line switches, or source pragmas/attributes. Read all of
them before saying a rule is enforced. `AnalysisLevel` selects a versioned
rule set; `AnalysisMode` influences which categories run. Projects targeting
older frameworks may opt into SDK analyzers explicitly or use packages.

Real examples:

- [`CA2007`](https://learn.microsoft.com/en-us/dotnet/fundamentals/code-analysis/quality-rules/ca2007),
  "Consider calling ConfigureAwait on the awaited task." It is context and
  configuration dependent; it does not prove a deadlock.
- [`CA1062`](https://learn.microsoft.com/en-us/dotnet/fundamentals/code-analysis/quality-rules/ca1062),
  "Validate arguments of public methods." Nullable annotations do not replace
  runtime validation at public boundaries.

Analyzer IDs beginning `CA` are not compiler errors, and style diagnostics
beginning `IDE` are not automatically build-enforced. Source generators and
analyzers execute during compilation and can write generated/intermediate
artifacts; running them requires L1.

A source suppression should state why the contract is safe, not merely that
the rule is noisy. A global `NoWarn` added to make CI green is **UNIDIOMATIC**
or **WRONG** when it hides a reachable defect.

## Formatting

`dotnet format` consumes solution/project configuration and `.editorconfig`.
A verification run is commonly:

```text
dotnet format <solution-or-project> --verify-no-changes
```

Even verification may evaluate projects and restore dependencies unless the
chosen version and flags prevent it, so treat it as L1. Verify syntax against
the installed tool's help; capabilities differ by SDK/tool version.

Formatting is mostly mechanical. Brace placement or expression-bodied-member
preferences are **TASTE** unless the repository has made them an enforced
rule. Do not turn every style diagnostic into a language-lawyer finding.

## NuGet and dependency judgment

Read the exact resolved model, not only remembered package behavior:

- `PackageReference` versions may be direct, centrally managed, conditional,
  or overridden;
- `Directory.Packages.props` enables central package management with
  `ManagePackageVersionsCentrally` and `PackageVersion` items;
- transitive versions follow NuGet resolution rules and can differ by TFM;
- `packages.lock.json` records a graph when lock-file mode is enabled;
- legacy `packages.config` installs packages differently and often relies on
  project-file imports or install scripts.

Authorized L1 commands can include:

```text
dotnet list <solution-or-project> package
dotnet list <solution-or-project> package --outdated
dotnet list <solution-or-project> package --vulnerable
dotnet restore <solution-or-project> --locked-mode
```

Some queries contact configured package sources and may update caches. Run
only when the order permits the access. A vulnerability result is evidence
from that source at that time; cite the advisory identifier it actually
returns, never invent a CVE.

Before recommending a package, ask:

1. Does the BCL for every target already provide the needed facility?
2. Does the package support every TFM and runtime identifier in scope?
3. Which exact version is resolved, and is the requested name authentic?
4. What transitive packages, analyzers, build targets, and native assets enter
   the graph?
5. Is maintenance and licensing evidence available through signed sources?
6. Does the package expose types that would become public API commitments?

Without external package evidence, mark maintenance and advisory claims
`Unverified`; do not browse or guess.

## .NET Framework and modern .NET migration

A migration changes more than a TFM string. Establish these before judging a
patch:

- SDK-style versus legacy project format;
- `packages.config`, binding redirects, GAC assumptions, and assembly-loading
  behavior;
- `System.Web`, `HttpContext.Current`, ASP.NET modules/handlers, and
  application lifecycle dependencies;
- AppDomains, remoting, COM, Windows-only APIs, registry or service behavior;
- configuration APIs and deployment transforms;
- serialization formats and runtime-specific behavior;
- generated code, designers, custom MSBuild tasks, and native dependencies;
- authentication, hosting, logging, and DI supplied by the old framework.

Classic ASP.NET is not ASP.NET Core with a namespace rename. A direct
`System.Web` dependency usually requires redesign at the platform boundary;
the surgeon chooses that migration.

[.NET Upgrade Assistant](https://learn.microsoft.com/en-us/dotnet/core/porting/upgrade-assistant-overview)
can analyze and stage parts of a migration. Its interfaces and supported
upgrade paths evolve, so inspect the installed version and official docs
before naming a command. Its output is a proposal, not proof of behavioral
compatibility. Installing or wiring it belongs to the toolsmith; applying a
migration requires an L1 order with narrow paths.

## Release boundary

Packing is L1. Forge approval, package publishing, deployment, and build
submission are L3: name a version-checked surgeon command, but never run it.
