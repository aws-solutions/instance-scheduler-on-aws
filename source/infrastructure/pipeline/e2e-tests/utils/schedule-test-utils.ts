// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import * as dynamodb from "@aws-sdk/client-dynamodb";
import { hubStackParams } from "./hub-stack-utils";

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
  periods: Period[];
}
export async function createSchedule(schedule: Schedule) {
  const dynamoClient = new dynamodb.DynamoDBClient({});
  try {
    await dynamoClient.send(
      new dynamodb.BatchWriteItemCommand({
        RequestItems: {
          [configTableName]: scheduleToBatchedPutRequests(schedule),
        },
      })
    );
  } finally {
    dynamoClient.destroy();
  }
}

/**
 * @return period-compatible time string that is n minutes in the future in UTC
 */
export function currentTimePlus(minutes: number): string {
  const targetTime = new Date();
  targetTime.setTime(targetTime.getTime() + minutesToMillis(minutes));
  return `${targetTime.getUTCHours()}:${targetTime.getUTCMinutes()}`;
}

function minutesToMillis(minutes: number) {
  return minutes * 60_000;
}

function scheduleToBatchedPutRequests(schedule: Schedule): dynamodb.WriteRequest[] {
  return [...schedule.periods.map((period) => putRequestForPeriod(period)), putRequestForSchedule(schedule)];
}

function putRequestForSchedule(schedule: Schedule): dynamodb.WriteRequest {
  return {
    PutRequest: {
      Item: {
        type: { S: "schedule" },
        name: { S: schedule.name },
        description: { S: schedule.description },
        periods: { SS: schedule.periods.map((period) => period.name) },
      },
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
