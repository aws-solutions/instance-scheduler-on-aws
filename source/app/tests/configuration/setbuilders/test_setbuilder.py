# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import string
from collections.abc import Sequence
from typing import Optional

from pytest import raises

from instance_scheduler.configuration.setbuilders.setbuilder import SetBuilder

characters = string.ascii_lowercase
names = [c * 3 for c in characters]
names_cased = [n.capitalize() for n in names]
all_items = set([i for i in range(0, len(names))])


def test_name() -> None:
    # names 1 char
    for i, name in enumerate(names):
        assert SetBuilder(names=names).build(name) == {i}
    # names 1 char with offset
    for i, name in enumerate(names):
        assert SetBuilder(names=names, offset=1).build(name) == {i + 1}

    # names 1 char ignore case
    for i, name in enumerate(names):
        assert SetBuilder(names=names, ignorecase=True).build(name.upper()) == {i}

    # names 3
    for i, name in enumerate(names_cased):
        assert SetBuilder(names=names_cased).build(name) == {i}

    # names 3, ignore case
    for i, name in enumerate(names):
        assert SetBuilder(names=names_cased, ignorecase=True).build(name) == {i}

    # names 3, 1 significant character
    for i, name in enumerate(names):
        assert SetBuilder(names=names_cased, significant_name_characters=1).build(
            name.upper()
        ) == {i}

    # names 3, 1 significant character, ignore case
    for i, name in enumerate(names):
        assert SetBuilder(names=names_cased, significant_name_characters=3).build(
            name + name
        ) == {i}

    # all items passed in as list of strings
    assert SetBuilder(names=names).build(names) == all_items


def test_value() -> None:
    # all by value
    for value in range(0, len(names)):
        assert SetBuilder(names=names).build(str(value)) == {value}

    # all by value with offset
    for value in range(1, len(names) + 1):
        assert SetBuilder(names=names, offset=1).build(str(value)) == {value}


def test_min_max() -> None:
    # builder initialized by min and max values
    for i in range(0, 5):
        assert SetBuilder(min_value=0, max_value=4).build(str(i)) == {i}


def test_wildcards() -> None:
    # all items using standard and custom wildcard
    assert SetBuilder(names).build("*") == all_items
    assert SetBuilder(names).build("?") == all_items
    assert SetBuilder(names, all_items_wildcards="!").build("!") == all_items

    # first item using standard and custom wildcard
    assert SetBuilder(names).build("^") == {0}
    assert SetBuilder(names, first_item_wildcard="!").build("!") == {0}
    assert SetBuilder(names, offset=1).build("^") == {1}

    # last item using standard and custom wildcard
    assert SetBuilder(names).build("$") == {len(names) - 1}
    assert SetBuilder(names, last_item_wildcard="!").build("!") == {len(names) - 1}
    assert SetBuilder(names, offset=1).build("$") == {len(names)}

    # combined first and last wildcard
    assert SetBuilder(names).build("^,$") == {0, len(names) - 1}
    assert SetBuilder(names).build("^-$") == all_items


def test_multiple() -> None:
    # comma separated list of names
    assert SetBuilder(names).build(",".join(names)) == all_items
    # comma separated list of values
    assert (
        SetBuilder(names).build(",".join([str(i) for i in range(0, len(names))]))
        == all_items
    )


def test_ranges() -> None:
    # name range
    assert SetBuilder(names).build(names[0] + "-" + names[2]) == {0, 1, 2}
    # name ranges no overlap
    assert SetBuilder(names).build(
        names[0] + "-" + names[2] + "," + names[4] + "-" + names[6]
    ) == {0, 1, 2, 4, 5, 6}
    # name ranges with overlap
    assert SetBuilder(names).build(
        names[2] + "-" + names[6] + "," + names[4] + "-" + names[8]
    ) == {2, 3, 4, 5, 6, 7, 8}
    # name range with wrap
    assert SetBuilder(names, wrap=True).build(names[-2] + "-" + names[2]) == {
        0,
        1,
        2,
        len(names) - 2,
        len(names) - 1,
    }

    # value range
    assert SetBuilder(names).build("0-2") == {0, 1, 2}
    # value ranges
    assert SetBuilder(names).build("0-3, 9-12") == {0, 1, 2, 3, 9, 10, 11, 12}
    # value ranges with overlap
    assert SetBuilder(names).build("0-8, 6-12") == {
        0,
        1,
        2,
        3,
        4,
        5,
        6,
        7,
        8,
        9,
        10,
        11,
        12,
    }
    # value range with wrap
    assert SetBuilder(names, wrap=True).build(str(len(names) - 2) + "-2") == {
        0,
        1,
        2,
        len(names) - 2,
        len(names) - 1,
    }

    with raises(ValueError):
        SetBuilder(names, wrap=False).build(names[1] + "-" + names[0])

    with raises(ValueError):
        SetBuilder(names, wrap=False).build("2-1")


