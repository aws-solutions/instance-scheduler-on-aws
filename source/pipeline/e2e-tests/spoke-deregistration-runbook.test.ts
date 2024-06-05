// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import * as dynamodb from "@aws-sdk/client-dynamodb";
import * as ssm from "@aws-sdk/client-ssm";
import { CfnStackResourceFinder } from "./utils/cfn-utils";
import { delaySeconds } from "./index";

const dynamoClient = new dynamodb.DynamoDBClient();
const ssmClient = new ssm.SSMClient();

describe("SpokeRegistrationRunbook", () => {
  test("deregister account", async () => {
    const hubStackName = process.env["HUB_STACK"];
    if (!hubStackName) {
      throw new Error(`Missing required environment variable: HUB_STACK`);
    }
    const stackResourceFinder = await CfnStackResourceFinder.fromStackName(hubStackName);
    const configTableName = stackResourceFinder.findResourceByPartialId("ConfigTable")?.PhysicalResourceId;
    const spokeRegistrationRunbookName =
      stackResourceFinder.findResourceByPartialId("SpokeDeregistrationRunbook")?.PhysicalResourceId;

    await dynamoClient.send(
      new dynamodb.UpdateItemCommand({
        TableName: configTableName,
        Key: { type: { S: "config" }, name: { S: "scheduler" } },
        UpdateExpression: "ADD remote_account_ids :a",
        ExpressionAttributeValues: { ":a": { SS: ["111111111111", "222222222222", "333333333333"] } },
      }),
    );

    await ssmClient.send(
      new ssm.StartAutomationExecutionCommand({
        DocumentName: spokeRegistrationRunbookName,
        Parameters: {
          AccountId: ["111111111111"],
        },
      }),
    );

    // The automation runs almost instantly ( < 1s ) but delay is still required to check results
    await delaySeconds(10);

    const accounts = await dynamoClient.send(
      new dynamodb.GetItemCommand({
        TableName: configTableName,
        Key: { type: { S: "config" }, name: { S: "scheduler" } },
        ProjectionExpression: "remote_account_ids",
      }),
    );

    expect(accounts.Item?.remote_account_ids.SS).not.toContainEqual(["111111111111"]);
    expect(accounts.Item?.remote_account_ids.SS).toEqual(expect.arrayContaining(["222222222222", "333333333333"]));

    await dynamoClient.send(
      new dynamodb.UpdateItemCommand({
        TableName: configTableName,
        Key: { type: { S: "config" }, name: { S: "scheduler" } },
        UpdateExpression: "DELETE remote_account_ids :a",
        ExpressionAttributeValues: { ":a": { SS: ["111111111111", "222222222222", "333333333333"] } },
      }),
    );
  }, 30000);
});
