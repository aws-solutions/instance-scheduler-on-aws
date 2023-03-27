#!/usr/bin/env node
// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import * as cdk from "aws-cdk-lib";
import { Aspects } from "aws-cdk-lib";
import { AwsSolutionsChecks } from "cdk-nag";
import { E2eTestStack } from "../lib/e2e-test-stack";
import PipelineStack from "../lib/pipeline-stack";

const app = new cdk.App();

new PipelineStack(app, "aws-instance-scheduler-testing-pipeline");

/*
E2eTestStack does not actually need to be built here to work in the pipeline,
but building it here ensures it gets covered by CDK-Nag
 */
new E2eTestStack(app, "aws-instance-scheduler-end-to-end-testing-resources");

Aspects.of(app).add(
  new AwsSolutionsChecks({
    verbose: true,
  })
);
