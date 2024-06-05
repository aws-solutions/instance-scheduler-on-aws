// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import {
  AutoScalingClient,
  BatchDeleteScheduledActionCommand,
  CreateOrUpdateTagsCommand,
  DeleteTagsCommand,
  DescribeScheduledActionsCommand,
  ScheduledUpdateGroupAction,
  UpdateAutoScalingGroupCommand,
} from "@aws-sdk/client-auto-scaling";
import { InvokeCommand, LambdaClient } from "@aws-sdk/client-lambda";
import { delayMinutes } from ".";
import { resourceParams } from "./asg-configure.test.resources";
import { createSchedule } from "./utils/schedule-test-utils";

const asgClient = new AutoScalingClient();
const lambdaClient = new LambdaClient();
const groupName = resourceParams.configureGroupName;

test("group name exists", () => {
  expect(groupName).not.toBeUndefined();
});

test("configure AutoScaling Group", async () => {
  if (resourceParams.configureGroupName === undefined) {
    throw new Error("Unknown group name");
  }

  await deleteAllScheduledScalingActions(resourceParams.configureGroupName);

  await asgClient.send(
    new UpdateAutoScalingGroupCommand({
      AutoScalingGroupName: groupName,
      MinSize: 1,
      DesiredCapacity: 1,
      MaxSize: 1,
    }),
  );

  await createSchedule({
    name: resourceParams.scheduleName,
    description: "testing schedule",
    periods: [
      {
        name: "asg-period",
        description: "testing period",
        begintime: "09:00",
        endtime: "17:00",
      },
    ],
  });

  await asgClient.send(
    new CreateOrUpdateTagsCommand({
      Tags: [
        {
          Key: "Schedule",
          Value: resourceParams.scheduleName,
          ResourceType: "auto-scaling-group",
          ResourceId: resourceParams.configureGroupName,
          PropagateAtLaunch: true,
        },
      ],
    }),
  );

  const asgOrch = process.env["AsgOrchName"];
  await lambdaClient.send(
    new InvokeCommand({
      FunctionName: asgOrch,
      InvocationType: "Event",
      Payload: JSON.stringify({}),
    }),
  );

  await delayMinutes(1);

  const actions = await asgClient.send(
    new DescribeScheduledActionsCommand({
      AutoScalingGroupName: groupName,
    }),
  );

  expect(actions.ScheduledUpdateGroupActions).not.toBeUndefined();

  if (actions.ScheduledUpdateGroupActions === undefined) {
    throw new Error("No actions");
  }

  expect(actions.ScheduledUpdateGroupActions).toHaveLength(2);
  const expectedStartAction: ScheduledUpdateGroupAction = {
    AutoScalingGroupName: resourceParams.configureGroupName,
    ScheduledActionName: expect.any(String),
    ScheduledActionARN: expect.any(String),
    StartTime: expect.any(Date),
    Time: expect.any(Date),
    Recurrence: "0 9 * * *",
    MinSize: 1,
    DesiredCapacity: 1,
    MaxSize: 1,
    TimeZone: "UTC",
  };
  const expectedStopAction: ScheduledUpdateGroupAction = {
    AutoScalingGroupName: resourceParams.configureGroupName,
    ScheduledActionName: expect.any(String),
    ScheduledActionARN: expect.any(String),
    StartTime: expect.any(Date),
    Time: expect.any(Date),
    Recurrence: "0 17 * * *",
    MinSize: 0,
    DesiredCapacity: 0,
    MaxSize: 0,
    TimeZone: "UTC",
  };
  expect(actions.ScheduledUpdateGroupActions).toContainEqual(expectedStartAction);
  expect(actions.ScheduledUpdateGroupActions).toContainEqual(expectedStopAction);
}, 180_000);

async function deleteAllScheduledScalingActions(groupName: string) {
  const actions = await asgClient.send(
    new DescribeScheduledActionsCommand({
      AutoScalingGroupName: groupName,
    }),
  );
  if (actions.ScheduledUpdateGroupActions !== undefined && actions.ScheduledUpdateGroupActions.length > 0) {
    await asgClient.send(
      new BatchDeleteScheduledActionCommand({
        AutoScalingGroupName: groupName,
        ScheduledActionNames: actions.ScheduledUpdateGroupActions.map((action) => action.ScheduledActionName).filter(
          (name): name is string => name !== undefined,
        ),
      }),
    );
  }
}

afterAll(async () => {
  if (resourceParams.configureGroupName === undefined) {
    throw new Error("Unknown group name");
  }

  await asgClient.send(
    new DeleteTagsCommand({
      Tags: [
        { Key: "Schedule", ResourceType: "auto-scaling-group", ResourceId: resourceParams.configureGroupName },
        { Key: "scheduled", ResourceType: "auto-scaling-group", ResourceId: resourceParams.configureGroupName },
      ],
    }),
  );
  await deleteAllScheduledScalingActions(resourceParams.configureGroupName);
});
