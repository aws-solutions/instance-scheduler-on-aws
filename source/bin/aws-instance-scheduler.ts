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

import * as cdk from '@aws-cdk/core';
import { AwsInstanceSchedulerStack } from '../lib/aws-instance-scheduler-stack';
import { AwsInstanceSchedulerRemoteStack } from '../lib/aws-instance-scheduler-remote-stack';

const SOLUTION_VERSION = process.env['DIST_VERSION'] || '%%VERSION%%';
const SOLUTION_NAME = process.env['SOLUTION_NAME'];
const SOLUTION_ID = process.env['SOLUTION_ID'];
const SOLUTION_BUCKET = process.env['DIST_OUTPUT_BUCKET'];
const SOLUTION_TMN = process.env['SOLUTION_TRADEMARKEDNAME'];
const SOLUTION_PROVIDER = 'AWS Solution Development';

const app = new cdk.App();


new AwsInstanceSchedulerStack(app, 'instance-scheduler', {
    description: '(' + SOLUTION_ID + ') - ' + SOLUTION_NAME + ', version ' + SOLUTION_VERSION,
    solutionId: SOLUTION_ID,
    solutionTradeMarkName: SOLUTION_TMN,
    solutionProvider: SOLUTION_PROVIDER,
    solutionBucket: SOLUTION_BUCKET,
    solutionName: SOLUTION_NAME,
    solutionVersion: SOLUTION_VERSION
});
new AwsInstanceSchedulerRemoteStack(app, 'instance-scheduler-remote', {
    description:  '(' + SOLUTION_ID + ') - ' + SOLUTION_NAME + ' cross account role, version ' + SOLUTION_VERSION,
    solutionId: SOLUTION_ID,
    solutionTradeMarkName: SOLUTION_TMN,
    solutionProvider: SOLUTION_PROVIDER,
    solutionBucket: SOLUTION_BUCKET,
    solutionName: SOLUTION_NAME,
    solutionVersion: SOLUTION_VERSION
});