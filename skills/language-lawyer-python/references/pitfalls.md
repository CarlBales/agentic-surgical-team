# Python Pitfalls

These patterns recur in generated Python. Each entry states the usual label and the smallest repair.
Confirm intent, supported Python, implementation, and tool configuration before filing it.

## Characteristic of generated Python

**Hallucinated standard-library APIs — WRONG.** Generated code often calls a plausible method on the
wrong class, combines two real signatures, or imports a name that never existed. Verify every
unfamiliar name in the standard-library documentation for the project's exact minor. Replace it with
the documented API; do not add a dependency merely to preserve invented spelling.

**Version drift — WRONG.** Syntax and APIs remembered from a newer interpreter can violate
`requires-python`. Concrete boundaries include `tomllib` and `ExceptionGroup` in 3.11; the `type`
statement, `typing.override`, `pathlib.Path.walk`, and `itertools.batched` in 3.12; and the `strict`
parameter to `itertools.batched` in 3.13. Verify each boundary on its versioned docs. For an older
minimum, use an established backport only if already accepted, or write the compatible form. A CI
job on only the newest minor does not prove the minimum.

**Confident fake verification — protocol violation.** A generated report may say "mypy passes" or
reconstruct likely traceback text without a run. At L0, label all such output **predicted, not
run**. At L1, quote command, version, status, and decisive output.

**Annotations treated as runtime validation — WRONG.** `payload: Payload` does not parse a mapping
or reject a string. Validate at the trust boundary or rely on a framework only after establishing
its exact runtime behavior. Keep the type annotation as the static contract.

**Blanket suppressions — UNIDIOMATIC**, and **WRONG** when they hide a real defect. Generated fixes
reach for `# type: ignore`, `# noqa`, `cast(Any, ...)`, or a broad lint ignore. Fix the contract
first. If the tool is genuinely limited, use its narrow, verified suppression with a reason.

**Over-engineered abstraction — TASTE** until it imposes a concrete cost; then **UNIDIOMATIC**. A
metaclass, descriptor, registry, generic protocol, and factory for a local two-case branch is not
more Pythonic. Delete layers until each one serves a caller-visible variation.

**Comments that narrate syntax — UNIDIOMATIC.** `# Loop over items` above a `for` loop consumes
attention while lifecycle, units, cancellation, or invariant reasoning remains undocumented.
Preserve why, not what.

## Subprocesses and shell injection

Interpolating external text into a command executed with `shell=True` is **WRONG**:

```python
# WRONG: user_name can terminate the argument and add shell syntax.
subprocess.run(f"lookup --user {user_name}", shell=True, check=True)
```

Pass a sequence with the shell disabled:

```python
subprocess.run(["lookup", "--user", user_name], check=True)
```

