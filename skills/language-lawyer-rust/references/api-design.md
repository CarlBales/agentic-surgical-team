# Rust API Design

Judgments about the public surface. The authority here is the
[Rust API Guidelines](https://rust-lang.github.io/api-guidelines/); this file
is the short form plus the findings that recur most.

A public API is a promise. The lawyer's job is to notice promises the surgeon
did not mean to make.

## Argument types

Take the least restrictive type that does the job.

| Instead of | Take | Why |
|---|---|---|
| `&String` | `&str` | callers with `&str` need no allocation |
| `&Vec<T>` | `&[T]` | same, for slices |
| `&PathBuf` | `&Path` or `impl AsRef<Path>` | accepts `&str`, `String`, `PathBuf` |
| `Vec<T>` (read only) | `&[T]` or `impl IntoIterator<Item = T>` | no forced allocation |
| `String` (read only) | `&str` | same |
| concrete closure type | `impl Fn(..) -> ..` | callers pass anything callable |

Counter-pressure: generics in the public surface cost compile time,
monomorphization, and readability, and they are harder to make
object-safe. `impl AsRef<Path>` on every function in a crate is
**UNIDIOMATIC** in the other direction. Use generics where callers
genuinely arrive with different types.

Take by value when you will store it; take by reference when you will read
it. A function taking `Vec<T>` and immediately borrowing it is
`clippy::needless_pass_by_value`.

## Return types

- Return owned data; do not return references into internals unless the
  lifetime relationship is part of the contract.
- Return iterators where the caller may not need all elements. `impl
  Iterator<Item = T> + '_` is the usual shape. Returning `Vec<T>` where an
  iterator would do is **TASTE** in a binary, **UNIDIOMATIC** in a library.
- `impl Trait` in return position hides the concrete type, which is good for
  future flexibility and bad when callers need to name it. Trade-off, not a
  rule.
- Avoid `Box<dyn Trait>` where a generic or `impl Trait` works; use it where
  heterogeneity is real.
- Newtype instead of returning a bare `u64` that means something. Primitive
  obsession in a public API is a real finding: `fn timeout(ms: u64)` invites
  the caller to pass seconds.

## Trait impls to consider

For every public type, ask whether these are missing:

- `Debug` — nearly always. Its absence breaks callers' `#[derive(Debug)]`.
  The rustc lint `missing_debug_implementations` catches it (it is a rustc
  lint, not a clippy one).
- `Clone`, `Copy` — when semantically sound. `Copy` is a semver promise.
- `Default` — when a meaningful empty or zero value exists.
- `PartialEq`/`Eq`, `Hash` — consistently: equal values must hash equally.
- `PartialOrd`/`Ord` — only when a total order is meaningful; derived order
  follows declaration order, which is a trap for enums.
- `Display` — for user-facing types. Not the same as `Debug`.
- `std::error::Error` with `source()` — for every error type.
- `From` — for conversions that cannot fail; `TryFrom` for those that can.
  Implement `From<YourError>` sparingly; it makes `?` silently convert.
- `Send`/`Sync` — auto; verify they are not accidentally lost by an internal
  `Rc` or raw pointer. Losing them in a patch release is a breaking change.
- `Deref` — only for smart pointers. `Deref` for inheritance-like reuse is
  **UNIDIOMATIC**.
- `Iterator` / `IntoIterator` — for collections, including `&T` and `&mut T`
  impls.
- Serde `Serialize`/`Deserialize` behind a feature flag, not unconditionally.

## Errors

Libraries and binaries want different things.

**Library**: a concrete, inspectable error type.

```rust
#[derive(Debug, thiserror::Error)]
#[non_exhaustive]
pub enum UploadError {
    #[error("upload exceeded maximum size of {max} bytes")]
    TooLarge { max: u64 },
    #[error("transport failure")]
    Transport(#[source] std::io::Error),
}
```

- One error type per module or per logical operation, not one per crate and
  not one per function.
- `#[non_exhaustive]` on public error enums, so adding a variant is not
  breaking.
- Implement `source()` so callers can walk the chain. `thiserror`'s
  `#[source]` or `#[from]` does this.
- Error messages are lowercase, no trailing period, and describe what failed
  rather than restating the type name.
- Never put a secret, a token, or a full credential in an error message.
  Flag any that do.

**Binary**: a context-carrying opaque type is fine — `anyhow::Result` or
equivalent. `anyhow` in a library's public signature is a finding: it
removes the caller's ability to match on what went wrong.

**Panics** are for broken invariants in your own code, not for bad input.
In library code:

- Both `unwrap()` and `expect()` require a locally provable invariant.
  Prefer `expect`, whose argument states the invariant — `expect("validated
  at line 40")`. Bare `unwrap()` takes no message, so the invariant has to
  be stated in a comment instead; an `unwrap()` with neither is a finding.
  `unwrap()` on a parse of user input is **WRONG** either way.
- Document panics in a `# Panics` section.
- Indexing (`v[i]`) panics; prefer `get()` where the index comes from
  outside.
- Integer overflow panics in debug and wraps in release unless
  `overflow-checks` is on. Use `checked_`, `saturating_`, or `wrapping_`
  explicitly when the behavior matters. Silent reliance on release-mode
  wrapping is **WRONG**.

## Naming

Follow [RFC 430](https://rust-lang.github.io/api-guidelines/naming.html):
`UpperCamelCase` types and traits, `snake_case` functions and modules,
`SCREAMING_SNAKE_CASE` constants.

Conversion prefixes carry meaning, and getting them wrong misleads callers:

| Prefix | Cost | Ownership |
|---|---|---|
| `as_` | free | borrowed → borrowed |
| `to_` | expensive | borrowed → borrowed (`Path::to_str`), borrowed → owned (`str::to_owned`), or owned → owned for `Copy` types (`f64::to_degrees`) |
| `into_` | variable, consuming | owned → owned |

The full rule is C-CONV in the API Guidelines. The common mistake is naming a
cheap borrowed-to-borrowed conversion `to_` or an expensive one `as_`.

Other conventions: getters are `field()`, not `get_field()`; setters are
`set_field()`; iterator methods are `iter()`, `iter_mut()`, `into_iter()`;
`is_`/`has_` for predicates; `_mut` suffix for mutable variants;
`try_` prefix for fallible variants of infallible operations.

## Visibility and module structure

- Default to private. Every `pub` is a maintenance obligation.
- `pub(crate)` for internal sharing, `pub(super)` for parent-only.
- Re-export the crate's main types at the root so callers write
  `crate::Thing`, not `crate::internal::module::Thing`.
- Do not expose dependency types in your public API unless you intend to
  track their semver. A `pub fn` returning `reqwest::Response` makes
  `reqwest` part of your contract.
- Sealed traits (a `pub` trait with a `pub(crate)` supertrait) when you want
  to implement a trait for your types only.

## Semver hazards

The authoritative list, with the exact conditions, is the
[Cargo SemVer chapter](https://doc.rust-lang.org/cargo/reference/semver.html).
Check it rather than trusting this summary. The breaking changes that get
missed:

- Adding a variant to a public enum that is not `#[non_exhaustive]`.
- Adding a public field to a struct that has **no** private field, since
  that breaks existing struct literals and exhaustive patterns. If a private
  field already exists, or the struct is `#[non_exhaustive]`, the addition is
  minor. Making an existing private field public is additive.
- Adding a method to a public trait without a default body.
- Adding a **non-defaulted** type parameter, or adding a bound to an existing
  one. A defaulted type parameter, and some compatible generalizations, are
  minor.
- Narrowing an argument type, or widening a return type.
- Losing an auto trait: a type that was `Send` or `Sync` and now is not.
  This is the easiest one to do by accident, by adding an `Rc` internally.
- Changing a `Copy` type to non-`Copy`.
- Renaming a public item, including re-exports.
- Raising the MSRV. Treat as breaking unless the project says otherwise.

Recommend `cargo-semver-checks` when a release is in question, and say that
it does not catch everything.

## Documentation of the public surface

Doc comments are the lawyer's territory; prose documents are the editor's.

- `//!` at the crate root saying what the crate is for.
- `///` on every public item, first line a single sentence.
- A runnable example on every non-trivial public function. Examples are
  compiled and run by `cargo test`, so they do not rot.
- `# Errors` for anything returning `Result`, `# Panics` for anything that
  can panic, `# Safety` for every `unsafe fn`. Missing `# Safety` is
  **WRONG**, not stylistic.
- `#![warn(missing_docs)]` on libraries.
- Link items with intra-doc links (`[`Type::method`]`) rather than URLs.
