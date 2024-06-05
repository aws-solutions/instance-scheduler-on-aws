// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import * as ec2 from "@aws-sdk/client-ec2";

export async function getInstanceState(client: ec2.EC2Client, instanceId: string) {
  const result = await client.send(
    new ec2.DescribeInstanceStatusCommand({
      InstanceIds: [instanceId],
      IncludeAllInstances: true,
    }),
  );

  // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
  if (!result.InstanceStatuses) throw new Error(`Instance with id of ${instanceId} Not Found`);

  // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
  return result.InstanceStatuses![0].InstanceState!.Name;
}

export async function setScheduleTag(client: ec2.EC2Client, instanceId: string, schedule: string) {
  await client.send(
    new ec2.CreateTagsCommand({
      Resources: [instanceId],
      Tags: [
        {
          Key: "Schedule",
          Value: schedule,
        },
      ],
    }),
  );
}
export async function clearScheduleTag(client: ec2.EC2Client, instanceId: string) {
  await client.send(
    new ec2.DeleteTagsCommand({
      Resources: [instanceId],
      Tags: [{ Key: "Schedule" }],
    }),
  );
}
