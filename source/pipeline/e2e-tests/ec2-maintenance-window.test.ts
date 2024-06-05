// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import * as ssm from "@aws-sdk/client-ssm";
import { CreateMaintenanceWindowCommand, DeleteMaintenanceWindowCommand } from "@aws-sdk/client-ssm";
import {
  createSchedule,
  currentTimePlus,
  toTimeStr,
  minutesToMillis,
  waitForExpect,
} from "./utils/schedule-test-utils";
import * as ec2 from "@aws-sdk/client-ec2";
import { resourceParams } from "./ec2-maintenance-window.test.resources";
import { clearScheduleTag, getInstanceState, setScheduleTag } from "./utils/ec2-test-utils";
import { v4 as uuidv4 } from "uuid";

const ssmClient = new ssm.SSMClient({});
const ec2Client = new ec2.EC2Client({});
const instanceId = resourceParams.ec2InstanceId;

function getCronStrForTime(time: Date) {
  return `cron(0 ${time.getUTCMinutes()} ${time.getUTCHours()} ? * *)`;
}
test(
  "maintenance window start behavior",
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

    //create maintenance window
    let windowId: string | undefined;
    const windowName = `test-window-${uuidv4()}`;
    await ssmClient
      .send(
        new CreateMaintenanceWindowCommand({
          Name: windowName,
          Description: "e2e test window",
          Schedule: getCronStrForTime(currentTimePlus(12)),
          ScheduleTimezone: "UTC",
          Duration: 1,
          Cutoff: 0,
          AllowUnassociatedTargets: false,
          Tags: [],
        }),
      )
      .then((response) => {
        windowId = response.WindowId;
      });

    try {
      //create schedule
      await createSchedule({
        name: resourceParams.maintWindowTestScheduleName,
        description: `testing schedule`,
        ssm_maintenance_window: [windowName],
        periods: [
          {
            name: "ec2-mw-unused-period",
            description: "testing period",
            begintime: toTimeStr(currentTimePlus(60)),
            endtime: toTimeStr(currentTimePlus(65)),
          },
        ],
      });
      await setScheduleTag(ec2Client, instanceId, resourceParams.maintWindowTestScheduleName);

      //confirm instance started in anticipation of upcoming maintenance window
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
    } finally {
      await ssmClient.send(
        new DeleteMaintenanceWindowCommand({
          WindowId: windowId,
        }),
      );
    }
  },
  minutesToMillis(15),
);

afterAll(async () => {
  await clearScheduleTag(ec2Client, instanceId);
});
