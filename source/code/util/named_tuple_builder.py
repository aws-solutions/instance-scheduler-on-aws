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

import collections


# check for dictionaries
def is_dict(o):
    return isinstance(o, type({}))


def is_array(o):
    return isinstance(o, type([]))


def tuple_name_func(name):
    result = "".join([c if c.isalnum() or c == '_' else "" for c in name.strip()])
    while result.startswith("_") or result[0].isdigit():
        result = result[1:]
    return result


# converts a dictionary in a named tuple
def as_namedtuple(name, d, deep=True, namefunc=None, excludes=None):
    name_func = namefunc if namefunc is not None else tuple_name_func

    if getattr(d, "keys") is None:
        return d

    if excludes is None:
        excludes = []

    dest = {}

    if deep:
        # deep copy to avoid modifications on input dictionaries
        for key in list(d):
            key_name = name_func(key)
            if is_dict(d[key]) and key not in excludes:
                dest[key_name] = as_namedtuple(key, d[key], namefunc=name_func, excludes=excludes, deep=True)
            elif is_array(d[key]) and key not in excludes:
                dest[key_name] = [as_namedtuple(key, i, namefunc=name_func, excludes=excludes, deep=True) for i in d[key]]
            else:
                dest[key_name] = d[key]
    else:
        dest = {name_func(key): d[key] for key in list(d)}

    return collections.namedtuple(name_func(name), list(dest))(*dest.values())