Python 3.13's `subprocess` [Security
Considerations](https://docs.python.org/3.13/library/subprocess.html#security-considerations) state
that Python does not implicitly invoke a shell and that the application is responsible for quoting
shell metacharacters when it explicitly does. Sequence arguments let `subprocess` preserve argument
boundaries. `shlex.quote` is for POSIX shell syntax and is not a portable substitute for avoiding a
shell.

A constant command using shell grammar may be deliberate and is not automatically exploitable, but
it still deserves `S602` review. If a pipeline, glob, or redirect is required, prefer composing
processes and files directly. When a shell truly is the API, isolate the constant script and pass
external values out-of-band or quote them according to that exact shell. Hand broader threat
analysis to the security reviewer.

Always decide `check`, timeout, text/binary mode, encoding, environment, working directory, and
output bounds. Ignoring a nonzero return when success is required is **WRONG**. Capturing unbounded
attacker-controlled output can exhaust memory.

## Exceptions

**Bare `except:` — WRONG** in ordinary application paths. It catches `BaseException` subclasses such
as `KeyboardInterrupt` and `SystemExit`, and in modern Python also catches `asyncio.CancelledError`.
Catch the specific failure that can be recovered from. `except Exception` avoids process-control
exceptions but is still too broad unless the boundary deliberately translates or records unknown
application failures.

```python
try:
    value = parse(text)
except ParseError as exc:
    raise ConfigError("invalid service configuration") from exc
```

**Exception swallowed after logging — WRONG** when the caller depends on failure. Return an explicit
result or re-raise. Logging at every layer is **UNIDIOMATIC** because one failure becomes several
duplicate records.

**`raise exc` for an unchanged exception — UNIDIOMATIC.** A bare `raise` retains the natural
traceback. Use `raise NewError(...) from exc` when crossing an abstraction boundary. Do not use
`from None` merely to make generated output look cleaner.

**Control flow in `finally` — WRONG** when `return`, `break`, or `continue` suppresses a pending
exception. Put result selection outside cleanup. Cleanup itself should not mask the primary failure;
preserve both when needed.

## Defaults, identity, and shared state

**Mutable argument default — WRONG** when calls should be independent. Defaults are created once at
function definition. Ruff calls this `B006`. Use `None` or a private sentinel and construct inside,
or use `dataclasses.field(default_factory=...)` for dataclass fields. Do not rewrite an intentional
shared cache without first establishing its contract.

**`value == None` — UNIDIOMATIC.** Use `value is None`; equality may be overloaded and `None` is a
singleton sentinel. Ruff/pycodestyle code `E711` describes this.

**`value is 0` or `name is "ready"` — WRONG** when value equality is intended. Object identity and
value equality differ; interning can make the bug appear to work on one runtime. Use `==` for values
and `is` only for identity sentinels such as `None` or a private `object()`.

**Shared class-level mutable collection — WRONG** when each instance should own one. Initialize it
on `self` or use a dataclass `default_factory`. A frozen dataclass is not deeply immutable; a list
field can still mutate.

**Shallow copy assumed independent — WRONG.** `dict.copy`, slicing, and `copy.copy` preserve
references to nested values. Construct the required nested state or use `deepcopy` only after
confirming its identity and performance semantics.

**`value or fallback` when falsy values are valid — WRONG.** It replaces `0`, `False`, `""`, and
empty containers. Test `is None` or membership in an explicit sentinel set according to the
contract.

## Time and dates

**Mixing naive and aware datetimes — WRONG.** Ordering comparisons can raise `TypeError`, and
silently assigning local meaning to a naive timestamp produces wrong instants. Define whether the
boundary accepts an instant, civil local time, or date. Use aware UTC for instants and
`zoneinfo.ZoneInfo` for named civil zones.

`datetime.replace(tzinfo=...)` attaches metadata; it does not convert an instant. Use `astimezone`
for conversion after the source instant is correctly defined. `datetime.UTC` is available from
Python 3.11; use `datetime.timezone.utc` when the supported minimum is older. Parsing an offset is
not the same as preserving an IANA zone and its daylight-saving rules.

Calling `datetime.now()` without a zone is **UNIDIOMATIC** where an instant is required and
**WRONG** when code later labels it UTC. Inject a clock where tests or consistency require control,
but do not build a clock abstraction for code that genuinely wants a one-off local display time.

## Numbers and money

**Binary float for exact money — WRONG** when decimal amounts, rounding rules, or ledger equality
are contractual. Use integer minor units or `decimal.Decimal` with an explicit rounding and
quantization policy. Construct `Decimal` from a string or integer, not from an already-rounded
binary float.

Float is correct for measurements and numerical work. Replacing every float with Decimal is
**UNIDIOMATIC** and can still be wrong without a precision context. For computed floats, exact `==`
is usually wrong; choose a domain tolerance or `math.isclose` parameters justified by scale. NaN is
not equal to itself.

**Implicit truncation with `int(value)` — WRONG** when rejection or rounding was required. Name the
policy: floor, ceiling, nearest with tie behavior, or parse an integer-only representation.

## Paths, files, and text

**Manual `os.path` plumbing — UNIDIOMATIC** in new code when `pathlib.Path` expresses joining,
suffixes, parents, iteration, and I/O directly. `os.path` is not wrong and can be appropriate in
established code or low-level string APIs. Do not churn a module solely to switch styles.

**String concatenation for paths — WRONG** when it assumes `/`, drops roots, or misreads drive
semantics. Use `Path` or the appropriate `os.path` operation. A filesystem path is not a URL; do not
send URL text through `Path`.

**`open(path)` without an encoding — WRONG** for a portable text file whose encoding is part of the
format, because the default is locale-dependent. Use `encoding="utf-8"` or the format's specified
encoding. Leave encoding absent for binary mode. Error handling (`strict`, `replace`, or another
policy) is part of the contract, not a cleanup detail.

Use a context manager for deterministic close. A small function that immediately returns
`Path.read_text(encoding="utf-8")` does not need a hand-written `with`; that choice is **TASTE**.
For atomic replacement, write a sibling temporary, flush as required by durability policy, and
replace; platform semantics need a platform lawyer when they are contractual.

**Unchecked path containment — WRONG** when untrusted components can escape an allowed root. `Path`
alone does not prevent `..`, absolute replacement, symlink races, or case/normalization surprises.
Escalate threat-sensitive designs.

## Built-ins, imports, and iteration

**Shadowing `list`, `dict`, `id`, `type`, `input`, or `format` — UNIDIOMATIC.** It makes later calls
fail or confuses readers and tools. Ruff's real rule `A001` covers variable shadowing when selected.
Rename to the domain noun; do not use an awkward suffix if a precise noun exists.

**Modifying a collection while iterating — WRONG** when it skips entries, raises, or violates the
intended traversal. Iterate over a deliberate snapshot or build a new collection. Mutation of values
while iterating mapping keys may be valid; classify the exact operation.

**Iterator consumed twice — WRONG** when the second consumer expects values. Iterators are normally
single-pass. Accept a reusable `Iterable`, materialize once with a stated memory cost, or document
consumption.

**Import-time environment reads cached forever — WRONG** when tests or runtime configuration expect
changes, and **UNIDIOMATIC** when it makes import order part of behavior. Read at a defined
application boundary and pass configuration. Constants derived from immutable deployment settings
can be legitimate.

**Circular import repaired with scattered local imports — UNIDIOMATIC.** A local import can be the
right lazy boundary, but generated code often hides a module dependency cycle. Move shared contracts
down a layer, use `TYPE_CHECKING` only for type-only imports, or redesign the ownership edge.

## Async and concurrency

**Coroutine created but not awaited — WRONG.** Calling `async def` does not run it. Await it or
create a task whose lifetime and result are owned. Do not silence the resulting warning by
discarding the object.

**Fire-and-forget task with no strong owner — WRONG** when completion matters. Keep a reference,
observe exceptions, and cancel/await during shutdown. Prefer a `TaskGroup` on Python 3.11+ for
related work.

**Blocking operation in async code — WRONG** when it stalls the event loop. Use an async API or
deliberately offload blocking work, while preserving context, cancellation expectations, and
shutdown. `asyncio.to_thread` does not make CPU-bound Python parallel on an ordinary GIL-enabled
CPython build.

**CancelledError swallowed — WRONG.** Clean up in `finally` and normally re-raise. Catching it as
ordinary failure can break timeouts and structured concurrency. If suppression is intentional,
follow the exact versioned asyncio contract and make task state explicit.

**"The GIL makes this thread-safe" — WRONG** as a general argument. Protect the multi-step invariant
with synchronization. CPython 3.13's experimental free-threaded build removes even the usual
implementation assumption and can run extension code under different GIL state.

## Review finish

Before closing a review, search every unfamiliar import, method, argument, Ruff code, checker
diagnostic, and "added in" claim in authoritative documentation for the baseline. Generated Python
is fluent enough that invented details look ordinary. If verification needs execution or external
access the order lacks, put the item under `Unverified`; do not turn confidence into evidence.
