"""Local Wolfram Engine kernel pool (ARCHITECTURE.md §5.2).

DeltaForge runs a **local Wolfram Engine 14.3 kernel** (free dev license) via
``wolframclient``'s process-based ``WolframLanguageSession``. There is NO Wolfram
Cloud and NO Secured Authentication Key — the "trust anchor" engine value is
``wolfram`` (a real local kernel ran it). Key behaviors:

  - ``wolframclient`` is an OPTIONAL import — guarded so this module imports even
    when the package is absent. With no package (or no kernel binary on disk),
    the pool starts in ``numeric_fallback`` mode and NEVER crashes.
  - Local kernels are heavy OS processes, so each kernel runs on a dedicated
    worker thread of a ``ThreadPoolExecutor`` and is driven synchronously there.
    The async API wraps every call in ``loop.run_in_executor`` + ``wait_for`` so
    timeouts and the FastAPI event loop stay clean.
  - A ``BoundedSemaphore`` (size = pool size) leases one kernel per
    ``async with pool.acquire()``.
  - A kernel that crashes/errors during use is poisoned (terminated + discarded)
    and lazily replaced on the next acquisition.
  - If ZERO kernels start, the service flips to ``numeric_fallback`` and logs
    CRITICAL.

This module never raises out of normal operation; callers treat
``KernelUnavailable`` / ``KernelEvalError`` as signals to degrade to fallback.
"""

from __future__ import annotations

import asyncio
import logging
import random
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable

from core.wolfram_settings import WolframSettings

logger = logging.getLogger(__name__)

# ── Optional wolframclient import (guarded) ───────────────────────────────────
WOLFRAMCLIENT_AVAILABLE = False
_IMPORT_ERROR: str | None = None
try:  # pragma: no cover - exercised only when the package is installed
    from wolframclient.evaluation import (  # type: ignore[import-not-found]
        WolframLanguageSession,
    )
    from wolframclient.exception import (  # type: ignore[import-not-found]
        WolframLanguageException,
    )

    WOLFRAMCLIENT_AVAILABLE = True
except ImportError as exc:  # pragma: no cover - default in dev without the dep
    WolframLanguageSession = None  # type: ignore[assignment,misc]

    class WolframLanguageException(Exception):  # type: ignore[no-redef]
        """Stand-in so ``except WolframLanguageException`` is always valid."""

    _IMPORT_ERROR = str(exc)
    logger.info(
        "wolframclient not installed (%s); pool will run in numeric_fallback mode",
        _IMPORT_ERROR,
    )


# ── Error taxonomy ────────────────────────────────────────────────────────────


