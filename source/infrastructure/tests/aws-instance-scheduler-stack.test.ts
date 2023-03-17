// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import { Template } from "aws-cdk-lib/assertions";
import { createHubStack } from "./instance-scheduler-stack-factory";

/*
 * SnapShot Testing for the AwsInstanceSchedulerStack.
 */
test("AwsInstanceSchedulerStack snapshot test", () => {
  expect(Template.fromStack(createHubStack())).toMatchSnapshot();
});
