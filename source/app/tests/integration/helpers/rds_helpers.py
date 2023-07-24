# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from typing import TYPE_CHECKING

import boto3

if TYPE_CHECKING:
    from mypy_boto3_rds import RDSClient
else:
    RDSClient = object


def get_rds_instance_state(instance_id: str) -> str:
    rds: RDSClient = boto3.client("rds")
    response = rds.describe_db_instances(DBInstanceIdentifier=instance_id)
    return response["DBInstances"][0]["DBInstanceStatus"]


def get_rds_cluster_state(cluster_id: str) -> str:
    rds: RDSClient = boto3.client("rds")
    response = rds.describe_db_clusters(DBClusterIdentifier=cluster_id)
    return response["DBClusters"][0]["Status"]
