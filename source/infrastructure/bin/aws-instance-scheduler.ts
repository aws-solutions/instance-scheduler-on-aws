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

import * as cdk from 'aws-cdk-lib';
import { AwsInstanceSchedulerStack } from '../lib/aws-instance-scheduler-stack';
import { AwsInstanceSchedulerRemoteStack } from '../lib/aws-instance-scheduler-remote-stack';
import PipelineStack from "../pipeline/pipeline-stack";
import {Aspects, DefaultStackSynthesizer} from "aws-cdk-lib";
import {AwsSolutionsChecks, NagSuppressions} from "cdk-nag";
import {getSolutionContext} from "./cdk-context";

const SOLUTION_TMN = process.env['SOLUTION_TRADEMARKEDNAME'] ? process.env['SOLUTION_TRADEMARKEDNAME'] : "aws-instance-scheduler";
const SOLUTION_PROVIDER = 'AWS Solution Development';



let synthesizer = new DefaultStackSynthesizer({
    generateBootstrapVersionRule: false,
});

// Solutions pipeline deployment
const { DIST_OUTPUT_BUCKET, SOLUTION_NAME, VERSION } = process.env;
if (DIST_OUTPUT_BUCKET && SOLUTION_NAME && VERSION)
    synthesizer = new DefaultStackSynthesizer({
        generateBootstrapVersionRule: false,
        fileAssetsBucketName: `${DIST_OUTPUT_BUCKET}-\${AWS::Region}`,
        bucketPrefix: `${SOLUTION_NAME}/${VERSION}/`,
    });

const app = new cdk.App();
const solutionDetails = getSolutionContext(app);

const hubStack = new AwsInstanceSchedulerStack(app, 'aws-instance-scheduler', {
    synthesizer: synthesizer,
    description: `(${solutionDetails.solutionId}) - The AWS CloudFormation template for deployment of the ${solutionDetails.solutionName}, version: ${solutionDetails.solutionVersion}`,
    solutionId: solutionDetails.solutionId,
    solutionTradeMarkName: SOLUTION_TMN,
    solutionProvider: SOLUTION_PROVIDER,
    solutionName: solutionDetails.solutionName,
    solutionVersion: solutionDetails.solutionVersion,
    appregApplicationName: solutionDetails.appRegAppName,
    appregSolutionName: solutionDetails.appRegSolutionName
});

new AwsInstanceSchedulerRemoteStack(app, 'aws-instance-scheduler-remote', {
    synthesizer: synthesizer,
    description:  `(${solutionDetails.solutionId}) - The AWS CloudFormation template for ${solutionDetails.solutionName} cross account role, version: ${solutionDetails.solutionVersion}`,
    solutionId: solutionDetails.solutionId,
    solutionTradeMarkName: SOLUTION_TMN,
    solutionProvider: SOLUTION_PROVIDER,
    solutionName: solutionDetails.solutionName,
    solutionVersion: solutionDetails.solutionVersion,
    appregApplicationName: solutionDetails.appRegAppName,
    appregSolutionName: solutionDetails.appRegSolutionName
});

new PipelineStack(app, 'aws-instance-scheduler-testing-pipeline');


NagSuppressions.addResourceSuppressionsByPath(hubStack, "/aws-instance-scheduler/SchedulerRole/DefaultPolicy/Resource", [
    {
        id: "AwsSolutions-IAM5",
        reason: "The scheduling lambda must access multiple resources across services"
    }
])

Aspects.of(app).add(new AwsSolutionsChecks({
    verbose: true
}))
