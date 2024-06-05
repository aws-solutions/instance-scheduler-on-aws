// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import * as rds from "@aws-sdk/client-rds";

import { resourceParams } from "./basic-rds-start-stop.test.resources";
import { delayMinutes } from "./index";
import { getInstanceState } from "./utils/rds-test-utils";
import {
  createSchedule,
  currentTimePlus,
  toTimeStr,
  minutesToMillis,
  waitForExpect,
} from "./utils/schedule-test-utils";

const rdsClient = new rds.RDSClient({});

test("rdsInstanceAccessible", async () => {
  const fetchResult = await rdsClient.send(
    new rds.DescribeDBInstancesCommand({
      DBInstanceIdentifier: resourceParams.rdsInstanceId,
    }),
  );

  expect(fetchResult.DBInstances?.[0]).not.toBeUndefined();
});

test("basic rds start-stop schedule", async () => {
  const preTestState = await getInstanceState(rdsClient, resourceParams.rdsInstanceId);
  if (!["stopped", "stopping"].includes(preTestState)) {
    console.log(`instance in state ${preTestState} before test. Attempting to stop before running test...`);
    await rdsClient.send(
      new rds.StopDBInstanceCommand({
        DBInstanceIdentifier: resourceParams.rdsInstanceId,
      }),
    );
  }

  let currentDelayMinutes = 1;
  const maxDelayMinutes = 5;
  while (
    (await rdsClient.send(new rds.DescribeDBInstancesCommand({ DBInstanceIdentifier: resourceParams.rdsInstanceId })))
      .DBInstances?.[0].DBInstanceStatus != "stopped"
  ) {
    await delayMinutes(currentDelayMinutes);
    currentDelayMinutes = Math.min(currentDelayMinutes * 2, maxDelayMinutes);
  }

  //create test schedule
  await createSchedule({
    name: resourceParams.taggedScheduleName,
    description: `testing schedule`,
    periods: [
      {
        name: "rds-start-stop-period",
        description: `testing period`,
        begintime: toTimeStr(currentTimePlus(2)),
        endtime: toTimeStr(currentTimePlus(5)),
      },
    ],
  });

  //confirm running during running period
  await delayMinutes(2); //wait for begintime
  await waitForExpect(
    async () => {
      expect(await getInstanceState(rdsClient, resourceParams.rdsInstanceId)).toBeOneOf(["available", "starting"]);
    },
    minutesToMillis(5),
    minutesToMillis(0.5),
  );

  //confirm stopped after stop time
  await delayMinutes(3); //wait for endtime

  await waitForExpect(
    async () => {
      expect(await getInstanceState(rdsClient, resourceParams.rdsInstanceId)).toBeOneOf(["stopped", "stopping"]);
    },
    minutesToMillis(5),
    minutesToMillis(0.5),
  );
}, 2_400_000);
