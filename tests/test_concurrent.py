from concurrent.futures import ThreadPoolExecutor
import itertools
import threading
import unittest
from unittest.mock import patch

from builtouts.concurrent import thread_iter, thread_map


class ThreadTests(unittest.TestCase):
    def test_empty_values_and_default_workers(self):
        self.assertEqual(thread_map(len, []), [])
        self.assertEqual(thread_map(len, ['a', 'abc', 'xy']), [1, 3, 2])
        self.assertEqual(thread_map(lambda x: x, [None, False, 0]), [None, False, 0])
        with patch('builtouts.concurrent.os.process_cpu_count', return_value=None):
            self.assertEqual(thread_map(str, [1]), ['1'])

    def test_actual_overlap_with_a_barrier(self):
        barrier = threading.Barrier(3, timeout=5)
        def work(value):
            barrier.wait()
            return value * 2
        self.assertEqual(thread_map(work, [1, 2, 3], max_workers=3, max_pending=3), [2, 4, 6])

    def test_ready_first_unblocks_before_first_input_finishes(self):
        release = threading.Event()
        first_started = threading.Event()
        def work(value):
            if value == 0:
                first_started.set()
                if not release.wait(5):
                    raise TimeoutError('test worker safety timeout')
            else:
                if not first_started.wait(5):
                    raise TimeoutError('first worker never started')
            return value
        try:
            with thread_iter(work, [0, 1], max_workers=2, ordered=False) as results:
                self.assertEqual(next(results), 1)
                release.set()
                self.assertEqual(list(results), [0])
        finally:
            release.set()

    def test_ordered_waits_for_input_order(self):
        second_done = threading.Event()
        def work(value):
            if value == 0:
                if not second_done.wait(5):
                    raise TimeoutError('second worker never ran')
            else:
                second_done.set()
            return value
        self.assertEqual(thread_map(work, [0, 1], max_workers=2), [0, 1])

    def test_lazy_bounded_input_including_completed_unconsumed_results(self):
        seen = []
        def source():
            for value in itertools.count():
                seen.append(value)
                yield value
        with thread_iter(lambda x: x, source(), max_workers=1, max_pending=3) as results:
            self.assertEqual(seen, [])
            self.assertEqual(next(results), 0)
            self.assertEqual(seen, [0, 1, 2])
            self.assertEqual(next(results), 1)
            self.assertEqual(seen, [0, 1, 2, 3])
        self.assertEqual(seen, [0, 1, 2, 3])
        self.assertEqual(list(results), [])

    def test_worker_exception_identity_and_cleanup(self):
        error = LookupError('original')
        threads = []
        def work(value):
            threads.append(threading.current_thread())
            if value == 1:
                raise error
            return value
        with self.assertRaises(LookupError) as raised:
            thread_map(work, range(10), max_workers=1, max_pending=2)
        self.assertIs(raised.exception, error)
        self.assertTrue(all(not thread.is_alive() for thread in threads))

    def test_input_exception_identity_and_cleanup(self):
        error = OSError('input')
        threads = []
        def source():
            yield 1
            raise error
        def work(value):
            threads.append(threading.current_thread())
            return value
        with self.assertRaises(OSError) as raised:
            thread_map(work, source(), max_workers=1, max_pending=3)
        self.assertIs(raised.exception, error)
        self.assertTrue(all(not thread.is_alive() for thread in threads))

    def test_early_exit_cancels_queued_calls_and_joins_running_workers(self):
        release = threading.Event()
        started = threading.Event()
        cancelled = threading.Event()
        threads = []
        class RecordingPool(ThreadPoolExecutor):
            def submit(self, function, *args, **kwargs):
                future = super().submit(function, *args, **kwargs)
                future.add_done_callback(lambda done: cancelled.set() if done.cancelled() else None)
                return future
        def work(value):
            threads.append(threading.current_thread())
            if value == 0:
                return value
            if value > 1:
                raise AssertionError('queued call should be cancelled')
            started.set()
            if not release.wait(5):
                raise TimeoutError('test safety timeout')
            return value
        def release_after_cancellation():
            cancelled.wait(5)
            release.set()
        releaser = threading.Thread(target=release_after_cancellation)
        releaser.start()
        try:
            with patch('builtouts.concurrent.ThreadPoolExecutor', RecordingPool):
                with thread_iter(work, range(10), max_workers=1, max_pending=10) as results:
                    self.assertEqual(next(results), 0)
                    self.assertTrue(started.wait(5))
            self.assertTrue(cancelled.is_set())
            self.assertEqual(list(results), [])
            self.assertTrue(all(not thread.is_alive() for thread in threads))
        finally:
            release.set()
            releaser.join(timeout=5)

    def test_unused_context_and_caller_exception(self):
        def bad_source():
            raise AssertionError('must remain unconsumed')
            yield
        with thread_iter(str, bad_source()) as results:
            pass
        self.assertEqual(list(results), [])
        with self.assertRaisesRegex(RuntimeError, 'caller'):
            with thread_iter(str, range(100), max_pending=1) as results:
                self.assertEqual(next(results), '0')
                raise RuntimeError('caller')

    def test_validation(self):
        for keyword in ('max_workers', 'max_pending'):
            for value in (True, 1.5, '2', 0, -1):
                with self.subTest(keyword=keyword, value=value), self.assertRaises((ValueError, TypeError)):
                    thread_map(str, [], **{keyword: value})
        for kwargs in ({'ordered': 1}, {'ordered': None}):
            with self.assertRaises(TypeError):
                thread_map(str, [], **kwargs)
        with self.assertRaises(TypeError):
            thread_map(None, [])
        with self.assertRaises(TypeError):
            thread_map(str, 1)


if __name__ == '__main__':
    unittest.main()
