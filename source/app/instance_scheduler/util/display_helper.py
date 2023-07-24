# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from collections.abc import Iterator
from typing import Any


def time_str(t: Any) -> str:
    return DisplayHelper.time_as_str(t)


def set_str(the_set: Any, displaynames: Any = None, offset: int = 0) -> str:
    return DisplayHelper.set_as_str(
        the_set=the_set, display_names=displaynames, offset=offset
    )


class DisplayHelper:
    """
    Class that implements helper functions for displaying sets of data in a more readable form
    """

    # uniform string to display time
    @staticmethod
    def time_as_str(t: Any) -> str:
        """
        Returns the time in a standard format
        :param t: time
        :return: time as a string
        """
        return "{:0>2d}:{:0>2d}:{:0>2d}".format(t.hour, t.minute, t.second)

    @staticmethod
    def set_as_str(the_set: Any, display_names: Any = None, offset: int = 0) -> str:
        """
        Displays a set as a readable string. Adjacent elements are combined in x-y ranges. A list of strings can be passed
        to the set to map the values to text.
        :param the_set: set to display
        :param display_names: optional names for possible values in the set, values are used as index on the list
        :param offset: offset for indexing the values t values in the display_names list
        :return: set as a readable string
        """
        result = []

        def get_sub_sets() -> Iterator[set[Any]]:
            if the_set is not None and len(the_set) > 0:
                temp = sorted(the_set)
                last = temp[0]
                current = {temp[0]}

                for index in range(1, len(temp)):
                    if temp[index] == last + 1:
                        current.add(temp[index])
                    else:
                        yield current
                        current = {temp[index]}
                    last = temp[index]

                yield current

        for subset in get_sub_sets():
            s = (
                display_names[min(subset) - offset]
                if display_names
                else str(min(subset) - offset)
            )
            if len(subset) > 1:
                s = "-".join(
                    [
                        s,
                        display_names[max(subset) - offset]
                        if display_names
                        else str(max(subset) - offset),
                    ]
                )
            result.append(s)

        return ",".join(result)