def test_increments() -> None:
    # increments on start name and value
    assert SetBuilder(names).build(names[0] + "/5") == {
        i for i in range(0, len(names), 5)
    }
    assert SetBuilder(names).build("0/3") == {i for i in range(0, len(names), 3)}

    # increment on ranges
    assert SetBuilder(names).build(names[0] + "-" + names[10] + "/2") == {
        0,
        2,
        4,
        6,
        8,
        10,
    }
    assert SetBuilder(names).build("0-10/3") == {0, 3, 6, 9}
    assert SetBuilder(names, wrap=True).build("10-5/5") == {10, 15, 20, 25, 4}

    # invalid increment numbers
    with raises(ValueError):
        SetBuilder(names).build("0/0")

    with raises(ValueError):
        SetBuilder(names).build("0/!")


def test_unknown_values() -> None:
    # unknown name raises error
    with raises(ValueError):
        SetBuilder(names).build("##")

    # unknown value raises error
    with raises(ValueError):
        SetBuilder(min_value=0, max_value=1).build("-1")

    # this class has a handler for handling unknow items
    class SetBuilderWithHandler(SetBuilder):
        def _parse_unknown(self, s: str) -> Optional[list[int]]:
            return [] if s == "" else None

    assert SetBuilderWithHandler(names).build("") == set()

    with raises(ValueError):
        SetBuilderWithHandler(names).build("unknown")


def test_custom_parsers() -> None:
    class SetBuilderWithCustomPreParser(SetBuilder):
        def __init__(self, names: Sequence[str]):
            SetBuilder.__init__(self, names=names)
            self._pre_custom_parsers = [self._pre_parser]

        def _pre_parser(self, s: str) -> Optional[list[int]]:
            if s == "###":
                return [0]
            return None

    assert SetBuilderWithCustomPreParser("").build("###") == {0}

    class SetBuilderWithCustomPostParser(SetBuilder):
        def __init__(self, names: Sequence[str]):
            SetBuilder.__init__(self, names=names)
            self._post_custom_parsers = [self._post_parser]

        def _post_parser(self, s: str) -> Optional[list[int]]:
            if s == "!!!":
                return [1]
            return None

    assert SetBuilderWithCustomPostParser("").build("!!!") == {1}

    class SetBuilderWithCustomParsers(SetBuilder):
        def __init__(self, names: Sequence[str]):
            SetBuilder.__init__(self, names=names)
            self._post_custom_parsers = [self._pre_parser, self._post_parser]

        def _pre_parser(self, s: str) -> Optional[list[int]]:
            if s == "###":
                return [99]
            return None

        def _post_parser(self, s: str) -> Optional[list[int]]:
            if s == "!!!":
                return [100]
            return None

    assert SetBuilderWithCustomParsers(names).build("###,!!!," + names[0]) == {
        0,
        99,
        100,
    }


def test_exceptions() -> None:
    # names and max_value combination not allowed
    with raises(ValueError):
        SetBuilder(names=names, max_value=1)

    # names and min_value combination not allowed
    with raises(ValueError):
        SetBuilder(names=names, min_value=0)

    # both min_value and max_value must be used
    with raises(ValueError):
        SetBuilder(min_value=0)

    # both min_value and max_value must be used
    with raises(ValueError):
        SetBuilder(max_value=1)

    # max_value must be equal or greater than min_value
    with raises(ValueError):
        SetBuilder(min_value=99, max_value=1)

    # offset must be the same if specified with min_value
    with raises(ValueError):
        SetBuilder(min_value=0, max_value=1, offset=1)
