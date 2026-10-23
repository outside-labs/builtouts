"""Bounded offline jobs; real I/O functions should set their own timeouts."""

from builtouts.concurrent import thread_iter, thread_map, thread_outcomes

assert thread_map(len, ['one', 'four'], max_workers=2, max_pending=2) == [3, 4]
with thread_iter(str.upper, ['one', 'two', 'three'], max_workers=2,
                 max_pending=2, ordered=False) as results:
    assert sorted(results) == ['ONE', 'THREE', 'TWO']
with thread_iter(lambda value: value * 2, range(100), max_workers=2,
                 max_pending=4) as results:
    assert next(results) == 0
    # Exiting early cancels queued work and joins running calls.
observed = []
with thread_outcomes(int, ['1', 'invalid', '3'], on_result=observed.append) as results:
    outcomes = list(results)
assert [row.index for row in outcomes] == [0, 1, 2]
assert [row.ok for row in outcomes] == [True, False, True]
assert outcomes[0].result() == 1
assert len(observed) == 3
print('Bounded thread jobs passed')
