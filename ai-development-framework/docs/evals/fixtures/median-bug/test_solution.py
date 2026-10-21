# Objective gate for the median-bug case. stdlib unittest — no new dependency.
# unittest.TestCase runs under both `python3 -m unittest` and pytest unchanged.
import unittest

from solution import median


class MedianTest(unittest.TestCase):
    def test_odd_unsorted(self):  # catches a forgot-to-sort bug
        self.assertEqual(median([3, 1, 2]), 2)

    def test_even_mean_of_middle(self):
        self.assertEqual(median([1, 2, 3, 4]), 2.5)

    def test_single(self):
        self.assertEqual(median([5]), 5)


if __name__ == "__main__":
    unittest.main()
