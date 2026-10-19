"""Bounded synchronous thread concurrency for independent I/O operations."""

from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from contextlib import contextmanager
import os

__all__ = ['thread_iter', 'thread_map']


def _positive(name: str, value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f'{name} must be a positive integer')
    if value <= 0:
        raise ValueError(f'{name} must be a positive integer')
    return value


def _results[T, R](
    pool: ThreadPoolExecutor, function: Callable[[T], R], iterable: Iterable[T],
    max_pending: int, ordered: bool,
) -> Iterator[R]:
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
            del pending[future]
            yield future.result()
            fill()
    finally:
        for future in pending:
            future.cancel()


@contextmanager
def thread_iter[T, R](
    function: Callable[[T], R], iterable: Iterable[T], *, max_workers: int | None = None,
    max_pending: int | None = None, ordered: bool = True,
) -> Iterator[Iterator[R]]:
    """Yield a bounded result iterator; always use as a context manager.

    ordered=True preserves input order; false returns ready results first.
    Input is pulled only as submitted-but-unconsumed result capacity permits.
    No input is consumed until iteration begins. Worker and input exceptions
    propagate unchanged. Exiting cancels queued calls and joins running calls;
    it cannot interrupt a running function. Give I/O operations their own timeout.
    The caller retains ownership of the input iterable and its resources.
    """
    if not callable(function):
        raise TypeError('function must be callable')
    if not isinstance(ordered, bool):
        raise TypeError('ordered must be a bool')
    workers = (min(32, (os.process_cpu_count() or 1) + 4) if max_workers is None
               else _positive('max_workers', max_workers))
    capacity = workers * 2 if max_pending is None else _positive('max_pending', max_pending)
    pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix='builtouts')
    results = _results(pool, function, iterable, capacity, ordered)
    try:
        yield results
    finally:
        results.close()
        pool.shutdown(wait=True, cancel_futures=True)


def thread_map[T, R](
    function: Callable[[T], R], iterable: Iterable[T], *, max_workers: int | None = None,
    max_pending: int | None = None, ordered: bool = True,
) -> list[R]:
    """Collect thread_iter results into a list; input must terminate.

    Outstanding work is bounded, but the returned list grows with all results.
    Use thread_iter to process large or infinite inputs incrementally.
    """
    with thread_iter(function, iterable, max_workers=max_workers,
                     max_pending=max_pending, ordered=ordered) as results:
        return list(results)
