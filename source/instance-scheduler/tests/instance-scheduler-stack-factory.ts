// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { App, Aspects, Stack } from "aws-cdk-lib";
import { AwsSolutionsChecks } from "cdk-nag";
import { InstanceSchedulerStack } from "../lib/instance-scheduler-stack";
import { TestFunctionFactory } from "../lib/lambda-functions/function-factory";
import { SpokeStack } from "../lib/remote-stack";

export function createHubStack(): Stack {
  const app = new App();
  Aspects.of(app).add(new AwsSolutionsChecks({ verbose: true }));
  return new InstanceSchedulerStack(app, "stack", {
    solutionId: "my-solution-id",
    solutionName: "my-solution-name",
    solutionVersion: "v9.9.9",
    factory: new TestFunctionFactory(),
  });
}

export function createSpokeStack(): Stack {
  const app = new App();
  Aspects.of(app).add(new AwsSolutionsChecks({ verbose: true }));
  return new SpokeStack(app, "stack", {
    solutionId: "my-solution-id",
    solutionName: "my-solution-name",
    solutionVersion: "v9.9.9",
    factory: new TestFunctionFactory(),
  });
}
