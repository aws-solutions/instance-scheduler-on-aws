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
import time
from datetime import datetime

import boto_retry

LOG_FORMAT = "{:7s} : {}"

ENV_LOG_GROUP = "LOG_GROUP"
ENV_ISSUES_TOPIC_ARN = "ISSUES_TOPIC_ARN"
ENV_SUPPRESS_LOG_STDOUT = "SUPPRESS_LOG_TO_STDOUT"

LOG_LEVEL_INFO = "INFO"
LOG_LEVEL_ERROR = "ERROR"
LOG_LEVEL_WARNING = "WARNING"
LOG_LEVEL_DEBUG = "DEBUG"

LOG_MAX_BATCH_SIZE = 1048576
LOG_ENTRY_ADDITIONAL = 26


class Logger:
    """
    Wrapper class for CloudWatch logging with buffering and helper methods
    """

    def __init__(self, logstream, context, loggroup=None, buffersize=10, debug=False):

        def get_loggroup(lambda_context):
            group = os.getenv(ENV_LOG_GROUP, None)
            if group is None:
                if lambda_context is None:
                    return None
                group = lambda_context.log_group_name
            return group

        self._logstream = logstream
        self._buffer_size = min(buffersize, 10000)
        self._context = context
        self._buffer = []
        self._debug = debug
        self._cached_size = 0
        self._client = None
        self._log_sequence_token = None
        self._loggroup = loggroup if loggroup is not None else get_loggroup(self._context)

        self._sns = None

    def __enter__(self):
        """
        Returns itself as the managed resource.
        :return:
        """
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Writes all cached action items to dynamodb table when going out of scope
        :param exc_type:
        :param exc_val:
        :param exc_tb:
        :return:
        """
        self.flush()

    def _emit(self, level, msg, *args):

        s = msg if len(args) == 0 else msg.format(*args)
        t = time.time()
        s = LOG_FORMAT.format(level, s)

        if self._cached_size + (len(s) + LOG_ENTRY_ADDITIONAL) > LOG_MAX_BATCH_SIZE:
            self.flush()

        self._cached_size += len(s) + LOG_ENTRY_ADDITIONAL

        if self._context is None and str(os.getenv(ENV_SUPPRESS_LOG_STDOUT, False)).lower() != "true":
            print("> " + s)
        self._buffer.append((int(t * 1000), s))

        if len(self._buffer) >= self._buffer_size:
            self.flush()

        return s

    @property
    def debug_enabled(self):
        """
        Return debug on/off switch
        :return: debug on/of
        """
        return self._debug

    @property
    def sns(self):
        if self._sns is None:
            self._sns = boto_retry.get_client_with_retries("sns", ["publish"], context=self._context)
        return self._sns

    @debug_enabled.setter
    def debug_enabled(self, value):
        """
        Sets debug switch
        :param value: True to enable debugging, False to disable
        :return:
        """
        self._debug = value

    def publish_to_sns(self, level, msg):
        """
        Publish message to sns topic
        :param msg:
        :param level:
        :return:
        """
        sns_arn = os.getenv(ENV_ISSUES_TOPIC_ARN, None)
        if sns_arn is not None:
            message = "Loggroup: {}\nLogstream {}\n{} : {}".format(self._loggroup, self._logstream, level, msg)
            self.sns.publish_with_retries(TopicArn=sns_arn, Message=message)

    def info(self, msg, *args):
        """
        Logs informational message
        :param msg: Message format string
        :param args: Message parameters
        :return:
        """
        self._emit(LOG_LEVEL_INFO, msg, *args)

    def error(self, msg, *args):
        """
        Logs error message
        :param msg: Error message format string
        :param args: parameters
        :return:
        """
        s = self._emit(LOG_LEVEL_ERROR, msg, *args)
        self.publish_to_sns("Error", s)

    def warning(self, msg, *args):
        """
        Logs warning message
        :param msg: Warning message format string
        :param args: parameters
        :return:
        """
        s = self._emit(LOG_LEVEL_WARNING, msg, *args)
        self.publish_to_sns("Warning", s)

    def debug(self, msg, *args):
        """
        Conditionally logs debug message, does not log if debugging is disabled
        :param msg: Debug message format string
        :param args: parameters
        :return: 
        """
        if self._debug:
            self._emit(LOG_LEVEL_DEBUG, msg, *args)

    def clear(self):
        """
        Clear all buffered error messages
        :return:
        """
        self._buffer = []

    @property
    def client(self):
        if self._client is None:
            methods = ["create_log_stream"]
            self._client = boto_retry.get_client_with_retries("logs", methods, context=self._context)
        return self._client

    def flush(self):
        """
        Writes all buffered messages to CloudWatch Stream
        :return:
        """

        if len(self._buffer) == 0:
            return

        put_event_args = {
            "logGroupName": self._loggroup,
            "logStreamName": self._logstream,
            "logEvents": [{"timestamp": r[0], "message": r[1]} for r in self._buffer]
        }

        retries = 5
        while retries > 0:
            try:
                self.client.put_log_events(**put_event_args)
                self._buffer = []
                self._cached_size = 0
                return
            except self.client.exceptions.ResourceNotFoundException:
                retries -= 1
                self.client.create_log_stream_with_retries(logGroupName=self._loggroup, logStreamName=self._logstream)
            except self.client.exceptions.InvalidSequenceTokenException as ex:
                retries -= 1
                put_event_args["sequenceToken"] = ex.response.get("expectedSequenceToken")
            except Exception:
                return
