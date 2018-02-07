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


import argparse
import json
import sys

import boto3
import jmespath

EVENT_SOURCE = "scheduler.cli"

HELP_CMD_CREATE_PERIOD = "Creates a period"
HELP_CMD_CREATE_SCHEDULE = "Creates a schedule"
HELP_CMD_DELETE_SCHEDULE = "Deletes a schedule"
HELP_CMD_DELETE_PERIOD = "Deletes a period"
HELP_CMD_DESCRIBE_PERIODS = "Describess configured periods"
HELP_CMD_DESCRIBE_SCHEDULES = "Described configured schedules"
HELP_CMD_SCHEDULE_DESCRIBE_USAGE = "Calculates periods and billing hours in which instances are running"
HELP_CMD_UPDATE_PERIOD = "Updates a period"
HELP_CMD_UPDATE_SCHEDULE = "Updates a schedule"
CMD_HELP_VERSION = "Show version"

HELP_ENDDATE = "End time of the period in format yyyymmdd, default is today"
HELP_NAME_SCHEDULE = "Name of the schedule"
HELP_PERIOD_BEGINTIME = "Begin time of the period in hotmat hh:mm"
HELP_PERIOD_DESCRIPTION = "Description for the period"
HELP_PERIOD_ENDTIME = "End time of the period in format hh:mm"
HELP_PERIOD_MONTH_DAYS = "Calendar monthdays of the period"
HELP_PERIOD_NAME = "Name of the period"
HELP_PERIOD_WEEKDAYS = "Weekdays of the period"
HELP_QUERY = "JMESPath query to transform or filter the result"
HELP_REGION = "Region in which the Instance Scheduler stack is deployed"
HELP_SCHEDULE_CLOUDWATCH_METRICS = "Enable/disable CloudWatch metrics for this schedule"
HELP_SCHEDULE_DESCRIPTION = "Description for the schedule."
HELP_SCHEDULE_ENFORCED = "Enforce schedule state for instance."
HELP_SCHEDULE_RETAIN_RUNNING = "keep instances running at end of period if they were already running at start of period"
HELP_SCHEDULE_NAME = "Name of the schedule"

HELP_PARAM_TIMEZONE = "Timezone for schedule"
HELP_SCHEDULE_OVERRIDE_STATUS = "Override status to keep instances in specified state."
HELP_SCHEDULE_PERIODS = "List of the names of the periods in the schedule. Each period can specify an instance type by " \
                        "appending @<type> to the name of the period."
HELP_SCHEDULE_STOP_NEW = "Stop new instances if outside of a running period"
HELP_SCHEDULE_USE_MAIN = "Use prefered maintenace windows of RDS instances as a running period."
HELP_STACK = "Name of the Instance Scheduler stack"
HELP_STARTDATE = "Start time of the period in format yyyymmdd, default is today"
HELP_SUB_COMMANDS = "Commands help"
HELP_VALID_COMMANDS = "Valid subcommands"

PROG_NAME = "scheduler-cli"
VALUES_OVERRIDE_STATUS = ["stopped", "running"]

PARAM_BEGINTIME = "--begintime"
PARAM_DESCRIPTION = "--description"
PARAM_ENDDATE = "--enddate"
PARAM_ENDTIME = "--endtime"
PARAM_ENFORCED = "--enforced"
PARAM_RETAINED_RUNNING = "--retain-running"
PARAM_METRICS = "--metrics"
PARAM_MONTHDAYS = "--monthdays"
PARAM_OVERRIDE = "--override-status"
PARAM_PERIODS = "--periods"
PARAM_STARTDATE = "--startdate"
PARAM_STOP_NEW = "--stop-new-instances"
PARAM_USE_MAIN = "--use-maintenance-window"
PARAM_WEEKDAYS = "--weekdays"
PARAM_TIMEZONE = "--timezone"

PARAM_STACK = "--stack"
PARAM_REGION = "--region"
PARAM_QUERY = "--query"
COMMON_PARAMS = [s[2:] for s in [PARAM_QUERY, PARAM_REGION, PARAM_STACK, ]] + ["command"]

CMD_CREATE_PERIOD = "create-period"
CMD_CREATE_SCHEDULE = "create-schedule"
CMD_DELETE_PERIOD = "delete-period"
CMD_DELETE_SCHEDULE = "delete-schedule"
CMD_DESCRIBE_PERIODS = "describe-periods"
CMD_DESCRIBE_SCHEDULE_USAGE = "describe-schedule-usage"
CMD_DESCRIBE_SCHEDULES = "describe-schedules"
CMD_UPDATE_PERIOD = "update-period"
CMD_UPDATE_SCHEDULE = "update-schedule"
CMD_VERSION = "--version"

