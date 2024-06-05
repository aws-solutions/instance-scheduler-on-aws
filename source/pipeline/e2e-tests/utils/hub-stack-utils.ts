// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { CfnOutput } from "aws-cdk-lib";
import { InstanceSchedulerTestingStack } from "../../lib/instance-scheduler-testing-stack";

const envKeys = {
  CONFIG_TABLE: "ConfigTableArn",
  ISSUE_SNS_TOPIC_ARN: "TopicArn",
  SCHEDULER_ROLE_ARN: "SchedulerRoleArn",
};

export const hubStackParams = {
  // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
  configTableArn: process.env[envKeys.CONFIG_TABLE]!,
  // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
  issueSnsTopicArn: process.env[envKeys.ISSUE_SNS_TOPIC_ARN]!,
  // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
  schedulerRoleArn: process.env[envKeys.SCHEDULER_ROLE_ARN]!,
};

export function extractOutputsFrom(hubStack: InstanceSchedulerTestingStack): Record<string, CfnOutput> {
  return {
    [envKeys.CONFIG_TABLE]: hubStack.configTableArn,
    [envKeys.ISSUE_SNS_TOPIC_ARN]: hubStack.topicArn,
    [envKeys.SCHEDULER_ROLE_ARN]: hubStack.schedulerRoleArn,
  };
}
