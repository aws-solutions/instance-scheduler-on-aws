######################################################################################################################
#  Copyright 2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.                                           #
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
from datetime import datetime
from time import sleep, time

from botocore.exceptions import ClientError

import boto_retry


class AwsApiServiceRetry:
    """
    Generic AWS retry logic for calling AWS API using the boto3 api
    """

    def __init__(self, call_retry_strategies=None, wait_strategy=None, context=None, timeout=None, lambda_time_out_margin=10):
        """
        Initializes retry logic instance
        :param call_retry_strategies: List of methods that examine an event raised by a boto3 method call to determine if the
        call may succeed at a later time
        :param wait_strategy: Wait strategy that returns retry wait periods
        :param context: Lambda context that is used to calculate remaining execution time
        :param timeout: Timeout for method call. This time can not exceed the remaining time if a method is called
        within the context of a lambda function.
        :param lambda_time_out_margin: If called within the context of a Lambda function this time should at least be
        remaining before making a retry. This is to allow possible cleanup and logging actions in the remaining time
        """
        self.default_strategies = [self.api_throttled, self.service_not_available]
        self._call_retry_strategies = call_retry_strategies if call_retry_strategies else self.default_strategies
        self._wait_strategy = wait_strategy if wait_strategy else boto_retry.ConstantWaitStrategy()
        self._timeout = timeout
        self._context = context
        self._lambda_time_out_margin = lambda_time_out_margin

    @classmethod
    def api_throttled(cls, ex):
        """
        Tests if the API call was throttled
        :param ex:
        :return:
        """
        return \
            type(ex) == ClientError and \
            ex.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0) == 400 and \
            "throttl" in ex.response.get("Error", {}).get("Code", "").lower()

    @classmethod
    def service_not_available(cls, ex):
        """
        Tests if the service was temporary not available
        :param ex:
        :return:
        """
        if type(ex) == ClientError:
            return False

        response = getattr(ex, "response", {})
        metadata = response.get("ResponseMetaData", {})
        return metadata.get("HTTPStatusCode", 0) == 503

    def can_retry(self, ex):
        """
        Tests if a retry can be done based on the exception of an earlier call
        :param ex: Execution raise by earlier call of the boto3 method
        :return: True if any of the call_retry_strategy returns True, else False
        """
        return any([rt(ex) for rt in self._call_retry_strategies])

    def call(self, boto_client_or_resource, method_name, call_arguments):
        """
        Calls the original boto3 methods that is wrapped in the retry logic
        :param boto_client_or_resource: Boto3 client or resource instance
        :param method_name: Name of the wrapped method with retries
        :param call_arguments: Boto3 method parameters
        :return: result of the wrapped boto3 method
        """

        def timed_out_by_specified_timeout(start_time, time_now, next_wait):
            if self._timeout is None:
                return False

            return (time_now - start_time) > (self._timeout - next_wait)

        def timed_out_by_lambda_timeout(next_wait):
            if self._context is None:
                return False

            context_seconds_left = self._context.get_remaining_time_in_millis() * 1000
            return context_seconds_left < self._lambda_time_out_margin + next_wait

        start = time()
        # gets the method with the retry logic
        method = getattr(boto_client_or_resource, method_name)

        # reset wait time strategy
        self._wait_strategy.reset()

        retries = 0
        for wait_until_next_retry in self._wait_strategy:
            try:
                # make the "wrapped" call
                if boto_retry.boto_retry_debug:
                    t = time()
                    dt = datetime.fromtimestamp(t)
                    print(boto_retry.LOG_FORMAT.format(dt.year, dt.month, dt.day, dt.hour, dt.minute,
                                                       dt.second, str(dt.microsecond)[0:3], method_name, retries))
                retries += 1
                resp = method(**call_arguments)
                # no exceptions, just return result
                return resp
            except Exception as ex:
                # there was an exception
                now = time()
                # test if there should be a retry based on the type of the exception
                if self.can_retry(ex):
                    # test if there is enough time left for the next retry, if not raise the exception
                    if timed_out_by_specified_timeout(start, now, wait_until_next_retry) or \
                            timed_out_by_lambda_timeout(wait_until_next_retry):
                        raise Exception("Call {} timed out, last exception was {}".format(method_name, ex))
                    else:
                        # else wait until next retry
                        sleep(wait_until_next_retry)
                        continue
                else:
                    # No recovery for this type of exception
                    raise ex