PARAM_NAME = "--name"


def _service_client(service, region=None):
    args = {"service_name": service}
    if region is not None:
        args["region_name"] = region
    return boto3.client(**args)


def handle_command(args, command):
    try:
        cloudformation_client = _service_client("cloudformation", region=args.region)
        lambda_resource = cloudformation_client.describe_stack_resource(
            StackName=args.stack, LogicalResourceId="Main").get("StackResourceDetail", None)

        lambda_client = boto3.client("lambda")

        event = {
            "source": EVENT_SOURCE,
            "action": command,
            "parameters": {a: getattr(args, a) for a in args.__dict__ if
                           (a not in COMMON_PARAMS
                            and getattr(args, a) is not None
                            and not hasattr(getattr(args, a), "__call__"))}
        }

        payload = str.encode(json.dumps(event))
        lambda_name = lambda_resource["PhysicalResourceId"]

        # start lambda function
        resp = lambda_client.invoke(FunctionName=lambda_name,
                                    InvocationType="RequestResponse",
                                    LogType="None",
                                    Payload=payload)

        # read lambda response and load json
        lambda_response = resp["Payload"].read().decode("utf-8")
        result = json.loads(lambda_response)

        # Error if api raised an exception
        if "Error" in result:
            print(result["Error"].capitalize())
            return 1

        # perform transformation of output
        if args.query:
            result = jmespath.search(args.query, result)

        # print output as formatted json
        print(json.dumps(result, indent=3))
        return 0

    except Exception as ex:
        print(ex)
        return 1


