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

import json
import sys

from collections import OrderedDict


def get_versioned_template(template_filename, bucket, solution, version):
    with open(template_filename, "rt") as f:
        template_text = "".join(f.readlines())
        template_text = template_text.replace("%bucket%", bucket)
        template_text = template_text.replace("%solution%", solution)
        template_text = template_text.replace("%version%", version)
        return json.loads(template_text, object_pairs_hook=OrderedDict)


def main(template_file, bucket, solution, version):
    template = get_versioned_template(template_file, bucket, solution, version)
    print(json.dumps(template, indent=4))


main(template_file=sys.argv[1], bucket=sys.argv[2], solution=sys.argv[3], version=sys.argv[4])

exit(0)
