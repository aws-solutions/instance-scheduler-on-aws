######################################################################################################################
#  Copyright 2016 Amazon.com, Inc. or its affiliates. All Rights Reserved.                                           #
#                                                                                                                    #
#  Licensed under the Amazon Software License (the "License"). You may not use this file except in compliance        #
#  with the License. A copy of the License is located at                                                             #
#                                                                                                                    #
#      http://aws.amazon.com/asl/                                                                                    #
#                                                                                                                    #
#  or in the "license" file accompanying this file. This file is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES #
#  OR CONDITIONS OF ANY KIND, express or implied. See the License for the specific language governing permissions    #
#  and limitations under the License.                                                                                #
######################################################################################################################

import json
import sys

from collections import OrderedDict

from jinja2 import Template

def get_versioned_template(template_filename, **args):
    with open(template_filename, "r") as f:
        template = Template(f.read())
        template_text = template.render(**args)
        return json.loads(template_text, object_pairs_hook=OrderedDict)


def main(template_file, **args):
    template = get_versioned_template(template_file, **args)
    print(json.dumps(template, indent=4))


main(template_file=sys.argv[1], version=sys.argv[2], bucket=sys.argv[3], prefix=sys.argv[4], s3_mirrors=sys.argv[5] == "true")

exit(0)
