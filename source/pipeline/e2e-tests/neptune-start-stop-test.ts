// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import * as neptune from "@aws-sdk/client-neptune";
import { resourceParams } from "./neptune-start-stop-test.resources";
import { createSchedule, currentTimePlus, toTimeStr } from "./utils/schedule-test-utils";
import { delayMinutes } from "./index";

async function getClusterState(client: neptune.NeptuneClient, clusterId: string) {
  const result = await client.send(
    new neptune.DescribeDBClustersCommand({
      DBClusterIdentifier: clusterId,
    }),
  );

  // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
  if (!result.DBClusters) throw new Error(`Cluster with id of ${clusterId} Not Found`);

  // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
  return result.DBClusters![0].Status!;
}
describe("neptune cluster", () => {
  const clusterId = resourceParams.neptuneInstanceId;
  const neptuneClient = new neptune.NeptuneClient({});

  test("clusterId exists", () => {
    expect(clusterId).not.toBeUndefined();
  });

  test("basic neptune start-stop", async () => {
    const preTestState = await getClusterState(neptuneClient, clusterId);
    //ensure instance is stopped
    if (!["stopped", "stopping"].includes(preTestState)) {
      console.log(`cluster in state ${preTestState} before test. Attempting to stop before running test...`);
      await neptuneClient.send(
        new neptune.StopDBClusterCommand({
          DBClusterIdentifier: clusterId,
        }),
      );
    }

    await createSchedule({
      name: resourceParams.startStopTestScheduleName,
      description: "neptune test schedule",
      periods: [
        {
          name: "neptune-start-stop-period",
          description: `testing period`,
          begintime: toTimeStr(currentTimePlus(3)),
          endtime: toTimeStr(currentTimePlus(7)),
        },
      ],
    });

    //confirm running during running period
    await delayMinutes(5); //2 minutes after start defined in schedule (1-2 scheduling executions)
    expect(await getClusterState(neptuneClient, resourceParams.neptuneInstanceId)).toBeOneOf(["available", "starting"]);

    //confirm stopped after stop time
    await delayMinutes(5); //2 minutes after stop defined in schedule (1-2 scheduling executions)
    expect(await getClusterState(neptuneClient, resourceParams.neptuneInstanceId)).toBeOneOf(["stopped", "stopping"]);
  });
});
