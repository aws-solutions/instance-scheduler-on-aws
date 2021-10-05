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

import os
from boto3.dynamodb.conditions import Key
from util.dynamodb_utils import DynamoDBUtils

class ScheduleState:

    def __init__(self, logger, service):
        self._logger = logger
        self.schedule_state_table_name = os.getenv("SCHEDULE_STATES_TABLE", None)
        self.dynamodb_table = DynamoDBUtils.get_dynamodb_table_resource_ref(self.schedule_state_table_name)
        self.service = service

    def get_schedule_state(self, schedule_name):
        self._logger.debug(f"Get scheduled state, for schedule name {schedule_name} for service {self.service}.")
        if schedule_name is not None:
            resp = self.dynamodb_table.get_item(
                Key={"name": schedule_name, 'service': self.service}, ConsistentRead=True)
            return resp.get("Item", {})
        else:
            self._logger.debug(f"Schedule unavailable for schedule name {schedule_name} for service {self.service}.")
            return {"name": schedule_name, 'service': self.service , "state": "unknown"}

    def save_schedule_state(self, schedule_name, state, localized_time, execution_id=None):
        self._logger.debug(f"Update state {state}, for schedule name {schedule_name} for service {self.service} at time {localized_time} to save schedule state.")
        get_schedule = self.get_schedule_state(schedule_name=schedule_name)
        if bool(get_schedule) is False:
            self._logger.debug(f"Previous state {state}, for schedule name {schedule_name}, at time {localized_time} is unavailable creating a new entry")
            try:
                resp = self.dynamodb_table.put_item(
                    Item={
                        'name': schedule_name,
                        'state': state,
                        'ssm-execution-id': execution_id,
                        'service': self.service,
                        'time': localized_time
                    }
                )
                return resp
            except Exception as error:
                self._logger.error(f"Error saving state {state}, for schedule name {schedule_name}, service {self.service}, at time {localized_time}")
                self._logger.error(error)
        else:
            try:
                return self.dynamodb_table.update_item(TableName=self.schedule_state_table_name, 
                                                        Key={"name": get_schedule["name"], 'service': self.service},
                                                        UpdateExpression="set #st =:s, #tm =:t, #ssmexecutionid =:e",
                                                        ExpressionAttributeNames={
                                                            "#ssmexecutionid": 'ssm-execution-id',
                                                            '#st': 'state',
                                                            '#tm': 'time'
                                                        },
                                                        ExpressionAttributeValues={
                                                            ":s": str(state),
                                                            ":t": str(localized_time),
                                                            ":e": str(execution_id)
                                                        },ReturnValues="UPDATED_NEW")
            except Exception as error:
                self._logger.error(f"Error updating state {state}, for schedule name {schedule_name} for service {self.service} at time {localized_time}")
                self._logger.error(error)

    def get_all_schedules(self):
        self._logger.debug("Retrieve all the schedules with previous states")
        schedules = []
        scan_kwargs = {
            'FilterExpression': Key('service').eq(self.service),
        }
        resp = self.dynamodb_table.scan(**scan_kwargs)
        schedules.extend(resp.get("Items"))
        while True:
            token = resp.get('LastEvaluatedKey', None)
            if token is not None:
                scan_kwargs = {
                    'ExclusiveStartKey': token,
                    'FilterExpression': Key('service').eq(self.service),
                }
                resp = self.dynamodb_table.scan(**scan_kwargs)
                schedules.extend(resp.get("Items"))
            else:
                break
        return schedules

    def delete_schedule(self, schedule_name):
        self._logger.debug(f"Remove the schedule {schedule_name} for service {self.service} and state.")
        if schedule_name is not None:
            try:
                self.dynamodb_table.delete_item(Key={"name": schedule_name, "service": self.service})
            except Exception as error:
                self._logger.error(f"Error removing schedule name {schedule_name} for service {self.service} and state.")
                self._logger.error(error)
