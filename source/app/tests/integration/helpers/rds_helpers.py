# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from typing import TYPE_CHECKING

import boto3
from mypy_boto3_rds.type_defs import (
    CreateDBClusterResultTypeDef,
    CreateDBInstanceResultTypeDef,
)

from tests.integration.helpers.boto_client_helpers import client_in_account_region

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


def stop_rds_instances(
    *instance_ids: str,
    account: str = "123456789012",
    region: str = "us-east-1",
) -> None:
    rds: RDSClient = client_in_account_region("rds", account, region)
    for rds_instance in instance_ids:
        rds.stop_db_instance(DBInstanceIdentifier=rds_instance)


def create_rds_instances(
    count: int,
    schedule_name: str = "test-schedule",
    account: str = "123456789012",
    region: str = "us-east-1",
    instance_type: str = "db.m5.large",
    engine: str = "postgres",
    id_prefix: str = "test-rds-instance",
    preferred_maintenance_window: str = "mon:01:00-mon:01:30",
) -> tuple[str, ...]:
    rds_client: RDSClient = client_in_account_region("rds", account, region)

    ids: list[str] = list()
    for i in range(count):
        instance_id = f"{id_prefix}-{i}"
        result: CreateDBInstanceResultTypeDef = rds_client.create_db_instance(
            DBInstanceIdentifier=instance_id,
            DBInstanceClass=instance_type,
            Engine=engine,
            PreferredMaintenanceWindow=preferred_maintenance_window,
            BackupRetentionPeriod=0,
        )
        instance_arn = result["DBInstance"]["DBInstanceArn"]
        rds_client.add_tags_to_resource(
            ResourceName=instance_arn,
            Tags=[{"Key": "Schedule", "Value": schedule_name}],
        )
        ids.append(instance_id)

    return tuple(ids)


def create_rds_clusters(
    count: int,
    schedule_name: str = "test-schedule",
    account: str = "123456789012",
    region: str = "us-east-1",
    instance_type: str = "db.m5.large",
    engine: str = "postgres",
    id_prefix: str = "test-rds-instance",
) -> tuple[str, ...]:
    rds_client: RDSClient = client_in_account_region("rds", account, region)

    ids: list[str] = list()
    for i in range(count):
        instance_id = f"{id_prefix}-{i}"
        result: CreateDBClusterResultTypeDef = rds_client.create_db_cluster(
            DBClusterIdentifier=instance_id,
            DBClusterInstanceClass=instance_type,
            Engine=engine,
            MasterUsername="user",
            MasterUserPassword="password",
        )
        instance_arn = result["DBCluster"]["DBClusterArn"]
        rds_client.add_tags_to_resource(
            ResourceName=instance_arn,
            Tags=[{"Key": "Schedule", "Value": schedule_name}],
        )
        ids.append(instance_id)

    return tuple(ids)


def start_rds_instances(
    *instance_ids: str,
    account: str = "123456789012",
    region: str = "us-east-1",
) -> None:
    rds: RDSClient = client_in_account_region("rds", account, region)
    for rds_instance in instance_ids:
        rds.start_db_instance(DBInstanceIdentifier=rds_instance)


def stop_rds_clusters(
    *cluster_ids: str,
    account: str = "123456789012",
    region: str = "us-east-1",
) -> None:
    rds: RDSClient = client_in_account_region("rds", account, region)
    for rds_cluster in cluster_ids:
        rds.stop_db_cluster(DBClusterIdentifier=rds_cluster)


def start_rds_clusters(
    *cluster_ids: str,
    account: str = "123456789012",
    region: str = "us-east-1",
) -> None:
    rds: RDSClient = client_in_account_region("rds", account, region)
    for rds_cluster in cluster_ids:
        rds.start_db_cluster(DBClusterIdentifier=rds_cluster)
