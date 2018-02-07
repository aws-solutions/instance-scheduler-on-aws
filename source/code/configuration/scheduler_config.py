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
import copy
import os

from datetime import datetime

import configuration

# class to hold the configuration for the instance scheduler
INF_SCHEDULE_DISPLAY = "Configuration:\n" \
                       "Scheduled services = \"{}\"\n" \
                       "Tagname = \"{}\"\n" \
                       "Default timezone = \"{}\"\n" \
                       "Trace = \"{}\"\n" \
                       "Use metrics = \"{}\"\n" \
                       "Regions = \"{}\"\n" \
                       "Started tags = \"{}\"\n" \
                       "Stopped tags = \"{}\"\n" \
                       "Process Lambda account = \"{}\"\n" \
                       "Cross account roles = \"{}\""

TAG_VAL_STR = "{{{}}}"


class SchedulerConfig:
    """
    Implements scheduler configuration
    """

    def __init__(self, scheduled_services, tag_name, regions, default_timezone, schedules, trace,
                 use_metrics, cross_account_roles, schedule_lambda_account, started_tags=None, stopped_tags=None):
        """
        Initializes schedule configuration instance
        :param scheduled_services: services handled by the scheduler
        :param tag_name: name of the tag to define schedule for instances
        :param regions: regions to handle
        :param default_timezone: default timezone for schedules
        :param schedules: instance running schedules
        :param trace: set to true for detailed logging
        :param use_metrics: global flag to enable metrics collection
        :param cross_account_roles: cross account roles for cross account scheduling
        :param schedule_lambda_account: set to true to schedule instances in account in which scheduler is installed
        :param started_tags: start tags in string format
        :param stopped_tags: stop tags in string format
        """
        self.tag_name = tag_name
        self.schedules = schedules
        self.default_timezone = default_timezone
        self.trace = trace
        self.use_metrics = use_metrics
        self.regions = regions
        self.cross_account_roles = cross_account_roles
        self.schedule_lambda_account = schedule_lambda_account
        self.scheduled_services = scheduled_services
        self._service_settings = None
        self._start_tags = started_tags
        self._stop_tags = stopped_tags

    def get_schedule(self, name):
        """
        Get a schedule by its name
        :param name: name of the schedule
        :return: Schedule, None f it does not exist
        """
        return self.schedules[name] if name in self.schedules else None

    @property
    def started_tags(self):
        """
        Return tags to set to started instances
        :return:  tags for started instances
        """
        if self._start_tags in ["" or None]:
            return []
        else:
            return self.tag_list(self.build_tags_from_template(self._start_tags))

    @property
    def stopped_tags(self):
        """
              Return tags to set to stopped instances
              :return:  tags for stopped instances
              """
        if self._stop_tags in ["" or None]:
            return []
        else:
            return self.tag_list(self.build_tags_from_template(self._stop_tags))

    @classmethod
    def build_tags_from_template(cls, tags_str, tag_variables=None):

        lastkey = None
        tags = {}
        for tag in tags_str.split(","):
            if "=" in tag:
                t = tag.partition("=")
                tags[t[0]] = t[2]
                lastkey = t[0]
            elif lastkey is not None:
                tags[lastkey] = ",".join([tags[lastkey], tag])

        tag_vars = {} if tag_variables is None else copy.copy(tag_variables)

        dt = datetime.utcnow()
        tag_vars.update({
            configuration.TAG_VAL_SCHEDULER: os.getenv(configuration.ENV_STACK, ""),
            configuration.TAG_VAL_YEAR: "{:0>4d}".format(dt.year),
            configuration.TAG_VAL_MONTH: "{:0>2d}".format(dt.month),
            configuration.TAG_VAL_DAY: "{:0>2d}".format(dt.day),
            configuration.TAG_VAL_HOUR: "{:0>2d}".format(dt.hour),
            configuration.TAG_VAL_MINUTE: "{:0>2d}".format(dt.minute),
            configuration.TAG_VAL_TIMEZONE: "UTC"
        })

        for tag in tags:
            value = tags[tag]
            if value not in ["", None]:
                for v in tag_vars:
                    tags[tag] = tags[tag].replace(TAG_VAL_STR.format(v), tag_vars[v])
        return tags

    @classmethod
    def tag_list(cls, tags_dict):
        valid_tags = {tag_key: tags_dict[tag_key] for tag_key in tags_dict if
                      not (tag_key.startswith("aws:") or tag_key.startswith("cloudformation:"))}
        return [{"Key": t, "Value": tags_dict[t]} for t in tags_dict] if valid_tags is not None else []

    def __str__(self):
        s = INF_SCHEDULE_DISPLAY.format(", ".join(self.scheduled_services),
                                        self.tag_name,
                                        self.default_timezone,
                                        str(self.trace),
                                        str(self.use_metrics),
                                        ", ".join(self.regions),
                                        self._start_tags,
                                        self._stop_tags,
                                        str(self.schedule_lambda_account),
                                        ", ".join(self.cross_account_roles))

        return s
