// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import * as instanceSchedulerHubStack from "../lib/instance-scheduler-stack";
import * as instanceSchedulerSpokeStack from "../lib/remote-stack";
import * as cdk from "aws-cdk-lib";
import { DefaultStackSynthesizer } from "aws-cdk-lib";

export function createHubStack(): cdk.Stack {
  const app = new cdk.App();
  const envEU = { account: "111111111111", region: "eu-west-1" };
  const stack = new instanceSchedulerHubStack.InstanceSchedulerStack(app, "stack", {
    env: envEU,
    description: "",
    solutionId: "SO0030",
    solutionName: "instance-scheduler-on-aws",
    solutionVersion: "v1.5.0",
    appregApplicationName: "AWS-Solutions",
    appregSolutionName: "instance-scheduler-on-aws",
    synthesizer: new DefaultStackSynthesizer({ generateBootstrapVersionRule: false }),
  });
  return stack;
}

export function createSpokeStack(): cdk.Stack {
  const envEU = { account: "111111111111", region: "eu-west-1" };
  const app = new cdk.App();
  const stack = new instanceSchedulerSpokeStack.InstanceSchedulerRemoteStack(app, "stack", {
    env: envEU,
    description: "",
    solutionId: "SO0030",
    solutionName: "instance-scheduler-on-aws",
    solutionVersion: "v1.5.0",
    appregApplicationName: "AWS-Solutions",
    appregSolutionName: "instance-scheduler-on-aws",
    synthesizer: new DefaultStackSynthesizer({ generateBootstrapVersionRule: false }),
  });
  return stack;
}
