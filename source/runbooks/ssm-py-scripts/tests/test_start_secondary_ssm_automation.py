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

from start_secondary_ssm_automation_rds_instance import split_arn_list
from start_secondary_ssm_automation_aurora_cluster import get_resource_list

db_arn_list = [
    "arn:aws:rds:us-east-1:account:db:database-name-1",
    "arn:aws:rds:us-east-1:account:db:database-name-2"
]

cluster_arn_list = [
    "arn:aws:rds:us-east-1:account:cluster:cluster-7jhu54i",
    "arn:aws:rds:us-east-1:account:cluster:name-cluster-2",
    "arn:aws:rds:us-east-1:account:cluster:name-cluster-1",
    "arn:aws:rds:us-east-1:account:cluster:cluster-ef5c4s7i"
]


def test_get_rds_db_ids():
    db_ids = split_arn_list(db_arn_list)
    for db_id in db_ids:
        assert db_id.startswith('database-name')
        assert ":" not in db_id


def test_get_rds_cluster_ids():
    cluster_ids = get_resource_list(cluster_arn_list)
    cluster_prefix = "cluster-"
    print(cluster_ids)
    for cluster_id in cluster_ids:
        assert not cluster_id.startswith(cluster_prefix)
