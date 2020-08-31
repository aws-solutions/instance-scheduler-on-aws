from botocore.exceptions import ClientError, ParamValidationError

from boto_retry.aws_service_retry import AwsApiServiceRetry


class Ec2ServiceRetry(AwsApiServiceRetry):
    """
        Class that extends retry logic with Ec2 specific logic
    """

    def __init__(self, context=None, timeout=None, wait_strategy=None, lambda_time_out_margin=10):
        """
              Initializes retry logic
              :param wait_strategy: Wait strategy that returns retry wait periods
              :param context: Lambda context that is used to calculate remaining execution time
              :param timeout: Timeout for method call. This time can not exceed the remaining time if a method is called
              within the context of a lambda function.
              :param lambda_time_out_margin: If called within the context of a Lambda function this time should at least be
              remaining before making a retry. This is to allow possible cleanup and logging actions in the remaining time
              """
        AwsApiServiceRetry.__init__(
            self,
            call_retry_strategies=None,
            wait_strategy=wait_strategy,
            context=context,
            timeout=timeout,
            lambda_time_out_margin=lambda_time_out_margin)

        self._call_retry_strategies += [self.snapshot_creation_per_volume_throttled,
                                        self.resource_limit_exceeded,
                                        self.request_limit_exceeded]

    @classmethod
    def snapshot_creation_per_volume_throttled(cls, ex):
        """
        Retries in case the snapshot creation rate is exceeded for a volume
        :param ex: Exception to test
        :return:
        """
        return type(ex) == ClientError and \
               ex.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0) == 400 and \
               "SnapshotCreationPerVolumeRateExceeded" == ex.response.get("Error", {}).get("Code", "")

    @classmethod
    def resource_limit_exceeded(cls, ex):
        """
        Retries in case resource limits are exceeded.
        :param ex:
        :return:
        """
        return type(ex) == ClientError and \
               ex.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0) == 400 and \
               "ResourceLimitExceeded" == ex.response.get("Error", {}).get("Code", "")

    @classmethod
    def request_limit_exceeded(cls, ex):
        """
        Retries in case resource limits are exceeded.
        :param ex:
        :return:
        """
        return type(ex) == ClientError and \
               ex.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0) == 503 and \
               "RequestLimitExceeded" == ex.response.get("Error", {}).get("Code", "")

    def can_retry(self, ex):
        """
           Tests if a retry can be done based on the exception of an earlier call
           :param ex: Execution raise by earlier call of the boto3 method
           :return: True if any of the call_retry_strategy returns True, else False
           """
        if type(ex) == ParamValidationError:
            return False
        return AwsApiServiceRetry.can_retry(self, ex)
