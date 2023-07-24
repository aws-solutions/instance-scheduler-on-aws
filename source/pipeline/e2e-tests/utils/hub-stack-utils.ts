// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import { InstanceSchedulerStack } from "../../../instance-scheduler/lib/instance-scheduler-stack";
import { CfnOutput } from "aws-cdk-lib";

const envKeys = {
  CONFIG_TABLE: "ConfigTable",
  ISSUE_SNS_TOPIC_ARN: "IssueSNSTopic",
  SCHEDULER_ROLE_ARN: "IssueSNSTopic",
};

export const hubStackParams = {
  // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
  configTableArn: process.env[envKeys.CONFIG_TABLE]!,
  // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
  issueSnsTopicArn: process.env[envKeys.ISSUE_SNS_TOPIC_ARN]!,
  // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
  schedulerRoleArn: process.env[envKeys.SCHEDULER_ROLE_ARN]!,
};

export function extractOutputsFrom(hubStack: InstanceSchedulerStack): Record<string, CfnOutput> {
  return {
    [envKeys.CONFIG_TABLE]: hubStack.configurationTableOutput,
    [envKeys.ISSUE_SNS_TOPIC_ARN]: hubStack.issueSnsTopicArn,
    [envKeys.SCHEDULER_ROLE_ARN]: hubStack.schedulerRoleArn,
  };
}
