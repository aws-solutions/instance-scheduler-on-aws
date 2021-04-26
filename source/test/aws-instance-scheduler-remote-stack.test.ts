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
import instanceSchedulerStack = require('../lib/aws-instance-scheduler-remote-stack');
import '@aws-cdk/assert/jest';


function getTestStack(): cdk.Stack {
  const envEU = { account: '111111111111', region: 'eu-west-1' };
  const app = new cdk.App();
  const stack = new instanceSchedulerStack.AwsInstanceSchedulerRemoteStack(app, 'stack', {
    env: envEU,
    description: "", 
    solutionId: "SO0030",
    solutionTradeMarkName: 'aws-instance-scheduler',
    solutionProvider: 'AWS Solution Development',
    solutionBucket: "solutions",
    solutionName: 'aws-instance-scheduler',
    solutionVersion: 'v1.4.0'
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
/*
 * SnapShot Testing for the AwsInstanceSchedulerStack.
 */
test('AwsInstanceSchedulerStack snapshot test', () => {
  expect(SynthUtils.toCloudFormation(getTestStack())).toMatchSnapshot();
});