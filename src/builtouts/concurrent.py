"""Bounded synchronous thread concurrency for independent I/O operations."""

from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from contextlib import contextmanager
from dataclasses import dataclass, field
import os
from typing import cast

__all__ = ['Outcome', 'thread_iter', 'thread_map', 'thread_outcomes']


@dataclass(frozen=True, slots=True)
class Outcome[R]:
    """An indexed result without a separate reference to the input item.

    Returned values and original exceptions may themselves retain input data.
    Exception tracebacks are preserved; they are not a memory isolation boundary.
    """

    index: int
    value: R | None = None
    error: Exception | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if isinstance(self.index, bool) or not isinstance(self.index, int):
            raise TypeError('index must be a nonnegative integer')
        if self.index < 0:
            raise ValueError('index must be nonnegative')
        if self.error is not None and not isinstance(self.error, Exception):
            raise TypeError('error must be an Exception or None')
        if self.error is not None and self.value is not None:
            raise ValueError('an outcome cannot contain both a value and an error')

    @property
    def ok(self) -> bool:
        return self.error is None

    def result(self) -> R:
        """Return the value (including None), or raise the original exception."""
        if self.error is not None:
            raise self.error
        return cast(R, self.value)


def _positive(name: str, value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f'{name} must be a positive integer')
    if value <= 0:
        raise ValueError(f'{name} must be a positive integer')
    return value


def _results[T, R](
    pool: ThreadPoolExecutor, function: Callable[[T], R], iterable: Iterable[T],
    max_pending: int, ordered: bool, on_result: Callable[[Outcome[R]], None] | None,
) -> Iterator[Outcome[R]]:
    source = iter(iterable)
    pending: dict[Future[R], int] = {}
    exhausted = False
    index = 0

    def fill() -> None:
        nonlocal exhausted, index
        while not exhausted and len(pending) < max_pending:
            try:
                item = next(source)
            except StopIteration:
                exhausted = True
                break
            pending[pool.submit(function, item)] = index
            index += 1

    try:
        fill()
        while pending:
            if ordered:
                future = next(iter(pending))
            else:
                done, _ = wait(pending, return_when=FIRST_COMPLETED)
                future = min(done, key=pending.__getitem__)
            result_index = pending.pop(future)
            try:
                outcome = Outcome(result_index, value=future.result())
            except Exception as error:
                outcome = Outcome(result_index, error=error)
            if on_result is not None:
                on_result(outcome)
            yield outcome
            fill()
    finally:
        for future in pending:
            future.cancel()


@contextmanager
def _thread_records[T, R](
    function: Callable[[T], R], iterable: Iterable[T], *, max_workers: int | None = None,
    max_pending: int | None = None, ordered: bool = True,
    on_result: Callable[[Outcome[R]], None] | None = None,
) -> Iterator[Iterator[Outcome[R]]]:
    if not callable(function):
        raise TypeError('function must be callable')
    if not isinstance(ordered, bool):
        raise TypeError('ordered must be a bool')
    if on_result is not None and not callable(on_result):
        raise TypeError('on_result must be callable or None')
    workers = (min(32, (os.process_cpu_count() or 1) + 4) if max_workers is None
               else _positive('max_workers', max_workers))
    capacity = workers * 2 if max_pending is None else _positive('max_pending', max_pending)
    pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix='builtouts')
    results = _results(pool, function, iterable, capacity, ordered, on_result)
    try:
        yield results
    finally:
        results.close()
        pool.shutdown(wait=True, cancel_futures=True)


@contextmanager
def thread_iter[T, R](
    function: Callable[[T], R], iterable: Iterable[T], *, max_workers: int | None = None,
    max_pending: int | None = None, ordered: bool = True,
    on_result: Callable[[Outcome[R]], None] | None = None,
) -> Iterator[Iterator[R]]:
    """Yield bounded values; always use as a context manager.

    ordered=True preserves input order; false returns ready results first.
    Worker and input exceptions propagate unchanged. on_result runs on the
    consuming thread before yielding a value or raising its worker exception.
    Exit cancels queued calls and joins running calls; I/O needs its own timeout.
    The caller owns input resources. No input is consumed before iteration.
    """
    with _thread_records(function, iterable, max_workers=max_workers,
                         max_pending=max_pending, ordered=ordered, on_result=on_result) as records:
        values = (record.result() for record in records)
        try:
            yield values
        finally:
            values.close()


@contextmanager
def thread_outcomes[T, R](
    function: Callable[[T], R], iterable: Iterable[T], *, max_workers: int | None = None,
    max_pending: int | None = None, ordered: bool = True,
    on_result: Callable[[Outcome[R]], None] | None = None,
) -> Iterator[Iterator[Outcome[R]]]:
    """Yield indexed successes/failures with the same bounds and cleanup.

    Worker Exception instances become outcomes. BaseException, producer failures
    and callback failures propagate. Only consumed results invoke on_result;
    unconsumed or cancelled work emits no outcome/callback during context exit.
    """
    with _thread_records(function, iterable, max_workers=max_workers,
                         max_pending=max_pending, ordered=ordered, on_result=on_result) as records:
        yield records


def thread_map[T, R](
    function: Callable[[T], R], iterable: Iterable[T], *, max_workers: int | None = None,
    max_pending: int | None = None, ordered: bool = True,
    on_result: Callable[[Outcome[R]], None] | None = None,
) -> list[R]:
    """Collect thread_iter results into a list; input must terminate.

    Outstanding work is bounded, but the returned list grows with all results.
    Use thread_iter to process large or infinite inputs incrementally.
    """
    with thread_iter(function, iterable, max_workers=max_workers,
                     max_pending=max_pending, ordered=ordered, on_result=on_result) as results:
        return list(results)
