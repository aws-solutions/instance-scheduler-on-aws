/*****************************************************************************
 *  Copyright 2020 Amazon.com, Inc. or its affiliates. All Rights Reserved.   *
 *                                                                            *
 *  Licensed under the Apache License, Version 2.0 (the "License"). You may   *
 *  not use this file except in compliance with the License. A copy of the    *
 *  License is located at                                                     *
 *                                                                            *
 *      http://www.apache.org/licenses/LICENSE-2.0                            *
 *                                                                            *
 *  or in the 'license' file accompanying this file. This file is distributed *
 *  on an 'AS IS' BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND,        *
 *  express or implied. See the License for the specific language governing   *
 *  permissions and limitations under the License.                            *
 *****************************************************************************/
import {AwsInstanceSchedulerStack} from "../../../instance-scheduler/lib/aws-instance-scheduler-stack";
import {CfnOutput} from "aws-cdk-lib";

const envKeys = {
  CONFIG_TABLE: "ConfigTable",
  ISSUE_SNS_TOPIC_ARN: "IssueSNSTopic",
  SCHEDULER_ROLE_ARN: "IssueSNSTopic"
}

export const hubStackParams = {
  configTableArn: process.env[envKeys.CONFIG_TABLE]!,
  issueSnsTopicArn: process.env[envKeys.ISSUE_SNS_TOPIC_ARN]!,
  schedulerRoleArn: process.env[envKeys.SCHEDULER_ROLE_ARN]!,
}

export function extractOutputsFrom(hubStack: AwsInstanceSchedulerStack): Record<string, CfnOutput> {
  return {
    [envKeys.CONFIG_TABLE]: hubStack.configurationTableOutput,
    [envKeys.ISSUE_SNS_TOPIC_ARN]: hubStack.issueSnsTopicArn,
    [envKeys.SCHEDULER_ROLE_ARN]: hubStack.schedulerRoleArn
  }
}
