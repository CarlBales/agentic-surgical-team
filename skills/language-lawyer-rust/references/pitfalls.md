# Rust Pitfalls

Findings that recur. The first section covers mistakes characteristic of
generated code, which is most of what this team reviews.

Each entry: the pattern, its label, and the fix.

## Characteristic of generated Rust

**Hallucinated APIs.** A plausible method that does not exist, a crate
feature that was never added, a `clippy` lint with an invented name, or a
`std` function attributed to the wrong type. **WRONG.** Verify every
unfamiliar API against `std` docs or `cargo doc`. This is the single most
common defect in generated Rust, and it is invisible until compile.

**Version drift.** Code written against a different major version of
`tokio`, `axum`, `clap`, `rand`, or `serde` than the project uses. **WRONG.**
Check `Cargo.toml` and the crate's changelog before reviewing against
remembered APIs.

**`clone()` as a borrow-checker escape.** Compiles, and hides a design
problem. The cost is type-dependent — `Arc::clone` is a refcount bump, a
`Vec` clone is an allocation and a copy — so judge it by what is being
cloned and how often. **UNIDIOMATIC.** Narrow the borrow, split the struct,
or own the data deliberately at a boundary.

**`Arc<Mutex<T>>` everywhere.** Reached for before asking whether the data
needs sharing at all. **UNIDIOMATIC.** Consider ownership transfer, channels,
or `&mut` through a single owner first.

**`unwrap()` on a value whose success is not locally proven.** Especially on
parsing, locking, and environment access. **WRONG** in a library when the
invariant is not established and documented; **UNIDIOMATIC** in a binary
outside `main`. `expect("validated at line 40")` where the validation really
is right there is acceptable. Return a typed error otherwise.

**`String` where `&str` belongs**, in both parameters and struct fields.
**UNIDIOMATIC.** `clippy::ptr_arg` catches the parameter case.

**Over-engineered generics.** Three type parameters and a trait bound where
a concrete type was sufficient. **TASTE** at worst, **UNIDIOMATIC** when it
makes the API unusable. Generated code tends to add abstraction preemptively.

**Over-commented obvious code.** `// increment i` above `i += 1`, while the
`unsafe` block has no comment at all. **UNIDIOMATIC.** Comments belong where
the reasoning is non-obvious.

**Fabricated verification.** A report claiming tests pass without having run
them. Protocol violation, not a language finding. Report what was actually
executed.

**Invented `unsafe` justification.** An `unsafe` block with a confident
comment that does not actually establish the invariant. **WRONG.** The
comment must name the specific guarantee and why it holds here.

## Ownership and borrowing

**`Rc<RefCell<T>>` graphs.** Reimplementing a mutable object graph.
**UNIDIOMATIC.** Consider an arena with index handles, or restructuring so
ownership is a tree.

**`&mut self` where `&self` with interior mutability was intended**, or the
reverse. Think about whether callers need concurrent access.

**Collecting to drop the borrow.** `let keys: Vec<_> = map.keys().cloned().collect();`
then mutating `map`. Correct, sometimes necessary. **TASTE** if the
collection is small, **UNIDIOMATIC** if `retain` or `drain` would do it in
place.

**Fighting the iterator invalidation rule with indices.** Sometimes right.
Flag only when `split_at_mut`, `iter_mut`, `chunks_mut`, or `windows` does
it safely.

**Struct holding both a value and a reference into it.** Not expressible
safely. **WRONG** if attempted with `unsafe`; redesign or use a crate built
for it, cited.

## Error handling

**`Box<dyn Error>` in a library's public API.** **UNIDIOMATIC.** Callers
cannot match on it. Use a concrete enum.

**`anyhow` in a library signature.** Same problem. `anyhow` is for binaries.

**Swallowed errors.** `let _ = fallible();` or a `match` arm that logs and
continues without recording the failure. **WRONG** when the caller needed to
know.

**`?` with a `From` impl that loses information.** Converting a specific
error into a generic one at the `?` site discards the cause. Keep it with
`#[source]`.

**Secrets in error messages.** A token, password, connection string, or full
request body in a `Display` impl. **WRONG.** Redact.

**`unwrap()` on a `Mutex` lock.** Common and usually accepted, since
poisoning means another thread panicked. Acceptable with a comment;
**UNIDIOMATIC** without one.

**Panicking on invalid input.** Input validation returns `Result`. Panics are
for broken internal invariants.

## Integers and conversions

**`as` casts that truncate silently.** `len as u32`, `i64 as usize`.
**WRONG** when the value can exceed the target range. Use `try_into()` and
handle the error, or `u32::try_from(..)`.

**Relying on release-mode wrapping.** Overflow panics in debug and wraps in
release. **WRONG** unless `wrapping_*` is written explicitly.

**`usize` assumed to be 64-bit.** Breaks on 32-bit and wasm targets.

**Float equality on computed results.** `a == b` where either side is the
result of arithmetic. **UNIDIOMATIC**; compare with a tolerance chosen for
the domain — absolute, relative, or ULP — and remember NaN is never equal to
itself. Exact comparison is fine against zero, against sentinels, and inside
a `PartialEq` impl, which is why `clippy::float_cmp` exempts those cases.

