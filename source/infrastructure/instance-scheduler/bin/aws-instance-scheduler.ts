#!/usr/bin/env node
// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import * as cdk from "aws-cdk-lib";
import { AwsInstanceSchedulerStack } from "../lib/aws-instance-scheduler-stack";
import { AwsInstanceSchedulerRemoteStack } from "../lib/aws-instance-scheduler-remote-stack";
import { Aspects, DefaultStackSynthesizer } from "aws-cdk-lib";
import { AwsSolutionsChecks, NagSuppressions } from "cdk-nag";
import { getSolutionContext } from "./cdk-context";

let synthesizer = new DefaultStackSynthesizer({
  generateBootstrapVersionRule: false,
});

// Solutions pipeline deployment
const { DIST_OUTPUT_BUCKET, SOLUTION_NAME, DIST_VERSION } = process.env;
if (DIST_OUTPUT_BUCKET && SOLUTION_NAME && DIST_VERSION) {
  synthesizer = new DefaultStackSynthesizer({
    generateBootstrapVersionRule: false,
    fileAssetsBucketName: `${DIST_OUTPUT_BUCKET}-\${AWS::Region}`,
    bucketPrefix: `${SOLUTION_NAME}/${DIST_VERSION}/`,
  });
}

const app = new cdk.App();
const solutionDetails = getSolutionContext(app);

const hubStack = new AwsInstanceSchedulerStack(app, "aws-instance-scheduler", {
  synthesizer: synthesizer,
  description: `(${solutionDetails.solutionId}) - The AWS CloudFormation template for deployment of the ${solutionDetails.solutionName}, version: ${solutionDetails.solutionVersion}`,
  solutionId: solutionDetails.solutionId,
  solutionName: solutionDetails.solutionName,
  solutionVersion: solutionDetails.solutionVersion,
  appregApplicationName: solutionDetails.appRegAppName,
  appregSolutionName: solutionDetails.appRegSolutionName,
});

new AwsInstanceSchedulerRemoteStack(app, "aws-instance-scheduler-remote", {
  synthesizer: synthesizer,
  description: `(${solutionDetails.solutionId}S) - The AWS CloudFormation template for ${solutionDetails.solutionName} cross account role, version: ${solutionDetails.solutionVersion}`,
  solutionId: solutionDetails.solutionId,
  solutionName: solutionDetails.solutionName,
  solutionVersion: solutionDetails.solutionVersion,
  appregApplicationName: solutionDetails.appRegAppName,
  appregSolutionName: solutionDetails.appRegSolutionName,
});

NagSuppressions.addResourceSuppressionsByPath(
  hubStack,
  "/aws-instance-scheduler/SchedulerRole/DefaultPolicy/Resource",
  [
    {
      id: "AwsSolutions-IAM5",
      reason: "The scheduling lambda must access multiple resources across services",
    },
  ]
);

Aspects.of(app).add(
  new AwsSolutionsChecks({
    verbose: true,
  })
);
