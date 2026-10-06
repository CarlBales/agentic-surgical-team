# Rust Toolchain

What to run, what the output means, and how to judge dependencies. The
toolsmith owns installing and wiring these; the lawyer owns interpreting
them.

## Establishing the baseline

```bash
rustc --version                 # installed compiler
cargo --version
cat rust-toolchain.toml         # project pin, if any; this wins
grep -E '^(edition|rust-version)' Cargo.toml
cargo tree --depth 1            # direct dependencies
```

Report all of these. An opinion about Rust code without a version attached
is not a finding, because idiom and availability both move with the release.

Editions are opt-in per crate and interoperate. Current editions: 2015,
2018, 2021, 2024. Edition changes that bear on review:

- **2024**: `gen` reserved as a keyword; `unsafe_op_in_unsafe_fn` warns by
  default, so the body of an `unsafe fn` is no longer implicitly an unsafe
  block; `impl Trait` lifetime capture rules changed; `static_mut_refs`
  denied; tail expression temporaries drop earlier; `unsafe` required on
  some attributes.
- **2021**: disjoint closure captures; `IntoIterator` for arrays; `panic!`
  format consistency; bare trait objects became a hard error, so `dyn Trait`
  is required.
- **2018**: module path changes; `dyn Trait` introduced and bare trait
  objects warned, but still accepted.

Use `cargo fix --edition` for migration, and say that it does not handle
semantic changes.

## Commands

```bash
cargo check --all-targets --all-features     # fastest type check
cargo clippy --all-targets -- -D warnings    # lints; the real gate
cargo fmt --check                            # formatting
cargo test --all-features                    # includes doc tests
cargo doc --no-deps --document-private-items
cargo build --release                        # optimization-dependent behavior

cargo +nightly miri test                     # UB detection in test-reachable code
cargo +nightly udeps                         # unused dependencies
cargo tree --duplicates                      # multiple versions of one crate
cargo deny check                             # licenses, advisories, bans
cargo audit                                  # known vulnerabilities
cargo semver-checks check-release            # semver violations
cargo bench                                  # or criterion
```

Only report output you actually ran. A prediction is labeled a prediction.

## Clippy

Lint groups: `correctness` (deny; these are bugs), `suspicious`,
`complexity`, `perf`, `style` (all warn by default), `pedantic`, `nursery`,
`restriction`, `cargo` (all allow by default).

`pedantic` is useful for review and noisy as a gate. `restriction` is for
project-specific policy, never a blanket recommendation.

Lints worth citing by name:

| Lint | Catches |
|---|---|
| `clippy::needless_pass_by_value` | taking ownership of something only read |
| `clippy::ptr_arg` | `&String` / `&Vec<T>` parameters |
| `clippy::redundant_clone` | clone whose result is never needed |
| `clippy::unwrap_used`, `clippy::expect_used` | panics in library paths |
| `clippy::missing_errors_doc`, `missing_panics_doc`, `missing_safety_doc` | undocumented contracts |
| `clippy::must_use_candidate` | results callers will silently drop |
| `clippy::await_holding_lock` | `.await` while holding a sync guard |
| `clippy::large_enum_variant` | one fat variant inflating every value |
| `clippy::needless_collect` | collecting only to iterate again |
| `missing_debug_implementations` (rustc, not clippy) | public type without `Debug` |
| `clippy::cast_possible_truncation`, `cast_sign_loss` | silent `as` casts |
| `clippy::indexing_slicing` | panicking indexing in library code |
| `clippy::mut_mut`, `clippy::mem_forget` | soundness-adjacent smells |

Project configuration lives in `[lints.clippy]` in `Cargo.toml` or in
`clippy.toml`. Read it before reporting a lint the project has deliberately
allowed. An `#[allow(...)]` without a comment explaining why is a finding;
an `#[allow]` with a good reason is not.

## Features

- Features are additive. A feature that *removes* or *changes* behavior
  rather than adding it is a design defect; two mutually exclusive features
  are worse.
- `default-features = false` on dependencies where the default pulls in a
  runtime, `std`, or TLS stack the project does not want.
- Test the feature matrix, at minimum no-default and all-features.
  `cargo hack` does the rest.
- `#[cfg(feature = "...")]` on public items means the public API changes with
  features. Document it with
  `#[cfg_attr(docsrs, doc(cfg(feature = "...")))]`.
- Feature unification applies per package version within a build graph:
  enabling a feature anywhere unifies it for every consumer of that same
  package version in the same graph. A library enabling `tokio/full` imposes
  it on everyone who shares that `tokio`. Resolver 2 (`resolver = "2"`, the
  default from edition 2021) narrows this: it does not unify features for
  platform-inactive dependencies, for build-dependencies and proc-macros
  versus normal dependencies, or for dev-dependencies of packages not being
  built.

## Dependency judgment

Before accepting a new dependency, ask:

1. **Does `std` do this now?** `OnceLock`, `LazyLock`, `let`-`else`,
   `is_some_and`, and array methods have retired a lot of small crates.
   State the version in which the std facility landed.
2. **Is it the community-standard choice?** `serde`, `tokio`, `thiserror`,
   `anyhow`, `clap`, `tracing`, `rayon`, `itertools`, `regex`, `reqwest`,
   `bytes`, `parking_lot`, `proptest`, `criterion` are defaults for their
   niches. A novel crate in a well-served niche needs a reason.
3. **Is it maintained?** Last release, open issue trend, whether it compiles
   on the project's toolchain.
4. **What does it cost?** Transitive count, compile time, binary size,
   whether it pulls a second async runtime or a second TLS implementation
   into the graph. `cargo tree --duplicates` makes this visible.
5. **Does it use `unsafe`?** For a crate on the trust path, that matters.
   `cargo geiger` counts it.
6. **Is the name right?** Typosquatting on crates.io is real. Flag any name
   one character from a popular crate.
7. **License compatibility.** `cargo deny check licenses`.

Require a real minimum, not `"*"`. Note that `"1.2"` is a **caret
requirement** — `>=1.2.0, <2.0.0` — not a pin; write `=1.2.3` when an exact
pin is genuinely intended, and expect that to cause conflicts in a shared
graph. Commit `Cargo.lock` for binaries; for libraries it is advisory only.

## Performance claims

Never assert a performance difference without a measurement. The acceptable
forms are:

- "Measured: `cargo bench` shows X" with the output.
- "This allocates once per iteration; whether it matters depends on the call
  rate, which I did not measure."

Things worth flagging anyway, as costs rather than as measured regressions:
allocation inside a hot loop, `collect()` into a `Vec` only to iterate it
again, `String` concatenation in a loop without `with_capacity`, `clone()` of
a large structure per call, `format!` on a hot path, and `Box<dyn Trait>`
dispatch where monomorphization was free.

Do not claim bounds checks cost anything without looking. LLVM frequently
eliminates them for `0..slice.len()` loops; on rustc 1.93 at `-O` such a loop
emits no panic path at all. If it matters, read the generated code
(`cargo asm`, or `--emit=llvm-ir`) or benchmark it.

Debug and release differ enough that a profile taken in debug is
meaningless. Say which profile a measurement came from.

## Reproducing a diagnostic

When the surgeon reports an error you cannot see, ask for:

```bash
cargo --version && rustc --version
cargo clean && cargo check --all-targets 2>&1 | head -50
rustc --explain E0502        # the rule, in the compiler's own words
```

Minimizing is the fastest route to a correct answer: reduce to the smallest
file that still fails, and the cause usually becomes obvious. Say when a
finding is unverified because you could not reproduce it.
