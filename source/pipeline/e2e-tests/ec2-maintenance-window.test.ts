// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import * as ssm from "@aws-sdk/client-ssm";
import { CreateMaintenanceWindowCommand, DeleteMaintenanceWindowCommand } from "@aws-sdk/client-ssm";
import { createSchedule, currentTimePlus } from "./utils/schedule-test-utils";
import * as ec2 from "@aws-sdk/client-ec2";
import { resourceParams } from "./ec2-maintenance-window.test.resources";
import { delayMinutes } from "./index";
import { getInstanceState } from "./utils/ec2-test-utils";

const ssmClient = new ssm.SSMClient({});
const ec2Client = new ec2.EC2Client({});
const instanceId = resourceParams.ec2InstanceId;

function getCronStrForTime(time: Date) {
  return `cron(0 ${time.getUTCMinutes()} ${time.getUTCHours()} ? * *)`;
}
test("maintenance window start behavior", async () => {
  //stop instance
  await ec2Client.send(
    new ec2.StopInstancesCommand({
      InstanceIds: [instanceId],
    }),
  );

  //confirm stopped
  await delayMinutes(1);
  expect(await getInstanceState(ec2Client, instanceId)).toBe(ec2.InstanceStateName.stopped);

  //create maintenance window
  let window_id: string | undefined;
  await ssmClient
    .send(
      new CreateMaintenanceWindowCommand({
        Name: "test-window",
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
      window_id = response.WindowId;
    });

  try {
    //create schedule
    await createSchedule({
      name: resourceParams.maintWindowTestScheduleName,
      description: `testing schedule`,
      use_maintenance_window: true,
      ssm_maintenance_window: "test-window",
    });

    //confirm instance started in anticipation of upcoming maintenance window
    await delayMinutes(5);
    expect(await getInstanceState(ec2Client, instanceId)).toBe(ec2.InstanceStateName.running);
  } finally {
    await ssmClient.send(
      new DeleteMaintenanceWindowCommand({
        WindowId: window_id,
      }),
    );
  }
}, 900_000);
