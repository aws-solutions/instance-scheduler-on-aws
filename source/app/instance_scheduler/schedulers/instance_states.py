# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import time
from decimal import Decimal
from typing import Any, Optional

from botocore.exceptions import ClientError

from instance_scheduler.configuration.instance_schedule import InstanceSchedule
from instance_scheduler.util.dynamodb_utils import DynamoDBUtils
from instance_scheduler.util.logger import Logger

INF_CLEANING = "Cleaning up instance registry."
INF_MOVING_FOR_PURGE = "Moving instance {} to be purged in next cleanup."
INF_REMOVING_INSTANCE = "Removing instance {} from instance registry."

WARN_LOADING_STATE = "Could not load instance state data {}, this warning should only occur once after creating the scheduler"


class InstanceStates:
    """
    Implements store for last desired state for service instances
    """

    INSTANCE_TABLE_TIMESTAMP = "timestamp"
    INSTANCE_TABLE_PURGE = "purge_in_next_cleanup"
    INSTANCE_TABLE_ACCOUNT_REGION = "account-region"
    INSTANCE_TABLE_NAME = "service"

    # cleanup interval time
    cleanup_interval = Decimal(12 * 3600)

    def __init__(self, table_name: str, service: str, logger: Logger) -> None:
        """
        Initializes instance of state store
        :param table_name: name of the state table
        :param service: name of the service
        :param logger: logger to log output of ste logic
        """
        self._table_name = table_name
        self._state_table = None
        self._state_info: dict[str, Any] = {}
        self._instances_to_purge: set[Any] = set()
        self._dirty: Optional[bool] = None
        self._timestamp: Decimal | float = Decimal(time.time())
        self._service = service
        self._current_account_region: Optional[str] = None
        self._logger = logger

    @property
    def state_table(self) -> Any:
        """
        Returns state table dynamodb table resource
        :return:
        """
        if self._state_table is None:
            self._state_table = DynamoDBUtils.get_dynamodb_table_resource_ref(
                self._table_name
            )
        return self._state_table

    def load(self, account: str, region: str) -> None:
        """
        Loads the desired state for the specified account and service
        :param account: account to load state for
        :param region: service to load state for
        :return:
        """
        self._dirty = False
        self._state_info = {}
        self._current_account_region = "{}:{}".format(account, region)

        # get single row from dynamoDB
        try:
            resp = self.state_table.get_item(
                Key={
                    InstanceStates.INSTANCE_TABLE_NAME: self._service,
                    InstanceStates.INSTANCE_TABLE_ACCOUNT_REGION: self._current_account_region,
                },
                ConsistentRead=True,
            )
            item = resp.get("Item", {})
        except ClientError as ex:
            self._logger.warning(WARN_LOADING_STATE, str(ex))
            item = {}

        # time of last update
        if InstanceStates.INSTANCE_TABLE_TIMESTAMP in item:
            self._timestamp = item[InstanceStates.INSTANCE_TABLE_TIMESTAMP]
        else:
            self._timestamp = Decimal(time.time())

        # instance states, one column per instance
        self._state_info = {
            i: item[i]
            for i in item
            if i
            not in [
                InstanceStates.INSTANCE_TABLE_TIMESTAMP,
                InstanceStates.INSTANCE_TABLE_NAME,
                InstanceStates.INSTANCE_TABLE_ACCOUNT_REGION,
                InstanceStates.INSTANCE_TABLE_PURGE,
            ]
        }

        # items to purge
        if InstanceStates.INSTANCE_TABLE_PURGE in item:
            self._instances_to_purge = item[InstanceStates.INSTANCE_TABLE_PURGE]

    def set_instance_state(self, instance_id: str, new_state: str) -> None:
        """
        Sets the state of an instance
        :param instance_id: id of the instance
        :param new_state: new state
        :return:
        """
        # get stored state
        state = self._state_info.get(instance_id, None)
        # only update if changed
        if not state or state != new_state:
            self._state_info[instance_id] = new_state
            self._dirty = True

    def get_instance_state(self, instance_id):
        """
        gets the stored state of an instance
        :param instance_id: id of the instance
        :return:
        """
        state = self._state_info.get(instance_id, None)
        return state if state else InstanceSchedule.STATE_UNKNOWN

    def delete_instance_state(self, instance_id: str) -> None:
        """
        Removes the state of an instance
        :param instance_id: id of the instance
        :return:
        """
        if instance_id in self._state_info:
            del self._state_info[instance_id]
            if instance_id in self._instances_to_purge:
                self._instances_to_purge.remove(instance_id)
            self._dirty = True

    def save(self) -> None:
        """
        Stores the instance state information to the dynamodb table if it has changed
        :return:
        """
        if self._dirty:
            # key and timestamp
            data: dict[str, Any] = {
                InstanceStates.INSTANCE_TABLE_NAME: self._service,
                InstanceStates.INSTANCE_TABLE_ACCOUNT_REGION: self._current_account_region,
                InstanceStates.INSTANCE_TABLE_TIMESTAMP: Decimal(time.time()),
            }

            # store instance states as one column per instance
            for i in self._state_info:
                data[i] = self._state_info[i]

            # instances to purge
            if len(self._instances_to_purge) > 0:
                data[InstanceStates.INSTANCE_TABLE_PURGE] = self._instances_to_purge

            self.state_table.put_item(Item=data)
            self._dirty = False

    def cleanup(self, instances: list[str]) -> None:
        """
        Removes instance id's from the table that have been terminated or not being processed by the scheduler.
        This code contains workaround for instances not being returned by describe_instances when changing state
        When an instance is not listed it is marked for removal at next cleanup if it is not found again
        :param instances:
        :return:
        """
        # cleanup only if the last cleanup was more than a the configured interval ago
        if (
            Decimal(time.time()) - Decimal(self._timestamp)
        ) > InstanceStates.cleanup_interval:
            self._logger.info(INF_CLEANING)
            self._timestamp = time.time()
            self._dirty = True

            # get key of stored instances
            stored_instances = [i for i in list(self._state_info)]
            for i in stored_instances:
                # test if instance was still there
                if i not in instances:
                    # if not test is it was also not there in last cleanup
                    if i in self._instances_to_purge:
                        # remove instance
                        del self._state_info[i]
                        self._instances_to_purge.remove(i)
                        self._logger.info(INF_REMOVING_INSTANCE, i)
                    else:
                        # when instance is not there queue it for removal in next cleanup
                        # this step is needed because instances don't show op in describe-instances when changing state
                        self._instances_to_purge.add(i)
                        self._dirty = True
                        self._logger.info(INF_MOVING_FOR_PURGE, i)
                elif i in self._instances_to_purge:
                    # the instance was not returned by describe instances at last cleanup but it is this time
                    self._instances_to_purge.remove(i)
