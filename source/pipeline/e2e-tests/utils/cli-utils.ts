// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { hubStackParams } from "./hub-stack-utils";
import * as dynamodb from "@aws-sdk/client-dynamodb";
import { unmarshall, marshall } from "@aws-sdk/util-dynamodb";

const configTableName = hubStackParams.configTableArn.substring(hubStackParams.configTableArn.lastIndexOf("/") + 1);
const dynamodbClient = new dynamodb.DynamoDBClient();

export interface Period {
  name: string;
  description: string;
  begintime: string;
  endtime: string;
  monthdays?: string;
  months?: string;
  weekdays?: string;
}

export interface Schedule {
  name: string;
  description: string;
  periods: Set<string>;
  ssm_maintenance_window?: Set<string>;
  override_status?: string;
  enforced?: boolean;
  timezone?: string;
  doNotStopNewInstance?: boolean;
  retainRunning?: boolean;
  hibernate?: boolean;
  useMetrics?: boolean;
}

export async function deleteConfigTableItemsWithNamePrefix(type: string, namePrefix: string) {
  const periodQueryResponse = await dynamodbClient.send(
    new dynamodb.QueryCommand({
      TableName: configTableName,
      KeyConditionExpression: "#type = :type AND begins_with(#name, :namePrefix)",
      ExpressionAttributeNames: {
        "#type": "type",
        "#name": "name",
      },
      ExpressionAttributeValues: {
        ":type": { S: type },
        ":namePrefix": { S: namePrefix },
      },
    }),
  );

  periodQueryResponse.Items?.forEach(async (item) => {
    await dynamodbClient.send(
      new dynamodb.DeleteItemCommand({
        TableName: configTableName,
        Key: {
          type: { S: item.type.S! },
          name: { S: item.name.S! },
        },
      }),
    );
  });
}

export async function getConfigTableItem(type: string, name: string) {
  const response = await dynamodbClient.send(
    new dynamodb.GetItemCommand({
      TableName: configTableName,
      Key: {
        type: { S: type },
        name: { S: name },
      },
    }),
  );

  if (response.Item === undefined) throw new Error("Did not find item");

  return unmarshall(response.Item);
}

export async function createSchedule(schedule: Schedule) {
  await dynamodbClient.send(
    new dynamodb.PutItemCommand({
      TableName: configTableName,
      Item: {
        ...marshall(schedule),
        type: { S: "schedule" },
      },
    }),
  );
}

export async function createPeriod(period: Period) {
  await dynamodbClient.send(
    new dynamodb.PutItemCommand({
      TableName: configTableName,
      Item: {
        ...marshall(period),
        type: { S: "period" },
      },
    }),
  );
}
