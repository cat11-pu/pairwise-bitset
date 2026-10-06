"""Behaviour tests for the bit set kernel."""

import unittest

from bitset.core import BitSet
from bitset.core import BitSetError
from bitset.core import busy_blocks
from bitset.core import compress
from bitset.core import decompress


class TestSingleBits(unittest.TestCase):
    def test_members_are_recorded_read_and_dropped(self):
        bits = BitSet(20)
        self.assertTrue(bits.is_empty())
        self.assertEqual(bits.blocks(), (0, 0, 0))
        bits.add(2)
        bits.add(10)
        bits.add(18)
        self.assertEqual(bits.blocks(), (0x04, 0x04, 0x04))
        self.assertEqual(
            [bits.contains(index) for index in (2, 10, 18, 0, 9, 19)],
            [True, True, True, False, False, False],
        )
        bits.discard(10)
        self.assertEqual(bits.blocks(), (0x04, 0x00, 0x04))
        self.assertEqual(bits.count(), 2)
        self.assertEqual(bits.members(), (2, 18))
        self.assertFalse(bits.is_empty())

        toggle = BitSet(20)
        toggle.flip(5)
        self.assertTrue(toggle.contains(5))
        toggle.flip(5)
        self.assertFalse(toggle.contains(5))
        self.assertTrue(toggle.is_empty())


class TestBounds(unittest.TestCase):
    def test_indices_outside_the_declared_length_are_rejected(self):
        bits = BitSet(20)
        for bad in (20, 21, 200):
            with self.assertRaises(BitSetError):
                bits.add(bad)
            with self.assertRaises(BitSetError):
                bits.contains(bad)
            with self.assertRaises(BitSetError):
                bits.discard(bad)
            with self.assertRaises(BitSetError):
                bits.flip(bad)
        narrow = BitSet(13)
        with self.assertRaises(BitSetError):
            narrow.add(13)
        with self.assertRaises(BitSetError):
            narrow.contains(13)
        with self.assertRaises(BitSetError):
            bits.add(-1)
        with self.assertRaises(BitSetError):
            bits.contains(-1)
        with self.assertRaises(TypeError):
            bits.add("3")
        with self.assertRaises(TypeError):
            BitSet("20")
        with self.assertRaises(BitSetError):
            BitSet(0)
        self.assertEqual(bits.blocks(), (0, 0, 0))


class TestCardinality(unittest.TestCase):
    def test_the_top_bit_of_each_block_is_counted(self):
        bits = BitSet(16)
        bits.add(7)
        bits.add(15)
        self.assertTrue(bits.contains(7))
        self.assertTrue(bits.contains(15))
        self.assertFalse(bits.is_empty())
        self.assertEqual(bits.count(), 2)
        self.assertEqual(bits.members(), (7, 15))


class TestUnion(unittest.TestCase):
    def test_union_holds_both_sides_and_keeps_the_operands(self):
        left = BitSet(24)
        for index in (2, 10, 18):
            left.add(index)
        right = BitSet(24)
        for index in (2, 11, 19):
            right.add(index)

        both = left.union(right)
        for index in (2, 10, 11, 18, 19):
            self.assertTrue(both.contains(index), index)
        for index in (0, 3, 9, 12, 17, 20, 23):
            self.assertFalse(both.contains(index), index)
        self.assertEqual(both.count(), 5)

        self.assertEqual(left.blocks(), (0x04, 0x04, 0x04))
        self.assertEqual(left.count(), 3)
        self.assertEqual(right.blocks(), (0x04, 0x08, 0x08))
        self.assertEqual(right.count(), 3)


class TestIntersection(unittest.TestCase):
    def test_intersection_holds_only_the_members_both_sides_have(self):
        left = BitSet(20)
        for index in (1, 9, 16, 18):
            left.add(index)
        right = BitSet(20)
        for index in (1, 10, 17):
            right.add(index)

        shared = left.intersection(right)
        self.assertTrue(shared.contains(1))
        for index in (9, 10, 16, 17, 18):
            self.assertFalse(shared.contains(index), index)
        self.assertEqual(shared.count(), 1)
        self.assertEqual(shared.members(), (1,))
        self.assertTrue(shared.is_subset(left))
        self.assertTrue(shared.is_subset(right))
        self.assertEqual(left.count(), 4)
        self.assertEqual(right.count(), 3)


