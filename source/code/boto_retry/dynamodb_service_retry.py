from boto_retry.aws_service_retry import AwsApiServiceRetry


class DynamoDbServiceRetry(AwsApiServiceRetry):
    """
    Class that extends retry logic with DynamoDB specific logic
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

        self._call_retry_strategies += [self.dynamo_throughput_exceeded, self.dynamo_resource_in_use]

    @classmethod
    def dynamo_throughput_exceeded(cls, ex):
        """
        Adds retry logic on top of the retry logic already done by boto3 if max throughput is exceeded for a table or index
        :param ex: Exception to test
        :return:
        """
        return type(ex).__name__ == "ProvisionedThroughputExceededException"

    @classmethod
    def dynamo_resource_in_use(cls, ex):
        return type(ex).__name__ == "ResourceInUseException"
