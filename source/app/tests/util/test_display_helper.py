# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import string

from instance_scheduler.util.display_helper import set_str

characters = string.ascii_lowercase
names = [c * 3 for c in characters]


def test_set_str() -> None:
    sep_item = ","
    sep_range = "-"
    # single item
    assert set_str({0}, names) == names[0]
    # two items
    assert set_str({0, 3}, names) == names[0] + sep_item + names[3]
    # range
    assert set_str({0, 1, 2, 3, 4}, names) == names[0] + sep_range + names[4]
    # range and item
    assert (
        set_str({0, 1, 2, 4}, names)
        == names[0] + sep_range + names[2] + sep_item + names[4]
    )
    # two ranges
    assert (
        set_str({0, 1, 3, 4}, names)
        == names[0] + sep_range + names[1] + sep_item + names[3] + sep_range + names[4]
    )
