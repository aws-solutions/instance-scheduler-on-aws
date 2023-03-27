// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import { createSpokeStack } from "./instance-scheduler-stack-factory";
import { Template } from "aws-cdk-lib/assertions";

/*
 * SnapShot Testing for the AwsInstanceSchedulerStack.
 */
test("AwsInstanceSchedulerStack snapshot test", () => {
  expect(Template.fromStack(createSpokeStack())).toMatchSnapshot();
});
