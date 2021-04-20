######################################################################################################################
#  Copyright 2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.                                           #
#                                                                                                                    #
#  Licensed under the Apache License Version 2.0 (the "License"). You may not use this file except in compliance     #
#  with the License. A copy of the License is located at                                                             #
#                                                                                                                    #
#      http://www.apache.org/licenses/                                                                               #
#                                                                                                                    #
#  or in the "license" file accompanying this file. This file is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES #
#  OR CONDITIONS OF ANY KIND, express or implied. See the License for the specific language governing permissions    #
#  and limitations under the License.                                                                                #
######################################################################################################################

import logging


class SetBuilder:
    """
    # class for building set of values from values names or value strings
    """

    # all values in set
    WILDCARD_ALL = "*?"

    # first value in set
    WILDCARD_FIRST = "^"

    # last value in set
    WILDCARD_LAST = "$"

    # increment operator
    INCREMENT_CHARACTER = "/"

    # range operator
    RANGE_CHARACTER = '-'

    def __init__(self, names=None, min_value=None, max_value=None, offset=None, wrap=False,
                 ignorecase=True, significant_name_characters=None,
                 first_item_wildcard=WILDCARD_FIRST,
                 all_items_wildcards=WILDCARD_ALL,
                 last_item_wildcard=WILDCARD_LAST):
        """

        :param names: Names for values
        :param min_value: Value for first item in set created from min and max value
        :param max_value: Max value for value in set created from min and max value
        :param offset: Offset for first value in set created from names
        :param wrap: Set to True to let sets wrap at max value
        :param ignorecase: Set to True to ignore case when mapping values from their names
        :param significant_name_characters: Number of significant characters to use when mapping values from their names
        :param first_item_wildcard: First item wildcard
        :param all_items_wildcards: All Items wildcard
        :param last_item_wildcard: Last item wildcard
        """

        # use value names to setup builder
        if names is not None:
            # min-value and max_value are not allowed
            if min_value is not None or max_value is not None:
                raise ValueError("min_value and max_value parameters can not be used with names parameter")

            # names to display for values
            self._displaynames = [str(i) for i in names]
            # names to identify values, use only the specified number of significant characters
            self._names = names if significant_name_characters == 0 else [name[0:significant_name_characters] for name in names]
            # convert to lowercase if case is ignored
            if ignorecase:
                self._names = [name.lower() for name in self._names]
            # offset for values
            self._offset = offset if offset else 0
            self._min_value = self._offset
            self._max_value = len(names) - 1 + self._offset
            # build list to identify values by their numeric string value
            self._values = self.values = [str(i + self._offset) for i in range(0, len(self._names))]

        else:
            # setup builder with min and max values instead if names

            # both must be present
            if min_value is None or max_value is None:
                raise ValueError("min_value or max_value may not be None if names parameter is None")

            # min must be less or equal than max
            if min_value > max_value:
                raise ValueError("min_value parameter should be less or equal to max_value parameter")

            # build names to identify values
            self._names = [str(i) for i in range(min_value, max_value + 1)]
            self._min_value = min_value
            self._max_value = max_value
            self._values = self._names
            # names used for display
            self._displaynames = self._values
            # offset may not conflict with min value
            if offset is not None and offset != min_value:
                raise ValueError("offset parameter should not be used or have the same value as min_value")
            self._offset = min_value

        self._logging = logging.getLogger("SetBuilder")

        self._wrap = wrap
        self._ignorecase = ignorecase
        self._all_items_wildcard_characters = all_items_wildcards
        self._first_item_wildcard = first_item_wildcard
        self._last_item_wildcard_character = last_item_wildcard
        self._significant_name_characters = significant_name_characters \
            if names is not None and significant_name_characters is not None else 0

        # custom parsers to be executed before standard parsers
        self._pre_custom_parsers = []
        # custom parsers to be executes after standard parsers
        self._post_custom_parsers = []
        # setup list of standard parsers
        self._standard_parsers = [
            self._parse_name,  # name
            self._parse_value,  # value, first and last wildcard
            self._parse_name_range,  # name-name
            self._parse_value_range,  # value-value
            self._parse_all,  # all items wildcard
            self._parse_name_incr,  # name/incr
            self._parse_value_incr,  # value/incr
            self._parse_name_range_incr,  # name-name/incr
            self._parse_value_range_incr]  # value-value/incr

    def build(self, set_spec):
        """
        Builds set of values from string or list of strings
        :param set_spec: Sets as comma separated string or list of strings
        :return:
        """
        if isinstance(set_spec, str) or isinstance(set_spec, type(u"")):
            set_string_list = set_spec.split(",")
            return self._get_set_items(set_string_list)
        elif isinstance(set_spec, list) or isinstance(set_spec, set):
            return self.build(",".join(set_spec))
        else:
            raise ValueError("set_str argument must be of type string, set or array")

    def str(self, the_set):
        """
        Displays set as a string using ',' to separate values and '-' for sequent ranges
        :param the_set: Set to display
        :return: String to display the set in a normalized format
        """
        result = []

        # gets list of single and subsequent items in the set
        def get_sub_sets():
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

        # build string from subset
        for subset in get_sub_sets():
            s = self._displaynames[min(subset) - self._offset]
            if len(subset) > 1:
                s = "-".join([s, self._displaynames[max(subset) - self._offset]])
            result.append(s)

        return ", ".join(result)

    @property
    def first(self):
        """
        Return lowest possible value in set
        :return: Lowest possible value in set
        """
        return self._offset

    @property
    def last(self):
        """
        Return highest possible value in set
        :return: Highest possible value in set
        """
        return len(self._names) - 1 + self._offset

    @property
    def all(self):
        """
        Returns all items in set
        :return: All items in set
        """
        return set(self._all)

    @property
    def _all(self):
        # internal function to return all items in set
        return [val + self._offset for val in range(0, len(self._values))]

    def _parse_name(self, name_str):
        # gets a set item by its name
        return self._get_single_item(name_str, self._get_value_by_name)

    def _parse_value(self, value_str):
        # value
        return self._get_single_item(value_str, self._get_value_by_str)

    def _parse_name_range(self, name_range_str):
        # name-name
        return self._get_range_from_str(name_range_str, self._get_value_by_name)

    def _parse_value_range(self, value_range_str):
        # value-value
        return self._get_range_from_str(value_range_str, fn=self._get_value_by_str)

    def _parse_name_incr(self, name_incr_str):
        # name/incr
        return self._get_increment(name_incr_str, self._get_name_incr)

    def _parse_value_incr(self, value_incr_str):
        # value/incr
        return self._get_increment(value_incr_str, self._get_value_incr)

    def _parse_name_range_incr(self, name_range_incr_str):
        # name-name/incr
        return self._get_increment(name_range_incr_str, fn=self._get_name_range_incr)

    def _parse_value_range_incr(self, value_range_incr_str):
        # value-value/incr
        return self._get_increment(value_range_incr_str, fn=self._get_value_range_incr)

    def _parse_all(self, all_wildcard_str):
        # wildcards
        if len(all_wildcard_str) == 1 and all_wildcard_str in self._all_items_wildcard_characters:
            return self._all

    def _parse_unknown(self, _):
        # handle unknown items
        return None

    @property
    def _parsers(self):
        # flattened list of all parsers
        return [parser
                for parsers in [self._pre_custom_parsers, self._standard_parsers, self._post_custom_parsers]
                for parser in parsers]

    def _special_items(self):
        # special items that do not need pre-formatting or must be excluded from formatting
        return "".join([self._all_items_wildcard_characters,
                        self._first_item_wildcard,
                        self._last_item_wildcard_character])

    def _seperator_characters(self):
        # character that separates name from instructions like increments
        return SetBuilder.INCREMENT_CHARACTER

    def _get_set_items(self, set_string_list):
        # gets the items from a list of strings
        set_items = set()

        # for every string in the list
        for set_str in set_string_list:
            s = self._format_item(set_str)

            # go through list off all parsers for the builder class
            for parser in self._parsers:
                # execute parser
                value = parser(s)
                # did it return a value
                if value is not None:
                    self._logging.debug("Parser : {}(\"{}\") returns {}".format(parser.__name__, set_str, value))
                    # add result from parser to result set
                    if len(value) > 0:
                        set_items.update(set(value))
                    # if the parser is "all-items" wildcard there is no need for further processing as all items are in the result
                    if parser == self._parse_all:
                        return set_items
                    break
            else:
                # if this point is reached none of the parsers returned one or more items, try _parse_unknown
                value = self._parse_unknown(s)
                if value is not None:
                    self._logging.debug("{}(\"{}\") returns {}".format(self._parse_unknown.__name__, set_str, value))
                    # noinspection PyTypeChecker
                    set_items.update(set(value))
                else:
                    # if it does not return a value then raise an exception because of an unknown item
                    raise ValueError("\"{}\" is an unknown value".format(set_str))

        return set_items

    def _format_item(self, set_str):
        # pre-processes the item before trying to parse it
        s = set_str.strip()

        # immediately return if it is a special item
        if len(s) == 1 and s in self._special_items():
            return s

        str_after_separator = None

        # check if the string has a separator, in that case remove and store string after and including the character
        for c in self._seperator_characters():
            if c in s:
                i = s.index(c)
                str_after_separator = s[i:]
                s = s[0:i]
                break

        # truncate to significant characters
        if self._significant_name_characters > 0:
            s = SetBuilder.RANGE_CHARACTER.join(
                [t[0:self._significant_name_characters] for t in s.split(self.RANGE_CHARACTER)])

        # case sensitivity, to lowercase if case is ignored
        if self._ignorecase:
            s = s.lower()

        # append separator and remaining part if it was truncated
        if str_after_separator is not None:
            s += str_after_separator

        return s

    @staticmethod
    def _get_single_item(item_str, fn):
        # function to return single set items in a uniform way as a set
        value = fn(item_str)
        if value is not None:
            return [value]
        return None

    def _get_value_by_name(self, name_str):
        # gets the value of a set item by its name, also handled first and last item wildcards
        # internal iterator for testing for names
        def from_name(name):
            if name in self._names:
                return self._names.index(name) + self._offset
            return None

        # loop to test for name and wildcards
        for fn in [from_name, self._get_first_value, self._get_last_value]:
            value = fn(name_str)
            if value is not None:
                return value
        return None

    def _get_value_by_str(self, value_str):
        # gets the value of a set item by its numeric string
        s = value_str
        while len(s) > 1 and s[0] == "0":
            s = s[1:]
        if s in self._values:
            return self._values.index(s) + self._offset
        return None

    def _get_range_from_str(self, range_str, fn, incr=1):
        # gets a range from a string, items are retrieved using the function specified by fn
        # check if there is a range separator in the string
        set_range = range_str.split(self.RANGE_CHARACTER)
        # check for valid name of value for start
        if len(set_range) == 2:
            start = fn(set_range[0])
            if start is not None:
                # check for valid name or value for end
                end = fn(set_range[1])
                if end is not None:
                    return self._get_range(start, end, incr)
        return None

    def _get_last_value(self, last_wildcard_str):
        # returns the last possible value if the str is the last wildcard character
        if len(last_wildcard_str) == 1 and last_wildcard_str == self._last_item_wildcard_character:
            return self.last
        return None

    def _get_first_value(self, first_wildcard_str):
        # returns the first possible value if the str is the first item wildcard character
        if len(first_wildcard_str) == 1 and first_wildcard_str == self._first_item_wildcard:
            return self.first
        return None

    def _get_range(self, start, end, step=1):
        # gets a range of items for the specified start, end and step value

        # check if wrapping is needed and allowed
        if not self._wrap and start > end:
            raise ValueError("start ({}) must be less or equal to end ({}) if wrap is false".format(start, end))

        # this is the start
        result = [start]
        current = start
        skip_to_next_value = step
        # until we reach the end value
        while current != end:
            # get next
            current += 1
            skip_to_next_value -= 1
            # handle wrapping
            current %= len(self._values) + self._offset
            current = max(current, self._offset)

            # handle step
            if skip_to_next_value == 0:
                result.append(current)
                skip_to_next_value = step
        return result

    @staticmethod
    def _get_increment(incr_str, fn):
        # returns a set of values using a start value and a increment
        temp = incr_str.split(SetBuilder.INCREMENT_CHARACTER)
        # check if there is an increment character and if the increment value is present and valid
        if len(temp) == 2:
            try:
                incr = int(temp[1])
            except ValueError:
                raise ValueError("Increment value must be an integer value ({})".format(temp[1]))

            if incr <= 0:
                raise ValueError("Increment value must be > 0 ({})".format(incr))

            return fn(temp[0], incr)
        return None

    def _get_increment_by_string(self, incr_string, fn, incr):
        # get increment items for start value retrieved by function fn

        start = fn(incr_string)
        if start is not None:
            return self._get_range(start=start, end=self.last, step=incr)
        return None

    def _get_name_incr(self, name_incr_str, incr):
        # get increment items for start value retrieved by its name
        return self._get_increment_by_string(name_incr_str, self._get_value_by_name, incr)

    def _get_value_incr(self, value_incr_str, incr):
        # get increment items for start value retrieved by its value string
        return self._get_increment_by_string(value_incr_str, self._get_value_by_str, incr)

    def _get_range_increment(self, incr_str, fn, incr):
        # gets increment values from a range specified by the name of the start and end value retrieved by function fn
        set_range = self._get_range_from_str(incr_str, fn, incr)
        if set_range is not None:
            return set_range
        return None

    def _get_name_range_incr(self, name_range_incr_str, incr):
        # gets increment values from a range specified by the name of the start and end value retrieved by their names
        return self._get_range_increment(name_range_incr_str, self._get_value_by_name, incr)

    def _get_value_range_incr(self, value_range_incr_str, incr):
        # gets increment values from a range specified by the name of the start and end value retrieved by their value strings
        return self._get_range_increment(value_range_incr_str, self._get_value_by_str, incr)
