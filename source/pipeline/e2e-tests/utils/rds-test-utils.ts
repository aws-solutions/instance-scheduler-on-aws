// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import * as rds from "@aws-sdk/client-rds";

/**
 * returns the instance status
 *
 * https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/accessing-monitoring.html#Overview.DBInstance.Status
 */
export async function getInstanceState(client: rds.RDSClient, instanceId: string) {
  const result = await client.send(
    new rds.DescribeDBInstancesCommand({
      DBInstanceIdentifier: instanceId,
    }),
  );

  // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
  if (!result.DBInstances) throw new Error(`Instance with id of ${instanceId} Not Found`);

  // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
  return result.DBInstances![0].DBInstanceStatus!;
}
