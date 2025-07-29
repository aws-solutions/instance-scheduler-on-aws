// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { createSpokeStack } from "./instance-scheduler-stack-factory";
import { Template } from "aws-cdk-lib/assertions";

// share Templates for testing to avoid redundant Docker builds
const remoteStack = Template.fromStack(createSpokeStack());

test("InstanceSchedulerRemoteStack snapshot test", () => {
  const resources = remoteStack.findResources("AWS::Lambda::Function");
  const remoteStackJson = remoteStack.toJSON();

  for (const lambda_function in resources) {
    remoteStackJson["Resources"][lambda_function]["Properties"]["Code"] =
      "Omitted to remove snapshot dependency on code hash";
  }
  expect(remoteStackJson).toMatchSnapshot();
});
