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

import requesthandlers
import configuration
import datetime
import pytz
from util.schedule_state import ScheduleState
import os
from schedulers.ssm_handler import SSMHandler
from util.logger import Logger

LOG_STREAM = "{}-{:0>4d}{:0>2d}{:0>2d}"
LOG_STREAM_PREFIX = "scheduler_ssm_handler"
ERR_INVALID_ARN = "{} is not a valid ARN"


class SchedulerSSMHandler:


    """
    Initializes the SchedulerSSMHandler, 
    :param event - lambda event
    :param context - lambda context
    :logger - logger implementation if none logger instance will be initialized.
    """
    def __init__(self, event, context, logger=None):
        self._context = context
        self._event = event
        if logger is None:
            self._is_trace_enabled = os.getenv("TRACE", False)
            logging_stream_name = "-".join([LOG_STREAM_PREFIX])
            dt = datetime.datetime.now()
            logstream = LOG_STREAM.format(logging_stream_name, dt.year, dt.month, dt.day)
            self._logger = Logger(logstream=logstream, buffersize=60 if self._is_trace_enabled else 30, context=self._context,debug=self._is_trace_enabled)
        else:
            self._logger = logger
        self._configuration = configuration.get_scheduler_configuration(self._logger)
        self._ssm_admin_role_name = os.getenv(requesthandlers.SSM_ADMIN_ROLE_NAME)
        self._execution_role_name = f"{self._configuration.namespace}-{self._configuration.execution_role_name}-{os.getenv('AWS_REGION')}"

    """
    private method used by get_schedules_state(...)
    """
    def get_periods_with_desired_states(self, periods, time):
        periods_with_desired_states = [
            {
                "period": p["period"],
                "instancetype": p.get("instancetype", None),
                "state": p["period"].get_desired_state(self._logger, time)
            }
            for p in periods]
        return periods_with_desired_states

    def get_schedules_state(self):
        """
        Retrieves the schedules from the configuration and evaluates the
        state of
        each schedule against the current time.
        :returns the list of items for each schedule with the attributes
            * schedule_name
            * periods_with_running_state
            * schedule_state
            * evaluated_time
        """
        schedules_state = []

        for schedule in self._configuration.schedules:
            schedule_data = self._configuration.get_schedule(schedule)
            localized_time = datetime.datetime.now(pytz.timezone(schedule_data.timezone))

            schedule = {
                "schedule_name": schedule,
                "periods_with_running_state": None,
                "schedule_state": "stopped",
                "evaluated_time": localized_time.isoformat(),
            }

            # get the desired state for every period in the schedule
            if schedule_data.periods is not None and len(schedule_data.periods) > 0:
                
                periods_with_desired_states = self.get_periods_with_desired_states(
                    schedule_data.periods, localized_time)
                # get periods from the schema that have a running state
                periods_with_running_state = [
                    p for p in periods_with_desired_states if p["state"] == "running"]

                if len(periods_with_running_state) > 0:
                    schedule["periods_with_running_state"] = periods_with_running_state
                    schedule["schedule_state"] = "running"
                    schedules_state.append(schedule)
                else:
                    schedules_state.append(schedule)
            else:
                schedules_state.append(schedule)
        return schedules_state

    def handle_schedule(self, schedule,
                        service,
                        scheduled_state_service,
                        ssm_handler):
        """
        Handles the schedule,
        * retrieves the schedule details i.e. previous execution from
        DynamoDB table,
        * if the schedule previous execution information is unavailable,
        the schedule state is used to either start/stop the instances,
            * ssm execution id for the start/stop runbook is saved in the
            dynamodb table along with the evaluated state i.e. running/stopped
        * if the schedule previous execution information is available,
        and the schedule state is same as before, no action is taken
        * if the schedule previous execution information is available,
        and the schedule state is different,
            * ssm execution id for the start/stop runbook is saved in the
            dynamodb table along with the evaluated state i.e. running/stopped
        """
        schedule_name = schedule.get("schedule_name")
        schedule_state = schedule.get("schedule_state")
        saved_schedule_state = scheduled_state_service.get_schedule_state(schedule_name)
        if bool(saved_schedule_state) is True and saved_schedule_state.get("state") == schedule_state:
            self._logger.info(f"schedule name {schedule_name} for service"
                              f"{service} has the state {schedule_state}, in"
                              f"dynamoDB and evaluated to the same state at "
                              f"the current time.")
            scheduled_state_service.save_schedule_state(
                schedule_name,
                schedule_state,
                schedule.get("evaluated_time"), 
                saved_schedule_state.get("ssm-execution-id"))
            return schedule
        else:
            self._logger.debug(f"schedule {schedule_name} for service {service} with state {schedule_state} sent to the SSM for triggering start/stop")
            if service == 'ec2':
                try:
                    schedule["execution_id"] = ssm_handler.run_ec2_instances_document(self._configuration.tag_name, schedule_name, schedule_state)
                except Exception as exception:
                    schedule["execution_id"] = 'error'
                    self._logger.error(f"Failed to initiate ec2 ssm automation for schedule {schedule_name} and service {service} instances, error {exception}")
            elif service == 'rds':
                try:
                    schedule["execution_id"] = "RDS Instances " + ssm_handler.run_rds_instances_document(self._configuration.tag_name, schedule_name, schedule_state)
                except Exception as exception:
                    schedule["execution_id"] = "RDS Instances " + "error"
                    self._logger.error(f"Failed to initiate rds ssm automation for schedule {schedule_name} and service {service} instances, error {exception}")
                # Check if the schedule cluster flag is True and trigger automation for scheduling RDS Clusters.
                if self._configuration.schedule_clusters:
                    try:
                        execution_id = ssm_handler.run_rds_clusters_document(self._configuration.tag_name, schedule_name, schedule_state)
                        schedule["execution_id"] = schedule.get("execution_id", "") + " RDS Clusters " + execution_id
                    except Exception as exception:
                        schedule["execution_id"] = schedule.get("execution_id", "") + " RDS Clusters " + "error"
                        self._logger.error(f"Failed to initiate rds clusters ssm automation for schedule {schedule_name} and service {service} Clusters, error {exception}")
            else:
                self._logger.info(f"Service {service} not supported")
            
            scheduled_state_service.save_schedule_state(
                schedule_name, 
                schedule_state, 
                schedule.get("evaluated_time"), 
                schedule.get("execution_id"))
            return schedule

    def handle_request(self):
        """ Entry method for the handling the scheduling of EC2/RDS
        instances using SSM Runbooks."""
        execution_status = 'SUCCESS'
        try:
            # instance scheduler will always ship with 2 services i.e ec2 and
            # rds. runtime complexity will always be 2 * (Number of schedules)
            self._logger.info(f"Starting scheduler_ssm_hanlder.")
            self._logger.debug(f"started tags, {self._configuration.started_tags}")
            self._logger.debug(f"stopped tags, {self._configuration.stopped_tags}")
            self._logger.debug(f"Execution Role Name {self._execution_role_name}")
            for service in self._configuration.scheduled_services:
                schedules_state = self.get_schedules_state()
                scheduled_state_service = ScheduleState(logger=self._logger,
                                                        service=service)
                existing_schedules = {}
                regions = list(self._configuration.regions)
                self._logger.debug(f"Scheduling for service {service} in Regions {regions}")
                # Get the list of accounts for scheduling.
                account_ids = list(self._configuration.remote_account_ids)
                self._logger.debug(f"Scheduling for service {service} in accounts {str(account_ids)}")
                if not account_ids:
                    self._logger.info(f"No account ids configured abandon scheduling.")
                    return "No account ids configured abandon scheduling."
                else:
                    ssm_handler = SSMHandler(
                        logger=self._logger,
                        accounts=account_ids,
                        regions=regions,
                        automation_assume_role_arn=self._ssm_admin_role_name,
                        execution_role_name=self._execution_role_name,
                        started_tags=self._configuration.started_tags,
                        stopped_tags=self._configuration.stopped_tags)

                    for schedule in schedules_state:
                        existing_schedules[schedule.get("schedule_name")] = self.handle_schedule(
                            schedule=schedule, 
                            service=service, 
                            scheduled_state_service=scheduled_state_service, 
                            ssm_handler=ssm_handler)
                    
                    # retrieve all the schedules in the dynamodb table and check if they are in the list schedules_state, delete them if they are not.
                    for saved_schedule in scheduled_state_service.get_all_schedules():
                        if existing_schedules.get(saved_schedule.get("name", None)) is None:
                            scheduled_state_service.delete_schedule(saved_schedule.get("name"))
                        
            return f"Scheduler SSM Handler completed. with Execution status as {execution_status}"
        except Exception as exception:
            self._logger.error(exception)
            execution_status = 'FAILED'
        finally:
            self._logger.flush()