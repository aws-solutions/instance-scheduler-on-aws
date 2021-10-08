######################################################################################################################
#  Copyright 2021 Amazon.com, Inc. or its affiliates. All Rights Reserved.                                           #
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

from requesthandlers.scheduler_setup_handler import SchedulerSetupHandler

def test_a_valid_org_id_pattern():

    handler = SchedulerSetupHandler({
        "ResourceProperties": {
            'stack_version': 'test'
        }
    }, {})
    response = handler.is_valid_org_id("o-x1mhq1lvsr")
    assert response != None

def test_an_invalid_org_id_pattern():

    handler = SchedulerSetupHandler({
        "ResourceProperties": {
            'stack_version': 'test'
        }
    }, {})
    response = handler.is_valid_org_id("111111111111,222222222222")
    assert response == None