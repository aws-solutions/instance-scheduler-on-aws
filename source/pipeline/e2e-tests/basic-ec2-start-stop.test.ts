// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import * as ec2 from "@aws-sdk/client-ec2";

import { resourceParams } from "./basic-ec2-start-stop.test.resources";
import { delayMinutes } from "./index";
import { clearScheduleTag, getInstanceState, setScheduleTag } from "./utils/ec2-test-utils";
import {
  createSchedule,
  currentTimePlus,
  toTimeStr,
  minutesToMillis,
  waitForExpect,
} from "./utils/schedule-test-utils";

const ec2Client = new ec2.EC2Client({});
const instanceId = resourceParams.ec2InstanceId;

test("instanceId exists", () => {
  expect(instanceId).not.toBeUndefined();
});
test(
  "basic ec2 start-stop schedule",
  async () => {
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
      name: resourceParams.startStopTestScheduleName,
      description: `testing schedule`,
      periods: [
        {
          name: "ec2-start-stop-period",
          description: `testing period`,
          begintime: toTimeStr(currentTimePlus(2)),
          endtime: toTimeStr(currentTimePlus(5)),
        },
      ],
    });

    await setScheduleTag(ec2Client, instanceId, resourceParams.startStopTestScheduleName);

    //confirm running during running period
    await delayMinutes(2);
    await waitForExpect(
      async () => {
        expect(await getInstanceState(ec2Client, instanceId)).toBeOneOf([
          ec2.InstanceStateName.pending,
          ec2.InstanceStateName.running,
        ]);
      },
      minutesToMillis(5),
      minutesToMillis(0.5),
    );

    //confirm stopped after stop time
    await delayMinutes(5);
    await waitForExpect(
      async () => {
        expect(await getInstanceState(ec2Client, instanceId)).toBeOneOf([
          ec2.InstanceStateName.stopping,
          ec2.InstanceStateName.stopped,
        ]);
      },
      minutesToMillis(5),
      minutesToMillis(0.5),
    );
  },
  minutesToMillis(15),
);

afterAll(async () => {
  await clearScheduleTag(ec2Client, instanceId);
});
