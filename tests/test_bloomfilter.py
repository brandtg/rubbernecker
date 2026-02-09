# SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0

import pytest
from rubbernecker.crawl.bloomfilter import BloomFilter


class TestBloomFilter:
    def test_default_initialization(self):
        bf = BloomFilter()
        assert bf.size == 15_000_000
        assert bf.hash_count == 9
        assert len(bf.bit_array) == 15_000_000

    def test_custom_initialization(self):
        bf = BloomFilter(size=1000, hash_count=5)
        assert bf.size == 1000
        assert bf.hash_count == 5
        assert len(bf.bit_array) == 1000

    def test_str_representation(self):
        bf = BloomFilter(size=100, hash_count=3)
        assert str(bf) == "BloomFilter(size=100, hash_count=3)"

    def test_add_and_check_positive(self):
        bf = BloomFilter(size=1000, hash_count=3)
        bf.add("test_item")
        assert bf.check("test_item") is True

    def test_check_nonexistent_item(self):
        bf = BloomFilter(size=1000, hash_count=3)
        bf.add("test_item")
        assert bf.check("nonexistent") is False

    def test_duplicate_add(self):
        bf = BloomFilter(size=1000, hash_count=3)
        bf.add("test_item")
        bf.add("test_item")
        assert bf.check("test_item") is True

    def test_optimal_parameters_1_percent(self):
        size, hash_count = BloomFilter.optimal_parameters(n=1000, p=0.01)
        assert size > 0
        assert hash_count > 0

    def test_optimal_parameters_1e6_elements(self):
        size, hash_count = BloomFilter.optimal_parameters(n=1_000_000, p=0.001)
        assert size > 0
        assert hash_count > 0

    def test_optimal_parameters_very_low_false_positive_rate(self):
        size, hash_count = BloomFilter.optimal_parameters(n=100, p=0.0001)
        assert size > 100
        assert hash_count >= 1

    def test_multiple_items(self):
        bf = BloomFilter(size=10000, hash_count=5)
        items = ["apple", "banana", "cherry", "date", "elderberry"]
        for item in items:
            bf.add(item)
        for item in items:
            assert bf.check(item) is True

    def test_hashes_generation(self):
        bf = BloomFilter(size=1000, hash_count=3)
        hashes = list(bf._hashes("test"))
        assert len(hashes) == 3
        for h in hashes:
            assert 0 <= h < 1000