class TestDifference(unittest.TestCase):
    def test_difference_keeps_what_the_right_side_lacks(self):
        left = BitSet(20)
        for index in (0, 8, 16):
            left.add(index)
        right = BitSet(20)
        for index in (0, 9, 17):
            right.add(index)

        only = left.difference(right)
        self.assertTrue(only.contains(8))
        self.assertTrue(only.contains(16))
        for index in (0, 9, 17, 1):
            self.assertFalse(only.contains(index), index)
        self.assertEqual(only.count(), 2)
        self.assertEqual(only.members(), (8, 16))
        self.assertTrue(only.is_subset(left))
        self.assertTrue(only.is_disjoint(right))
        self.assertTrue(left.difference(left).is_empty())
        self.assertEqual(left.count(), 3)
        self.assertEqual(right.count(), 3)


class TestComplement(unittest.TestCase):
    def test_complement_flips_only_the_bits_inside_the_length(self):
        bits = BitSet(13)
        for index in (0, 8, 12):
            bits.add(index)

        other = bits.complement()
        for index in range(13):
            self.assertEqual(other.contains(index), not bits.contains(index), index)
        self.assertEqual(other.count(), 10)
        self.assertEqual(other.members(), (1, 2, 3, 4, 5, 6, 7, 9, 10, 11))
        self.assertEqual(sum(1 for index in other if index >= 13), 0)
        self.assertEqual(bits.count(), 3)
        self.assertEqual((bits.complement()).complement().blocks(), bits.blocks())


class TestSparseBlocks(unittest.TestCase):
    def test_the_sparse_form_keeps_every_block_of_the_set(self):
        bits = BitSet(40)
        for index in (1, 9, 10, 24, 34):
            bits.add(index)

        runs = compress(bits)
        self.assertEqual(len(runs), 2)
        covered = tuple(
            block
            for start, payload in runs
            for block in range(start, start + len(payload))
        )
        self.assertEqual(covered, busy_blocks(bits))
        self.assertEqual(
            sum(len(payload) for _, payload in runs), len(busy_blocks(bits))
        )

        restored = decompress(runs, 40)
        self.assertEqual(restored.blocks(), bits.blocks())
        self.assertEqual(restored.count(), 5)
        self.assertEqual(restored.members(), (1, 9, 10, 24, 34))
        self.assertEqual(decompress((), 40).members(), ())
        self.assertEqual(compress(BitSet(40)), ())


class TestSetLaws(unittest.TestCase):
    def test_union_intersection_and_difference_split_the_members(self):
        left = BitSet(20)
        for index in (2, 9, 16, 18):
            left.add(index)
        right = BitSet(20)
        for index in (2, 10, 17, 18):
            right.add(index)

        both = left.union(right)
        shared = left.intersection(right)
        only_left = left.difference(right)
        only_right = right.difference(left)

        self.assertTrue(shared.is_subset(both))
        self.assertTrue(only_left.is_subset(left))
        self.assertTrue(only_right.is_subset(right))
        self.assertTrue(shared.is_disjoint(only_left))
        self.assertEqual(both.count(), 6)
        self.assertEqual(shared.count(), 2)
        self.assertEqual(only_left.count(), 2)
        self.assertEqual(only_right.count(), 2)
        self.assertEqual(
            both.count(), shared.count() + only_left.count() + only_right.count()
        )


class TestScan(unittest.TestCase):
    def test_the_scan_walks_every_member_in_order(self):
        bits = BitSet(20)
        for index in (0, 1, 3, 8, 9, 16, 17):
            bits.add(index)

        self.assertEqual(tuple(bits), (0, 1, 3, 8, 9, 16, 17))
        self.assertEqual(bits.members(), (0, 1, 3, 8, 9, 16, 17))
        self.assertEqual(
            [index for index in range(20) if bits.contains(index)], list(bits)
        )
        self.assertEqual(bits.count(), 7)
        self.assertEqual(list(BitSet(20)), [])

        empty = BitSet(20)
        empty.add(0)
        empty.discard(0)
        self.assertEqual(list(empty), [])


if __name__ == "__main__":
    unittest.main()
