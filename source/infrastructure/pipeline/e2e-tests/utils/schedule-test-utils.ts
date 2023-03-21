/*****************************************************************************
 *  Copyright 2020 Amazon.com, Inc. or its affiliates. All Rights Reserved.   *
 *                                                                            *
 *  Licensed under the Apache License, Version 2.0 (the "License"). You may   *
 *  not use this file except in compliance with the License. A copy of the    *
 *  License is located at                                                     *
 *                                                                            *
 *      http://www.apache.org/licenses/LICENSE-2.0                            *
 *                                                                            *
 *  or in the 'license' file accompanying this file. This file is distributed *
 *  on an 'AS IS' BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND,        *
 *  express or implied. See the License for the specific language governing   *
 *  permissions and limitations under the License.                            *
 *****************************************************************************/
import * as dynamodb from "@aws-sdk/client-dynamodb"
import {hubStackParams} from "./hub-stack-utils";

const configTableName = hubStackParams.configTableArn.substring(hubStackParams.configTableArn.lastIndexOf("/") + 1)
export interface Period {
  name: string,
  description: string
  begintime: string,
  endtime: string
}

export interface Schedule {
  name: string
  description: string
  periods: Period[]
}
export async function createSchedule(client: dynamodb.DynamoDBClient, schedule: Schedule) {
  await client.send(
    new dynamodb.BatchWriteItemCommand({
      RequestItems: {
        [configTableName]: scheduleToBatchedPutRequests(schedule)
      }
    })
  )
}

/**
 * @return period-compatible time string that is n minutes in the future in UTC
 */
export function currentTimePlus(minutes: number) : string{
  const targetTime = new Date();
  targetTime.setTime(targetTime.getTime() + minutesToMillis(minutes))
  return `${targetTime.getUTCHours()}:${targetTime.getUTCMinutes()}`
}

function minutesToMillis(minutes: number) {
  return minutes * 60_000;
}

function scheduleToBatchedPutRequests(schedule: Schedule) : dynamodb.WriteRequest[] {
  return [
    ...schedule.periods.map(period => putRequestForPeriod(period)),
    putRequestForSchedule(schedule)
  ]
}

function putRequestForSchedule(schedule: Schedule) : dynamodb.WriteRequest {
  return {
    PutRequest: {
      Item: {
        "type": {S: "schedule"},
        "name": {S: schedule.name},
        "description": {S: schedule.description},
        "periods": {SS: schedule.periods.map(period => period.name)}
      }
    }
  }
}

function putRequestForPeriod(period: Period) : dynamodb.WriteRequest {
  return {
    PutRequest: {
      Item: {
        "type": {S: "period"},
        "name": {S: period.name},
        "description": {S: period.description},
        "begintime": {S: period.begintime},
        "endtime": {S: period.endtime},
      }
    }
  }
}
