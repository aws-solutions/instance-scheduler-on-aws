// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import * as ec2 from "@aws-sdk/client-ec2";

import { resourceParams } from "./encrypted-ec2-start.test.resources";
import { delayMinutes } from "./index";
import { clearScheduleTag, getInstanceState, setScheduleTag } from "./utils/ec2-test-utils";
import { createSchedule } from "./utils/schedule-test-utils";

const ec2Client = new ec2.EC2Client({});
const instanceId = resourceParams.ec2InstanceId;

test("instanceId exists", () => {
  expect(instanceId).not.toBeUndefined();
});
test("encrypted EC2 start", async () => {
  //stop instance
  await ec2Client.send(
    new ec2.StopInstancesCommand({
      InstanceIds: [instanceId],
    }),
  );

  //confirm stopped
  await ec2.waitUntilInstanceStopped({ client: ec2Client, maxWaitTime: 300 }, { InstanceIds: [instanceId] });
  expect(await getInstanceState(ec2Client, instanceId)).toBe(ec2.InstanceStateName.stopped);

  //create schedule
  await createSchedule({
    name: resourceParams.encryptedEc2ScheduleName,
    description: `always-running test schedule`,
    enforced: true,
    override_status: "running",
  });
  await setScheduleTag(ec2Client, instanceId, resourceParams.encryptedEc2ScheduleName);

  //confirm running during running period
  await delayMinutes(2);
  expect(await getInstanceState(ec2Client, instanceId)).toBeOneOf([
    ec2.InstanceStateName.pending,
    ec2.InstanceStateName.running,
  ]);
}, 900_000);

afterAll(async () => {
  await clearScheduleTag(ec2Client, instanceId);
});
