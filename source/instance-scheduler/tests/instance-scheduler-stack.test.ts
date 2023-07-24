// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { Template } from "aws-cdk-lib/assertions";
import { createHubStack } from "./instance-scheduler-stack-factory";

test("InstanceSchedulerStack snapshot test", () => {
  const hubStackJson = Template.fromStack(createHubStack()).toJSON();
  hubStackJson.Resources.Main.Properties.Code = "Omitted to remove snapshot dependency on code hash";
  expect(hubStackJson).toMatchSnapshot();
});

test("Hub stack has expected defaults for started and stopped tags", () => {
  const hubStackTemplate = Template.fromStack(createHubStack());
  expect(hubStackTemplate.findParameters("StartedTags")["StartedTags"]["Default"]).toBe(
    "InstanceScheduler-LastAction=Started By {scheduler} {year}/{month}/{day} {hour}:{minute}{timezone}, ",
  );
  expect(hubStackTemplate.findParameters("StoppedTags")["StoppedTags"]["Default"]).toBe(
    "InstanceScheduler-LastAction=Stopped By {scheduler} {year}/{month}/{day} {hour}:{minute}{timezone}, ",
  );
});
