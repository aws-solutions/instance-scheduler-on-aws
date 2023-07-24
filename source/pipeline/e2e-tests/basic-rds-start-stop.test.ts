// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import * as rds from "@aws-sdk/client-rds";

import { resourceParams } from "./basic-rds-start-stop.test.resources";
import { delayMinutes } from "./index";
import { getInstanceState } from "./utils/rds-test-utils";
import { createSchedule, currentTimePlus, toTimeStr } from "./utils/schedule-test-utils";

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
    await delayMinutes(5);
  }

  //create test schedule
  await createSchedule({
    name: resourceParams.taggedScheduleName,
    description: `testing schedule`,
    periods: [
      {
        name: "rds-start-stop-period",
        description: `testing period`,
        begintime: toTimeStr(currentTimePlus(3)),
        endtime: toTimeStr(currentTimePlus(7)),
      },
    ],
  });

  //confirm running during running period
  await delayMinutes(5);
  expect(await getInstanceState(rdsClient, resourceParams.rdsInstanceId)).toBeOneOf(["available", "starting"]);

  //confirm stopped after stop time
  await delayMinutes(4);
  expect(await getInstanceState(rdsClient, resourceParams.rdsInstanceId)).toBeOneOf(["stopped", "stopping"]);
}, 1_200_000);