class KernelUnavailable(RuntimeError):
    """No usable kernel (no package, no binary, or all kernels dead)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class KernelEvalError(RuntimeError):
    """A deterministic kernel/math error (WL message). NOT retried."""

    def __init__(self, message: str, wl_messages: tuple[tuple[str, str], ...]) -> None:
        super().__init__(message)
        self.wl_messages = wl_messages


@dataclass
class EvalOutcome:
    """Result of a wrapped kernel evaluation."""

    value: Any
    wl_output: str | None
    messages: tuple[tuple[str, str], ...]
    kernel_ms: float


# Transient transport/process errors that justify a retry.
def _transient_error_types() -> tuple[type[BaseException], ...]:
    types: list[type[BaseException]] = [
        asyncio.TimeoutError,
        ConnectionError,
        OSError,
        BrokenPipeError,
    ]
    try:  # pragma: no cover - depends on wolframclient internals
        from wolframclient.evaluation.kernel.kernelsession import (  # type: ignore
            WolframKernelException,
        )

        types.append(WolframKernelException)
    except Exception:  # noqa: BLE001 - best-effort enrichment only
        pass
    return tuple(types)


_TRANSIENT = _transient_error_types()


@dataclass
class _Kernel:
    """A single local kernel bound to one dedicated worker thread.

    ``executor`` is a 1-worker pool so all calls to this kernel are serialized
    on the SAME OS thread (``WolframLanguageSession`` is not thread-safe).
    """

    session: Any
    executor: ThreadPoolExecutor


class WolframSessionPool:
    """Bounded pool of local Wolfram Engine kernels driven off the event loop."""

    def __init__(self, settings: WolframSettings) -> None:
        self._settings = settings
        self._semaphore = asyncio.BoundedSemaphore(settings.wolfram_pool_size)
        self._idle: list[_Kernel] = []
        self._lock = asyncio.Lock()
        self._started = False
        self._live_mode = False  # True only when >=1 kernel started
        self._reason: str | None = None
        self._healthy_count = 0

    # ── Lifecycle ────────────────────────────────────────────────────────────

    @property
    def live_mode(self) -> bool:
        """True iff at least one real local kernel is available."""
        return self._live_mode

    @property
    def reason(self) -> str | None:
        """Why the pool is not live (None when live)."""
        return self._reason

    @property
    def pool_size(self) -> int:
        return self._settings.wolfram_pool_size

    @property
    def healthy_sessions(self) -> int:
        return self._healthy_count

    async def start(self) -> None:
        """Pre-start ``pool_size`` kernels. Never raises; degrades gracefully."""
        async with self._lock:
            if self._started:
                return
            self._started = True

            if not self._settings.wolfram_enabled:
                self._reason = "kill_switch"
                self._live_mode = False
                logger.warning("Wolfram kill-switch active; numeric_fallback mode")
                return
            if not WOLFRAMCLIENT_AVAILABLE:
                self._reason = "kernel_unavailable"
                self._live_mode = False
                logger.warning(
                    "wolframclient unavailable; numeric_fallback mode (%s)",
                    _IMPORT_ERROR,
                )
                return
            if not self._settings.kernel_path_exists():
                self._reason = "kernel_unavailable"
                self._live_mode = False
                logger.warning(
                    "Wolfram kernel binary not found at %s; numeric_fallback mode",
                    self._settings.resolved_kernel_path(),
                )
                return

            created = 0
            for _ in range(self._settings.wolfram_pool_size):
                kernel = await self._create_kernel()
                if kernel is not None:
                    self._idle.append(kernel)
                    created += 1

            self._healthy_count = created
            if created == 0:
                self._reason = "kernel_unavailable"
                self._live_mode = False
                logger.critical(
                    "Zero Wolfram kernels started; flipping to numeric_fallback"
                )
            else:
                self._live_mode = True
                self._reason = None
                logger.info(
                    "Wolfram kernel pool live with %d/%d kernels",
                    created,
                    self._settings.wolfram_pool_size,
                )

    async def _create_kernel(self) -> _Kernel | None:
        """Create + start one local kernel on its own worker thread.

        Returns ``None`` on any failure (the pool degrades rather than crashing).
        """
        if not WOLFRAMCLIENT_AVAILABLE:
            return None
        kernel_path = self._settings.resolved_kernel_path()
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="wl-kernel")

        def _build_and_start() -> Any:
            session = WolframLanguageSession(kernel_path)
            session.start(block=True)  # block until the kernel is ready
            return session

        loop = asyncio.get_event_loop()
        try:
            session = await asyncio.wait_for(
                loop.run_in_executor(executor, _build_and_start),
                timeout=self._settings.wolfram_connect_timeout_s,
            )
            return _Kernel(session=session, executor=executor)
        except asyncio.TimeoutError:
            logger.error(
                "Timed out starting Wolfram kernel (%.1fs)",
                self._settings.wolfram_connect_timeout_s,
            )
            executor.shutdown(wait=False, cancel_futures=True)
            return None
        except Exception as exc:  # noqa: BLE001 - never let pool init crash app
            logger.exception("Error starting Wolfram kernel: %s", exc)
            executor.shutdown(wait=False, cancel_futures=True)
            return None

    async def stop(self) -> None:
        """Terminate all kernels. Idempotent and exception-safe."""
        async with self._lock:
            kernels = list(self._idle)
            self._idle.clear()
            self._healthy_count = 0
            self._live_mode = False
            self._started = False
        for kernel in kernels:
            await self._safe_terminate(kernel)

    async def _safe_terminate(self, kernel: _Kernel) -> None:
        loop = asyncio.get_event_loop()
        try:
            await asyncio.wait_for(
                loop.run_in_executor(kernel.executor, kernel.session.terminate),
                timeout=self._settings.wolfram_connect_timeout_s,
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("Error terminating Wolfram kernel: %s", exc)
        finally:
            kernel.executor.shutdown(wait=False, cancel_futures=True)

    # ── Leasing ──────────────────────────────────────────────────────────────

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[_Kernel]:
        """Lease a healthy kernel. Raises ``KernelUnavailable`` if none.

        A kernel that errors during use is poisoned (terminated + not returned)
        and lazily replaced on the next acquisition.
        """
        if not self._live_mode:
            raise KernelUnavailable(self._reason or "kernel_unavailable")

        await self._semaphore.acquire()
        kernel = await self._checkout()
        if kernel is None:
            self._semaphore.release()
            raise KernelUnavailable(self._reason or "kernel_unavailable")

        poisoned = False
        try:
            yield kernel
        except (KernelUnavailable, KernelEvalError):
            raise
        except Exception:
            poisoned = True
            raise
        finally:
            if poisoned:
                await self._poison(kernel)
            else:
                await self._checkin(kernel)
            self._semaphore.release()

    async def _checkout(self) -> _Kernel | None:
        async with self._lock:
            if self._idle:
                return self._idle.pop()
        # Lazily (re)create a replacement if the pool drained.
        kernel = await self._create_kernel()
        if kernel is not None:
            async with self._lock:
                self._healthy_count += 1
        return kernel

    async def _checkin(self, kernel: _Kernel) -> None:
        async with self._lock:
            self._idle.append(kernel)

    async def _poison(self, kernel: _Kernel) -> None:
        async with self._lock:
            self._healthy_count = max(0, self._healthy_count - 1)
            if self._healthy_count == 0 and not self._idle:
                self._live_mode = False
                self._reason = "kernel_unavailable"
                logger.critical("All Wolfram kernels poisoned; numeric_fallback mode")
        await self._safe_terminate(kernel)

    # ── Evaluation ───────────────────────────────────────────────────────────

    async def evaluate(self, operation: str, payload_expr: str) -> EvalOutcome:
        """Evaluate ``payload_expr`` capturing value + verbatim InputForm.

        Wraps the payload as
        ``<|"value" -> (expr), "form" -> ToString[(expr), InputForm]|>`` and uses
        the kernel's ``evaluate_wrap`` so kernel messages are exposed. Any message
        ⇒ failure (``KernelEvalError``, NOT retried). Transport/process errors are
        retried with exponential backoff + jitter up to ``wolfram_max_retries``.
        """
        # Quiet only KNOWN-BENIGN numeric messages (underflow / precision /
        # infinities that Black-Scholes legitimately produces for deep OTM/ITM
        # strikes across a full chain). ANY other message still surfaces and
        # fails the eval, so verifiability is preserved — we only stop correct
        # kernel results from being discarded over benign numeric noise.
        _BENIGN_MSGS = (
            "{General::munfl, General::ovfl, General::meprec, "
            "N::meprec, Power::infy, Infinity::indet}"
        )
        wrapped = (
            '<|"value" -> Quiet[(' + payload_expr + "), " + _BENIGN_MSGS + "], "
            '"form" -> ToString[(' + payload_expr + "), InputForm]|>"
        )

        attempt = 0
        last_exc: BaseException | None = None
        while attempt <= self._settings.wolfram_max_retries:
            try:
                return await self._evaluate_once(wrapped)
            except KernelEvalError:
                raise  # deterministic — do not retry
            except _TRANSIENT as exc:
                last_exc = exc
                attempt += 1
                if attempt > self._settings.wolfram_max_retries:
                    break
                backoff = min(2.0**attempt, 8.0) * (0.5 + random.random())
                logger.warning(
                    "Transient Wolfram error (attempt %d/%d) for %s: %s; backoff %.2fs",
                    attempt,
                    self._settings.wolfram_max_retries,
                    operation,
                    exc,
                    backoff,
                )
                await asyncio.sleep(backoff)
        raise KernelUnavailable(f"eval_timeout: {last_exc}")

    async def _evaluate_once(self, wrapped_expr: str) -> EvalOutcome:
        loop = asyncio.get_event_loop()
        start = loop.time()
        async with self.acquire() as kernel:
            call: Callable[[], Any] = lambda: _kernel_evaluate_wrap(
                kernel.session, wrapped_expr
            )
            try:
                result = await asyncio.wait_for(
                    loop.run_in_executor(kernel.executor, call),
                    timeout=self._settings.wolfram_eval_timeout_s,
                )
            except asyncio.TimeoutError as exc:
                # acquire()'s finally poisons the kernel via the _TRANSIENT path.
                raise asyncio.TimeoutError("evaluate_wrap timed out") from exc

            kernel_ms = (loop.time() - start) * 1000.0
            messages = _extract_messages(result)
            if messages:
                raise KernelEvalError(f"kernel returned messages: {messages}", messages)
            value, wl_output = _extract_value_and_form(result)
            return EvalOutcome(
                value=value,
                wl_output=wl_output,
                messages=messages,
                kernel_ms=kernel_ms,
            )


# ── Kernel call + result extraction (defensive across wolframclient versions) ─


def _kernel_evaluate_wrap(session: Any, wrapped_expr: str) -> Any:
    """Run ``evaluate_wrap`` on a local session, falling back to ``evaluate``.

    ``WolframLanguageSession.evaluate_wrap`` returns a result object exposing
    ``.result`` + ``.messages``. Older/edge builds may only expose ``evaluate``;
    we degrade gracefully so a bare value still round-trips.
    """
    from wolframclient.language import wlexpr  # type: ignore[import-not-found]

    expr = wlexpr(wrapped_expr)
    evaluate_wrap = getattr(session, "evaluate_wrap", None)
    if callable(evaluate_wrap):
        return evaluate_wrap(expr)
    return session.evaluate(expr)


def _extract_messages(result: Any) -> tuple[tuple[str, str], ...]:
    raw = getattr(result, "messages", None)
    if not raw:
        return ()
    out: list[tuple[str, str]] = []
    for m in raw:
        if isinstance(m, (tuple, list)) and len(m) >= 2:
            out.append((str(m[0]), str(m[1])))
        else:
            out.append(("Message", str(m)))
    return tuple(out)


def _extract_value_and_form(result: Any) -> tuple[Any, str | None]:
    """Pull ``value`` and ``form`` out of the wrapped Association result."""
    payload = getattr(result, "result", result)
    value: Any = payload
    wl_output: str | None = None
    if isinstance(payload, dict):
        # wolframclient deserializes the association keys to strings.
        value = payload.get("value", payload.get("'value'", payload))
        form = payload.get("form", payload.get("'form'"))
        if form is not None:
            wl_output = str(form)
    return value, wl_output
