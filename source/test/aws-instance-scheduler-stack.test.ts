#!/usr/bin/env node
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

import { SynthUtils } from '@aws-cdk/assert';
import * as cdk from '@aws-cdk/core';
import instanceSchedulerStack = require('../lib/aws-instance-scheduler-stack');
import '@aws-cdk/assert/jest';


function getTestStack(): cdk.Stack {
  const app = new cdk.App();
  const envEU = { account: '111111111111', region: 'eu-west-1' };
  const stack = new instanceSchedulerStack.AwsInstanceSchedulerStack(app, 'stack', {
    env: envEU, 
    solutionId: "SO0030",
    solutionTradeMarkName: 'aws-instance-scheduler',
    solutionProvider: 'AWS Solution Development',
    solutionBucket: "solutions",
    solutionName: 'aws-instance-scheduler',
    solutionVersion: 'v1.3.3'
  })

  const instanceSchedulerStackMetadata =
  {
    "AWS::CloudFormation::Interface": {
      "ParameterGroups": [
        {
          "Label": {
            "default": "Scheduler (version v1.3.3)"
          },
          "Parameters": [
            "TagName",
            "ScheduledServices",
            "ScheduleRdsClusters",
            "CreateRdsSnapshot",
            "SchedulingActive",
            "Regions",
            "DefaultTimezone",
            "CrossAccountRoles",
            "ScheduleLambdaAccount",
            "SchedulerFrequency",
            "MemorySize"
          ]
        },
        {
          "Label": {
            "default": "Options"
          },
          "Parameters": [
            "UseCloudWatchMetrics",
            "SendAnonymousData",
            "Trace"
          ]
        },
        {
          "Label": {
            "default": "Other parameters"
          },
          "Parameters": [
            "LogRetentionDays",
            "StartedTags",
            "StoppedTags"
          ]
        }
      ],
      "ParameterLabels": {
        "LogRetentionDays": {
          "default": "Log retention days"
        },
        "StartedTags": {
          "default": "Started tags"
        },
        "StoppedTags": {
          "default": "Stopped tags"
        },
        "SchedulingActive": {
          "default": "Scheduling enabled"
        },
        "CrossAccountRoles": {
          "default": "Cross-account roles"
        },
        "ScheduleLambdaAccount": {
          "default": "This account"
        },
        "UseCloudWatchMetrics": {
          "default": "Enable CloudWatch Metrics"
        },
        "Trace": {
          "default": "Enable CloudWatch Logs"
        },
        "TagName": {
          "default": "Instance Scheduler tag name"
        },
        "ScheduledServices": {
          "default": "Service(s) to schedule"
        },
        "ScheduleRdsClusters": {
          "default": "Schedule Aurora Clusters"
        },
        "CreateRdsSnapshot": {
          "default": "Create RDS instance snapshot"
        },
        "DefaultTimezone": {
          "default": "Default time zone"
        },
        "SchedulerFrequency": {
          "default": "Frequency"
        },
        "Regions": {
          "default": "Region(s)"
        },
        "MemorySize": {
          "default": "Memory size"
        },
        "SendAnonymousData": {
          "default": "Send anonymous usage data"
        }
      }
    }
  }
  stack.templateOptions.metadata = instanceSchedulerStackMetadata
  stack.templateOptions.templateFormatVersion = "2010-09-09"
  return stack;
}
/*
 * SnapShot Testing for the AwsInstanceSchedulerStack.
 */
test('AwsInstanceSchedulerStack snapshot test', () => {
  expect(SynthUtils.toCloudFormation(getTestStack())).toMatchSnapshot();
});