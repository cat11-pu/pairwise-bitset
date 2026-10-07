"""Fixed width bit sets: block storage, set algebra, scans and sparse blocks.

A bit set is a declared length in bits plus the blocks of bytes that hold it.
Bit ``i`` lives in block ``i // 8``, at the low end of that byte: the least
significant bit of a block is the lowest index the block holds.  Bits at or
above the declared length are padding, they are never members and they stay
clear, so two sets of the same length can be compared block by block and a
complement can never reach past the declared length.

Sets of the same length combine with union, intersection and difference, each
returning a fresh set and leaving both operands alone.  A set can also be
written in a sparse form that keeps only the runs of blocks that hold bits,
which is what a mostly empty posting list wants.

Only the standard library is used, every result is deterministic, and nothing
here reads the clock, the disk or the network.
"""

#: Bits per block.
BLOCK = 8


class BitSetError(ValueError):
    """Raised when a bit set cannot carry out the requested operation."""


def _check_size(size):
    """Return size as a positive int."""
    if isinstance(size, bool) or not isinstance(size, int):
        raise TypeError("size must be an int")
    if size <= 0:
        raise BitSetError("size must be positive")
    return size


def _mask(width):
    """The low width bits of one block set, width between 0 and 8."""
    return (1 << width) - 1


def _popcount(value):
    """How many bits one block holds."""
    return bin(value & 0xFF).count("1")


def _block_of(index):
    """The block that holds a bit index."""
    return index // BLOCK


def _bit_of(index):
    """Where a bit index sits inside its block."""
    return index % BLOCK


class BitSet:
    """A set of indices from 0 up to a declared length, held in blocks.

    The length is fixed at construction.  Index 0 is the least significant bit
    of block 0, and any index at or above the length is out of range.
    """

    def __init__(self, size):
        self.size = _check_size(size)
        self._blocks = bytearray(self.nbytes())

    def nbytes(self):
        """How many blocks back the set."""
        return (self.size + BLOCK - 1) // BLOCK

    def blocks(self):
        """The backing blocks, lowest index first."""
        return tuple(self._blocks)

    def tail(self):
        """How many bits the last block holds, from 1 to 8."""
        used = self.size % BLOCK
        return used if used else BLOCK

    def _mask_tail(self):
        """Drop every bit at or above the declared length."""
        self._blocks[-1] &= _mask(self.tail())

    def _check_index(self, index):
        """Return index when it names a bit of this set."""
        if isinstance(index, bool) or not isinstance(index, int):
            raise TypeError("index must be an int")
        if index < 0 or index >= self.size:
            raise BitSetError("%r is outside a set of %d bits" % (index, self.size))
        return index

    def add(self, index):
        """Put index into the set."""
        index = self._check_index(index)
        self._blocks[_block_of(index)] |= 1 << _bit_of(index)

    def discard(self, index):
        """Take index out of the set."""
        index = self._check_index(index)
        self._blocks[_block_of(index)] &= 0xFF ^ (1 << _bit_of(index))

    def flip(self, index):
        """Turn index on when it was off, and off when it was on."""
        index = self._check_index(index)
        self._blocks[_block_of(index)] ^= 1 << _bit_of(index)

    def contains(self, index):
        """Whether index is a member."""
        index = self._check_index(index)
        return (self._blocks[_block_of(index)] >> _bit_of(index)) & 1 == 1

    def count(self):
        """How many members the set holds."""
        return sum(_popcount(value) for value in self._blocks)

    def is_empty(self):
        """Whether the set holds nothing."""
        return self.count() == 0

    def __iter__(self):
        """The members in ascending order."""
        for block_index, value in enumerate(self._blocks):
            while value:
                lowest = value & -value
                yield block_index * BLOCK + lowest.bit_length() - 1
                value ^= lowest

    def members(self):
        """The members as a tuple, in ascending order."""
        return tuple(self)

    def copy(self):
        """A set of the same length and members."""
        clone = BitSet(self.size)
        clone._blocks[:] = self._blocks
        return clone

    def _same_shape(self, other):
        """Return other when it is a set of the same length."""
        if not isinstance(other, BitSet):
            raise TypeError("a BitSet is required")
        if other.size != self.size:
            raise BitSetError("sizes differ: %d and %d" % (self.size, other.size))
        return other

    def union(self, other):
        """A new set holding every member of either side.

        The result is a fresh set and both sides keep their own members.
        """
        other = self._same_shape(other)
        out = BitSet(self.size)
        out._blocks[:] = self._blocks
        for block_index in range(out.nbytes()):
            out._blocks[block_index] |= other._blocks[block_index]
        return out

    def intersection(self, other):
        """A new set holding the members both sides have."""
        other = self._same_shape(other)
        out = self.copy()
        for block_index in range(out.nbytes()):
            out._blocks[block_index] &= other._blocks[block_index]
        return out

    def difference(self, other):
        """A new set holding the members of the left side the right side lacks."""
        other = self._same_shape(other)
        out = BitSet(self.size)
        for block_index in range(out.nbytes()):
            out._blocks[block_index] = (
                self._blocks[block_index] & (0xFF ^ other._blocks[block_index])
            )
        return out

    def is_subset(self, other):
        """Whether every member of this set is a member of other."""
        other = self._same_shape(other)
        return all(
            self._blocks[block_index] | other._blocks[block_index]
            == other._blocks[block_index]
            for block_index in range(self.nbytes())
        )

    def is_disjoint(self, other):
        """Whether the two sides share no member."""
        return self.intersection(other).is_empty()

    def equals(self, other):
        """Whether both sides have the same length and the same members."""
        other = self._same_shape(other)
        return self.blocks() == other.blocks()

    def complement(self):
        """A new set of the same length with every bit inside it flipped.

        Only the bits below the declared length belong to the set; the padding
        of the last block is not a member and stays clear.
        """
        out = BitSet(self.size)
        for block_index in range(out.nbytes()):
            out._blocks[block_index] = 0xFF ^ self._blocks[block_index]
        out._mask_tail()
        return out


def busy_blocks(bitset):
    """The block indices that hold at least one member."""
    return tuple(
        block_index
        for block_index, value in enumerate(bitset.blocks())
        if value
    )


def compress(bitset):
    """The sparse form of a set: one entry per run of blocks that hold bits.

    Each entry pairs the block index the run starts at with the bytes of the
    run itself, so a mostly empty set costs one entry per busy region instead
    of a block per block.
    """
    blocks = bitset.blocks()
    runs = []
    index = 0
    while index < len(blocks):
        if blocks[index] == 0:
            index += 1
            continue
        start = index
        while index < len(blocks) and blocks[index] != 0:
            index += 1
        runs.append((start, bytes(blocks[start:index])))
    return tuple(runs)


def decompress(runs, size):
    """Rebuild the set a sparse form describes."""
    bitset = BitSet(size)
    for start, payload in runs:
        if start < 0 or start + len(payload) > bitset.nbytes():
            raise BitSetError("the run at block %r does not fit" % (start,))
        for offset in range(len(payload)):
            bitset._blocks[start + offset] = payload[offset]
    bitset._mask_tail()
    return bitset