def build_parser():
    def add_common_arguments(parser):
        parser.add_argument(PARAM_QUERY, help=HELP_QUERY)
        parser.add_argument(PARAM_REGION, help=HELP_REGION)
        parser.add_argument(PARAM_STACK, PARAM_STACK[1:3], required=True, help=HELP_STACK)

    def add_period_arguments(period_parser):
        period_parser.add_argument(PARAM_BEGINTIME, help=HELP_PERIOD_BEGINTIME)
        period_parser.add_argument(PARAM_DESCRIPTION, help=HELP_PERIOD_DESCRIPTION)
        period_parser.add_argument(PARAM_ENDTIME, help=HELP_PERIOD_ENDTIME)
        period_parser.add_argument(PARAM_MONTHDAYS, help=HELP_PERIOD_MONTH_DAYS)
        period_parser.add_argument(PARAM_NAME, required=True, help=HELP_PERIOD_NAME)
        period_parser.add_argument(PARAM_WEEKDAYS, help=HELP_PERIOD_WEEKDAYS)

    def add_schedule_arguments(schedule_parser):
        schedule_parser.add_argument(PARAM_DESCRIPTION, help=HELP_SCHEDULE_DESCRIPTION)
        schedule_parser.add_argument(PARAM_ENFORCED, type=bool, default=False, help=HELP_SCHEDULE_ENFORCED)
        schedule_parser.add_argument(PARAM_RETAINED_RUNNING, type=bool, default=False, help=HELP_SCHEDULE_RETAIN_RUNNING)
        schedule_parser.add_argument(PARAM_TIMEZONE, help=HELP_PARAM_TIMEZONE)
        schedule_parser.add_argument(PARAM_METRICS, type=bool, help=HELP_SCHEDULE_CLOUDWATCH_METRICS)
        schedule_parser.add_argument(PARAM_NAME, required=True, help=HELP_SCHEDULE_NAME)
        schedule_parser.add_argument(PARAM_OVERRIDE, choices=VALUES_OVERRIDE_STATUS, help=HELP_SCHEDULE_OVERRIDE_STATUS)
        schedule_parser.add_argument(PARAM_PERIODS, type=str, help=HELP_SCHEDULE_PERIODS)
        schedule_parser.add_argument(PARAM_STOP_NEW, type=bool, default=True, help=HELP_SCHEDULE_STOP_NEW)
        schedule_parser.add_argument(PARAM_USE_MAIN, type=bool, help=HELP_SCHEDULE_USE_MAIN)

    def build_describe_schedules_parser():
        sub_parser = subparsers.add_parser(CMD_DESCRIBE_SCHEDULES, help=HELP_CMD_DESCRIBE_SCHEDULES)
        sub_parser.add_argument(PARAM_NAME, help=HELP_NAME_SCHEDULE)
        add_common_arguments(sub_parser)
        sub_parser.set_defaults(func=handle_command, command=CMD_DESCRIBE_SCHEDULES)

    def build_describe_periods_parser():
        sub_parser = subparsers.add_parser(CMD_DESCRIBE_PERIODS, help=HELP_CMD_DESCRIBE_PERIODS)
        sub_parser.add_argument(PARAM_NAME, help=HELP_PERIOD_NAME)
        add_common_arguments(sub_parser)
        sub_parser.set_defaults(func=handle_command, command=CMD_DESCRIBE_PERIODS)

    def build_create_period_parser():
        sub_parser = subparsers.add_parser(CMD_CREATE_PERIOD, help=HELP_CMD_CREATE_PERIOD)
        add_period_arguments(sub_parser)
        add_common_arguments(sub_parser)
        sub_parser.set_defaults(func=handle_command, command=CMD_CREATE_PERIOD)

    def build_create_schedule_parser():
        sub_parser = subparsers.add_parser(CMD_CREATE_SCHEDULE, help=HELP_CMD_CREATE_SCHEDULE)
        add_schedule_arguments(sub_parser)
        add_common_arguments(sub_parser)
        sub_parser.set_defaults(func=handle_command, command=CMD_CREATE_SCHEDULE)

    def build_update_period_parser():
        sub_parser = subparsers.add_parser(CMD_UPDATE_PERIOD, help=HELP_CMD_UPDATE_PERIOD)
        add_period_arguments(sub_parser)
        add_common_arguments(sub_parser)
        sub_parser.set_defaults(func=handle_command, command=CMD_UPDATE_PERIOD)

    def build_update_schedule_parser():
        sub_parser = subparsers.add_parser(CMD_UPDATE_SCHEDULE, help=HELP_CMD_UPDATE_SCHEDULE)
        add_schedule_arguments(sub_parser)
        add_common_arguments(sub_parser)
        sub_parser.set_defaults(func=handle_command, command=CMD_UPDATE_SCHEDULE)

    def build_delete_period_parser():
        sub_parser = subparsers.add_parser(CMD_DELETE_PERIOD, help=HELP_CMD_DELETE_PERIOD)
        sub_parser.add_argument(PARAM_NAME, help=HELP_PERIOD_NAME)
        add_common_arguments(sub_parser)
        sub_parser.set_defaults(func=handle_command, command=CMD_DELETE_PERIOD)

    def build_delete_schedule_parser():
        sub_parser = subparsers.add_parser(CMD_DELETE_SCHEDULE, help=HELP_CMD_DELETE_SCHEDULE)
        sub_parser.add_argument(PARAM_NAME, PARAM_NAME[1:3], help=HELP_SCHEDULE_NAME)
        add_common_arguments(sub_parser)
        sub_parser.set_defaults(func=handle_command, command=CMD_DELETE_SCHEDULE)

    def build_describe_schedule_usage_parser():
        sub_parser = subparsers.add_parser(CMD_DESCRIBE_SCHEDULE_USAGE, help=HELP_CMD_SCHEDULE_DESCRIBE_USAGE)
        sub_parser.add_argument(PARAM_ENDDATE, help=HELP_ENDDATE)
        sub_parser.add_argument(PARAM_NAME, required=True, help=HELP_SCHEDULE_NAME)
        sub_parser.add_argument(PARAM_STARTDATE, help=HELP_STARTDATE)
        add_common_arguments(sub_parser)
        sub_parser.set_defaults(func=handle_command, command=CMD_DESCRIBE_SCHEDULE_USAGE)

    new_parser = argparse.ArgumentParser(prog=PROG_NAME)
    new_parser.add_argument(CMD_VERSION, action='version', version='%(prog)s #version#')
    subparsers = new_parser.add_subparsers(help=HELP_SUB_COMMANDS, description=HELP_VALID_COMMANDS)

    build_create_period_parser()
    build_create_schedule_parser()
    build_delete_period_parser()
    build_delete_schedule_parser()
    build_describe_periods_parser()
    build_describe_schedule_usage_parser()
    build_describe_schedules_parser()
    build_update_period_parser()
    build_update_schedule_parser()

    return new_parser


def main():
    parser = build_parser()
    p = parser.parse_args(sys.argv[1:])
    sys.exit( p.func(p, p.command))


