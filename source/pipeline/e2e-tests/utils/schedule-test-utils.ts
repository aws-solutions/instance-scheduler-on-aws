// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import * as dynamodb from "@aws-sdk/client-dynamodb";
import { hubStackParams } from "./hub-stack-utils";
import { AttributeValue } from "@aws-sdk/client-dynamodb";
import { setTimeout } from "timers/promises";

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
  ssm_maintenance_window?: string[];
  override_status?: string;
  enforced?: boolean;
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

export function zeroPadToTwoDigits(value: number): string {
  return ("0" + value).slice(-2);
}

export function toTimeStr(targetTime: Date): string {
  const hours = zeroPadToTwoDigits(targetTime.getHours());
  const minutes = zeroPadToTwoDigits(targetTime.getMinutes());
  return `${hours}:${minutes}`;
}

export function minutesToMillis(minutes: number) {
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
  if (schedule.ssm_maintenance_window) item.ssm_maintenance_window = { SS: schedule.ssm_maintenance_window };
  if (schedule.enforced) item.enforced = { BOOL: schedule.enforced };
  if (schedule.override_status) item.override_status = { S: schedule.override_status };

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

export async function waitForExpect(
  expectation: () => void | Promise<void>,
  timeout: number,
  interval: number,
): Promise<void> {
  const maxTries = Math.ceil(timeout / interval);

  let errorOnLastAttempt;

  for (let tries = 0; tries <= maxTries; tries++) {
    try {
      await expectation();
      return;
    } catch (error) {
      errorOnLastAttempt = error;
      await setTimeout(interval);
    }
  }

  throw new Error(
    `Timed out waiting for expectation to pass after ${timeout}ms. Error thrown by last attempt: ${errorOnLastAttempt}`,
  );
}
