# SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0

import hashlib
import math
from typing import Generator

# Tuned for false positive rate of 0.1% with 1 million elements
DEFAULT_SIZE = 15_000_000  # ~1.8 MB
DEFAULT_HASH_COUNT = 9


class BloomFilter:
    def __init__(
        self, size: int = DEFAULT_SIZE, hash_count: int = DEFAULT_HASH_COUNT
    ) -> None:
        """
        Initialize a Bloom filter with a given size and number of hash functions.

        :param size: Size of the bit array.
        :param hash_count: Number of hash functions to use.
        """
        self.size: int = size
        self.hash_count: int = hash_count
        self.bit_array: list[int] = [0] * size

    def __str__(self) -> str:
        return f"BloomFilter(size={self.size}, hash_count={self.hash_count})"

    def _hashes(self, item: str) -> Generator[int, None, None]:
        """
        Generate hash values for the given item using multiple hash functions.
        """
        for i in range(self.hash_count):
            hash_result = int(hashlib.md5((item + str(i)).encode()).hexdigest(), 16)
            yield hash_result % self.size

    def add(self, item: str) -> None:
        """
        Add an item to the Bloom filter.

        :param item: The item to add.
        """
        for hash_value in self._hashes(item):
            self.bit_array[hash_value] = 1

    def check(self, item: str) -> bool:
        """
        Check if an item is in the Bloom filter.

        :param item: The item to check.
        :return: True if the item is possibly in the filter, False if it is definitely not.
        """
        return all(self.bit_array[hash_value] for hash_value in self._hashes(item))

    @staticmethod
    def optimal_parameters(n: int, p: float) -> tuple[int, int]:
        """
        Calculate optimal size and hash count for a given number of elements (n) and false positive
        probability (p).

        :param n: Number of elements expected to be added to the filter.
        :param p: Desired false positive probability.
        :return: A tuple containing the optimal size of the bit array and the number of hash functions.
        """
        m = -(n * math.log(p)) / (math.log(2) ** 2)
        k = (m / n) * math.log(2)
        return int(m), int(k)
