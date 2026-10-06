# Ownership, Lifetimes, and Soundness

The hard part of Rust, and the part the surgeon most often needs a lawyer
for. Everything here is a judgment aid, not a substitute for reading
[the Reference](https://doc.rust-lang.org/reference/) and
[the Rustonomicon](https://doc.rust-lang.org/nomicon/).

## Reading borrow checker errors

The borrow checker enforces one rule: at any point, a value has either one
mutable reference or any number of shared references, never both. Most
errors are that rule plus the question of how long a reference lives.

| Code | Says | Usually means |
|---|---|---|
| `E0499` | two mutable borrows at once | the data should be split, indexed differently, or an index used instead of a reference |
| `E0502` | mutable and immutable borrow overlap | the read and the write want to be sequenced, or the read should be copied out first |
| `E0505` | moved while borrowed | the borrow's scope is wider than intended |
| `E0506` | assigned to a borrowed value | restructure, or use `std::mem::replace`/`take` |
| `E0597` | does not live long enough | the value wants to be **owned**, not borrowed |
| `E0515` | returns a reference to a local | return the owned value, or take a reference parameter to write into |
| `E0716` | temporary dropped while borrowed | bind the temporary to a `let` first |
| `E0373` | closure may outlive the current function | `move` the closure, or clone an `Arc` into it |
| `E0521` | borrowed data escapes | the spawned task needs owned or `'static` data |

The fix hierarchy, best to worst:

1. **Restructure so the borrow is narrower.** Shorter scopes, earlier
   `drop`, splitting a struct so disjoint fields are borrowed separately,
   using `split_at_mut` or `iter_mut` instead of indexing.
2. **Own the data.** Clone once at a boundary, or take ownership in the
   signature. Honest and cheap in most code.
3. **Interior mutability.** `Cell`, `RefCell`, `Mutex`, `RwLock`, chosen for
   the actual concurrency need.
4. **`unsafe`.** Almost never the right answer to a borrow error.

Two notes on borrowck itself: NLL means a borrow ends at its last use, not
at the end of the block, so the error points at a real overlap, not a
scoping artifact. And borrowck is per-function; errors that look
cross-function are really about the signature.

## Lifetime annotations

Lifetimes describe relationships that already exist. They never extend how
long data lives.

- Elision covers most signatures. Adding explicit lifetimes where elision
  would do is **UNIDIOMATIC** noise.
- `&'a mut T` is invariant in `T`. This is the source of the "lifetime may
  not live long enough" errors that look inexplicable.
- `'static` as a bound means "contains no non-`'static` references," not
  "lives forever." `String` is `'static`. Adding `'static` to silence an
  error is usually the wrong fix; it is the right fix for spawned tasks that
  genuinely need owned data.
- Higher-ranked bounds (`for<'a> Fn(&'a str) -> &'a str`) appear when a
  closure must work for any lifetime. If one shows up in an error, the
  closure signature is usually underconstrained.
- A struct holding a reference infects everything that holds it. Before
  adding a lifetime parameter to a struct, ask whether it should own instead.
  Self-referential structs are not expressible safely; that is what `Pin`
  and the `ouroboros`-style crates exist for.

## Interior mutability

| Type | Use when | Cost / hazard |
|---|---|---|
| `Cell<T>` | `T: Copy`, single-threaded, get/set only | no borrows handed out |
| `RefCell<T>` | single-threaded, need `&mut` through `&` | **panics** on borrow conflict at runtime |
| `OnceCell` / `OnceLock` | initialize once, read many | `OnceLock` for cross-thread |
| `Mutex<T>` | cross-thread exclusive access | poisoning on panic; deadlock if lock order is inconsistent |
| `RwLock<T>` | many readers, rare writer | writer starvation; worse than `Mutex` under write load |
| `Atomic*` | single values, lock-free counters and flags | ordering is subtle; see below |

`RefCell` in a library's public path is a finding: it converts a compile-time
error into a runtime panic for the caller. `Rc<RefCell<T>>` as a pervasive
pattern usually means the ownership graph was never designed.

Atomic orderings: use `SeqCst` unless you can state the happens-before
relationship you need. `Relaxed` is correct for independent counters.
`Acquire`/`Release` pair to publish data written before the release. Anything
cleverer needs a written argument in a comment, and Miri or Loom to check it.

## `Send` and `Sync`

- `Send`: safe to move to another thread. `Sync`: safe to share by reference.
- Both are auto traits, derived structurally. You almost never implement them
  by hand. A manual `unsafe impl Send for T {}` is a **WRONG** finding unless
  there is a documented argument for why the invariant holds.
- `Rc<T>` is neither. `RefCell<T>` is `Send` when `T: Send`, and never
  `Sync`. `MutexGuard` is not `Send`. Raw pointers are neither, which is why
  wrapper types around FFI handles so often need a hand-written impl — and
  why those are where soundness bugs live.
- A "future is not `Send`" error in async code usually means a
  non-`Send` guard or `Rc` is held across an `.await`.

## `unsafe` review

Every `unsafe` block is a claim that the author has checked something the
compiler cannot. Review it as a claim.

Checklist:

- [ ] Is there a comment stating **which** invariant is being upheld, and
      why it holds here? Missing comment is a finding on its own.
- [ ] Does every `unsafe fn` have a `# Safety` section naming the caller's
      obligations?
- [ ] Can a **safe** caller of the surrounding API break the invariant? If
      yes, the API is unsound regardless of the block's internal correctness.
      This is the most important question.
- [ ] Is the `unsafe` block as small as possible, or does it wrap safe code
      too?
- [ ] Pointers: non-null, aligned, dereferenceable, pointing at an
      initialized value of the right type, within the same allocation?
- [ ] Aliasing: no `&mut` coexisting with any other reference to the same
      data, including through raw pointers?
- [ ] Is `transmute` used where the layout is not guaranteed? The Reference
      guarantees field alignment, aggregate alignment, and non-overlapping
      fields for `#[repr(Rust)]`, but **not** field order or ABI, so code
      that assumes a mapping is relying on the unspecified part. Between
      references of different lifetimes, `transmute` is laundering the
      borrow checker.
- [ ] `MaybeUninit` used for anything not yet initialized, rather than
      `mem::uninitialized` or a zeroed value?
- [ ] For `Pin`: is the pinning contract maintained, and is `get_unchecked_mut`
      justified?
- [ ] Panic safety: if user code panics mid-operation, is the data structure
      left in a valid state? Unwinding through `unsafe` is where leaks and
      double-frees come from.
- [ ] FFI: is every `extern` signature exactly right, including `repr`,
      nullability, ownership of returned pointers, and who frees?

Undefined behavior, non-exhaustively: data races; dereferencing null,
dangling, unaligned, or out-of-bounds pointers; producing an invalid value
(a `bool` that is not 0 or 1, an invalid `char`, an uninhabited type, a
niche-violating enum discriminant); breaking aliasing rules; calling a
function with a mismatched signature; unwinding across an FFI boundary that
does not allow it; mutating a shared `&T` without interior mutability.

UB is not "it might behave oddly." It licenses the compiler to do anything,
including miscompiling unrelated code. Report it as **WRONG**, always.

Verification: `cargo +nightly miri test` catches a large fraction of UB in
code reachable from tests. If you recommend `unsafe`, recommend Miri with
it. Say when a finding is unverified because you could not run Miri.

## Common unsound patterns

- `unsafe impl Send`/`Sync` on a type containing a raw pointer, with no
  argument for why.
- Returning `&'a T` derived from a raw pointer whose allocation is not tied
  to `'a`.
- `transmute` to change a lifetime, or between `&T` and `&mut T`.
- Holding a `&mut` into a collection across an operation that may reallocate.
- `mem::transmute::<&[u8], &[T]>` without alignment and validity checks; use
  `bytemuck` or `zerocopy` instead and cite them.
- `std::str::from_utf8_unchecked` on bytes that were not validated.
- `get_unchecked` with an index derived from untrusted input.
- An FFI callback that can unwind into C.
- `Drop` that assumes it runs; `mem::forget` and leaks are safe in Rust, so
  soundness must never depend on a destructor running.
