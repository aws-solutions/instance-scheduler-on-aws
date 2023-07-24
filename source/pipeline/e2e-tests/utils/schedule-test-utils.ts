// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import * as dynamodb from "@aws-sdk/client-dynamodb";
import { hubStackParams } from "./hub-stack-utils";
import { AttributeValue } from "@aws-sdk/client-dynamodb";

const configTableName = hubStackParams.configTableArn.substring(hubStackParams.configTableArn.lastIndexOf("/") + 1);
export interface Period {
  name: string;
  description: string;
  begintime: string;
  endtime: string;
}

export interface Schedule {
  name: string;
  description: string;
  periods?: Period[];
  use_maintenance_window?: boolean;
  ssm_maintenance_window?: string;
}
export async function createSchedule(schedule: Schedule) {
  const dynamoClient = new dynamodb.DynamoDBClient({});
  try {
    await dynamoClient.send(
      new dynamodb.BatchWriteItemCommand({
        RequestItems: {
          [configTableName]: scheduleToBatchedPutRequests(schedule),
        },
      }),
    );
  } finally {
    dynamoClient.destroy();
  }
}

/**
 * @return period-compatible time string that is n minutes in the future in UTC
 */
export function currentTimePlus(minutes: number): Date {
  const targetTime = new Date();
  targetTime.setTime(targetTime.getTime() + minutesToMillis(minutes));
  return targetTime;
}

export function toTimeStr(targetTime: Date): string {
  return `${targetTime.getUTCHours()}:${targetTime.getUTCMinutes()}`;
}

function minutesToMillis(minutes: number) {
  return minutes * 60_000;
}

function scheduleToBatchedPutRequests(schedule: Schedule): dynamodb.WriteRequest[] {
  const requests: dynamodb.WriteRequest[] = [];
  if (schedule.periods) requests.push(...schedule.periods.map((period) => putRequestForPeriod(period)));
  requests.push(putRequestForSchedule(schedule));

  return requests;
}

function putRequestForSchedule(schedule: Schedule): dynamodb.WriteRequest {
  const item: { [key: string]: AttributeValue } = {
    type: { S: "schedule" },
    name: { S: schedule.name },
    description: { S: schedule.description },
  };

  if (schedule.periods) item.periods = { SS: schedule.periods.map((period) => period.name) };
  if (schedule.use_maintenance_window) item.use_maintenance_window = { BOOL: schedule.use_maintenance_window };
  if (schedule.ssm_maintenance_window) item.ssm_maintenance_window = { S: schedule.ssm_maintenance_window };

  return {
    PutRequest: {
      Item: item,
    },
  };
}

function putRequestForPeriod(period: Period): dynamodb.WriteRequest {
  return {
    PutRequest: {
      Item: {
        type: { S: "period" },
        name: { S: period.name },
        description: { S: period.description },
        begintime: { S: period.begintime },
        endtime: { S: period.endtime },
      },
    },
  };
}
