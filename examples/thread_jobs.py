"""Bounded offline jobs; real I/O functions should set their own timeouts."""

from builtouts.concurrent import thread_iter, thread_map

assert thread_map(len, ['one', 'four'], max_workers=2, max_pending=2) == [3, 4]
with thread_iter(str.upper, ['one', 'two', 'three'], max_workers=2,
                 max_pending=2, ordered=False) as results:
    assert sorted(results) == ['ONE', 'THREE', 'TWO']
with thread_iter(lambda value: value * 2, range(100), max_workers=2,
                 max_pending=4) as results:
    assert next(results) == 0
    # Exiting early cancels queued work and joins running calls.
print('Bounded thread jobs passed')