**`.len()` as a byte count treated as a character count.** `String::len` is
bytes. Indexing a `&str` at a non-boundary panics. Use `chars().count()`
when you mean characters, and know that is not graphemes either.

## Async

**`.await` while holding a `std::sync::MutexGuard`.** The guard is not
`Send`, so the future is not `Send` and will not compile where a `Send`
future is required. Even where it does compile, the lock is held across a
suspension point, so a contending task on the same thread can deadlock and
others block. **WRONG** whenever the future must be `Send` or contention is
possible. Drop the guard before awaiting, or use an async mutex.
`clippy::await_holding_lock` flags the risk.

**Blocking calls in an async fn.** File I/O, `std::thread::sleep`, a
synchronous HTTP client, or CPU-heavy work. **WRONG.** It starves the
executor. Use `spawn_blocking` or the async equivalent.

**Cancellation unsafety.** A future that leaves state inconsistent when
dropped at an await point. Appears with `select!` and with timeouts.
**WRONG** when the inconsistency is observable. Ask of every `.await`: what
if we never come back here?

**Unbounded channels.** Unbounded memory growth under load. **UNIDIOMATIC**
at best; bound the channel and decide what happens when it is full.

**Forgotten `JoinHandle`.** A spawned task whose handle is dropped runs
detached, and its panic disappears. Flag it.

**`async fn` in a public trait without thought.** Its desugaring affects
object safety and `Send` bounds. Know what the project expects before
recommending.

**Mixed runtimes.** Two executors in one process, usually from a dependency
pulling in a second one. Check `cargo tree`.

## Traits and types

**`Deref` for code reuse.** Not inheritance. **UNIDIOMATIC.** Use composition
and explicit methods.

**Blanket impls that conflict.** `impl<T: Foo> Bar for T` forecloses future
impls and collides with other crates' blankets. Coherence errors here are
not fixable later; flag before it ships.

**Orphan rule violations.** Cannot implement a foreign trait for a foreign
type. The fix is a newtype wrapper.

**Derived `Ord` on an enum.** Order follows declaration order. Reordering
variants silently changes behavior. Flag when the order is semantically
meaningful.

**`Hash` and `Eq` disagreeing.** Breaks `HashMap`. **WRONG.**

**`PartialEq` that is not transitive**, or a `Hash` impl covering a subset of
the `Eq` fields. **WRONG.**

**`impl Trait` in a public return type** when callers need to name it, or a
concrete type where flexibility was wanted. Judgment call; state the
trade-off.

## Collections and iterators

**`collect()` then `into_iter()`.** `clippy::needless_collect`.

**`for i in 0..v.len()` with `v[i]`.** **UNIDIOMATIC** where `iter()` reads
better. Do not justify it on bounds-check cost; LLVM usually removes those
for this exact pattern.

**`HashMap` iteration order assumed stable.** It is not. Use `BTreeMap` when
order matters.

**`Vec::remove(0)` in a loop.** O(n²). Use `VecDeque`.

**`contains` on a `Vec` in a loop.** O(n·m). Use a `HashSet`.

**Missing `with_capacity`** when the size is known. **TASTE** in cold code.

**`sort()` where `sort_unstable()` is fine.** `sort_unstable` sorts in place
with no allocation; the `std` docs describe it as typically faster, while
noting `sort` can win on partially sorted data. Treat the speed difference
as unmeasured. **TASTE** unless you benchmarked it.

**`iter().nth(n)` instead of indexing** a slice. **UNIDIOMATIC.**

## Macros, modules, and build

**`macro_rules!` where a function would do.** **UNIDIOMATIC.** Macros resist
tooling, inference, and readers.

**`#[macro_export]` without namespacing.** Pollutes the crate root of every
consumer.

**`mod.rs` versus `name.rs`.** Both work. Match the project. **TASTE.**

**`pub use` creating two public paths to one type.** Confusing in docs, and
both paths become semver commitments.

**`build.rs` with incomplete `cargo::rerun-if-changed`.** By default Cargo
reruns the script when any file in the package changes, which is broad but
safe. Emitting directives narrows that — and an incomplete set then misses
inputs outside the package, such as a vendored C source or a generated
schema, so the build goes stale silently.

**`#[allow(dead_code)]` masking a real problem.** Ask whether the code is
reachable at all.

## Testing

Test design belongs to the tester; these are the language-level findings.

**`#[test]` functions that `unwrap()` with no message.** Failure output is
useless. **UNIDIOMATIC.**

**Doc examples marked `ignore` to avoid fixing them.** `ignore` means neither
compiled nor run, so the example rots silently. **UNIDIOMATIC** unless there
is a stated reason. `no_run` is different: rustdoc still compiles it and only
skips execution, which is the right marker for an example that would open a
socket or delete a file.

**`#[cfg(test)]` helpers that drift from production code paths.**

**Tests that depend on `HashMap` iteration order** or on wall-clock time.
Flaky by construction. **WRONG.**
