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

import * as instanceSchedulerHubStack from '../lib/aws-instance-scheduler-stack';
import * as instanceSchedulerSpokeStack from '../lib/aws-instance-scheduler-remote-stack';
import * as cdk from 'aws-cdk-lib';
import {DefaultStackSynthesizer} from "aws-cdk-lib";

export function createHubStack(): cdk.Stack {
  const app = new cdk.App();
  const envEU = { account: '111111111111', region: 'eu-west-1' };
  const stack = new instanceSchedulerHubStack.AwsInstanceSchedulerStack(app, 'stack', {
    env: envEU,
    description: "",
    solutionId: "SO0030",
    solutionName: 'aws-instance-scheduler',
    solutionVersion: 'v1.5.0',
    appregApplicationName: "AWS-Solutions",
    appregSolutionName: "instance-scheduler-on-aws",
    synthesizer: new DefaultStackSynthesizer(({ generateBootstrapVersionRule: false}))
  })

  const instanceSchedulerStackMetadata =
  {
    "AWS::CloudFormation::Interface": {
      "ParameterGroups": [
        {
          "Label": {
            "default": "Scheduler (version v1.4.0)"
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

export function createSpokeStack(): cdk.Stack {
  const envEU = { account: '111111111111', region: 'eu-west-1' };
  const app = new cdk.App();
  const stack = new instanceSchedulerSpokeStack.AwsInstanceSchedulerRemoteStack(app, 'stack', {
    env: envEU,
    description: "",
    solutionId: "SO0030",
    solutionName: 'aws-instance-scheduler',
    solutionVersion: 'v1.5.0',
    appregApplicationName: "AWS-Solutions",
    appregSolutionName: "instance-scheduler-on-aws",
    synthesizer: new DefaultStackSynthesizer(({ generateBootstrapVersionRule: false}))
  })


  const instanceSchedulerRemoteStackMetadata =
  {
    "AWS::CloudFormation::Interface": {
      "ParameterGroups": [{
        "Label": {
          "default": "Account"
        },
        "Parameters": [
          "InstanceSchedulerAccount"
        ]
      }],
      "ParameterLabels": {
        "InstanceSchedulerAccount": {
          "default": "Primary account"
        }
      }
    }
  }
  stack.templateOptions.metadata = instanceSchedulerRemoteStackMetadata
  stack.templateOptions.templateFormatVersion = "2010-09-09"
  return stack;
}
