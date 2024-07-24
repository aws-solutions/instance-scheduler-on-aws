// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import {
  conditions,
  coreScheduler,
  logRetentionDays,
  principals,
  schedulingIntervalMinutes,
} from "../test_utils/stack-factories";

describe("core scheduler", function () {
  const functions = coreScheduler.findResources("AWS::Lambda::Function");
  const functionIds = Object.getOwnPropertyNames(functions);
  expect(functionIds).toHaveLength(8);
  const mainFunctionId = functionIds.find((funcId: string) => funcId == "Main");
  if (!mainFunctionId) {
    throw Error("unable to locate main function");
  }

  const keys = coreScheduler.findResources("AWS::KMS::Key");
  const keyIds = Object.getOwnPropertyNames(keys);
  expect(keyIds).toHaveLength(1);
  const keyId = keyIds[0];
  const key = keys[keyId];

  describe("key", function () {
    it("has expected id", function () {
      expect(keyId).toEqual("InstanceSchedulerEncryptionKey");
    });

    it("is enabled", function () {
      expect(key.Properties.Enabled).toEqual(true);
    });

    it("has rotation enabled", function () {
      expect(key.Properties.EnableKeyRotation).toEqual(true);
    });

    it("is retained if ddb tables are retained", function () {
      expect(key.DeletionPolicy).toEqual({
        "Fn::If": [conditions.enableDdbDeletionProtection, "Retain", "Delete"],
      });
      expect(key.UpdateReplacePolicy).toEqual({
        "Fn::If": [conditions.enableDdbDeletionProtection, "Retain", "Delete"],
      });
    });

    describe("policy", function () {
      it("grants admin access to root principal", function () {
        expect(key.Properties.KeyPolicy.Statement).toEqual(
          expect.arrayContaining([
            {
              Action: "kms:*",
              Effect: "Allow",
              Principal: {
                AWS: {
                  "Fn::Join": ["", ["arn:", { Ref: "AWS::Partition" }, ":iam::", { Ref: "AWS::AccountId" }, ":root"]],
                },
              },
              Resource: "*",
            },
          ]),
        );
      });
    });

    describe("alias", function () {
      const aliases = coreScheduler.findResources("AWS::KMS::Alias");
      const aliasIds = Object.getOwnPropertyNames(aliases);
      expect(aliasIds).toHaveLength(1);
      const aliasId = aliasIds[0];
      const alias = aliases[aliasId];

      it("has expected id", function () {
        expect(aliasId).toEqual("InstanceSchedulerEncryptionKeyAlias");
      });

      it("has expected name", function () {
        expect(alias.Properties.AliasName).toEqual({
          "Fn::Join": ["", ["alias/", { Ref: "AWS::StackName" }, "-instance-scheduler-encryption-key"]],
        });
      });

      it("targets key", function () {
        expect(alias.Properties.TargetKeyId).toEqual({ "Fn::GetAtt": [keyId, "Arn"] });
      });
    });
  });

  const stateTableLogicalId = "StateTable";

  describe("state table", function () {
    const table = coreScheduler.findResources("AWS::DynamoDB::Table")[stateTableLogicalId];

    it("partition key is service", function () {
      const key = "service";

      expect(table.Properties.KeySchema).toEqual(
        expect.arrayContaining([
          {
            AttributeName: key,
            KeyType: "HASH",
          },
        ]),
      );
      expect(table.Properties.AttributeDefinitions).toEqual(
        expect.arrayContaining([
          {
            AttributeName: key,
            AttributeType: "S",
          },
        ]),
      );
    });

    it("sort key is account-region", function () {
      const key = "account-region";

      expect(table.Properties.KeySchema).toEqual(
        expect.arrayContaining([
          {
            AttributeName: key,
            KeyType: "RANGE",
          },
        ]),
      );
      expect(table.Properties.AttributeDefinitions).toEqual(
        expect.arrayContaining([
          {
            AttributeName: key,
            AttributeType: "S",
          },
        ]),
      );
    });

    it("is billed per-request", function () {
      expect(table.Properties.BillingMode).toStrictEqual("PAY_PER_REQUEST");
    });

    it("has point-in-time recovery enabled", function () {
      expect(table.Properties.PointInTimeRecoverySpecification).toStrictEqual({
        PointInTimeRecoveryEnabled: true,
      });
    });

    it("is encrypted with KMS key", function () {
      const keys = coreScheduler.findResources("AWS::KMS::Key");
      const keyIds = Object.getOwnPropertyNames(keys);
      expect(keyIds).toHaveLength(1);
      expect(table.Properties.SSESpecification).toStrictEqual({
        KMSMasterKeyId: { "Fn::GetAtt": [keyIds[0], "Arn"] },
        SSEEnabled: true,
        SSEType: "KMS",
      });
    });

    it("has deletion protection enabled", function () {
      expect(table.Properties.DeletionProtectionEnabled).toEqual({
        "Fn::If": [conditions.enableDdbDeletionProtection, "True", "False"],
      });
    });
  });

  const configTableLogicalId = "ConfigTable";

  describe("config table", function () {
    const table = coreScheduler.findResources("AWS::DynamoDB::Table")[configTableLogicalId];

    it("partition key is type", function () {
      const key = "type";

      expect(table.Properties.KeySchema).toEqual(
        expect.arrayContaining([
          {
            AttributeName: key,
            KeyType: "HASH",
          },
        ]),
      );
      expect(table.Properties.AttributeDefinitions).toEqual(
        expect.arrayContaining([
          {
            AttributeName: key,
            AttributeType: "S",
          },
        ]),
      );
    });

    it("sort key is name", function () {
      const key = "name";

      expect(table.Properties.KeySchema).toEqual(
        expect.arrayContaining([
          {
            AttributeName: key,
            KeyType: "RANGE",
          },
        ]),
      );
      expect(table.Properties.AttributeDefinitions).toEqual(
        expect.arrayContaining([
          {
            AttributeName: key,
            AttributeType: "S",
          },
        ]),
      );
    });

    it("is billed per-request", function () {
      expect(table.Properties.BillingMode).toStrictEqual("PAY_PER_REQUEST");
    });

    it("has point-in-time recovery enabled", function () {
      expect(table.Properties.PointInTimeRecoverySpecification).toStrictEqual({
        PointInTimeRecoveryEnabled: true,
      });
    });

    it("is encrypted with KMS key", function () {
      const keys = coreScheduler.findResources("AWS::KMS::Key");
      const keyIds = Object.getOwnPropertyNames(keys);
      expect(keyIds).toHaveLength(1);
      expect(table.Properties.SSESpecification).toStrictEqual({
        KMSMasterKeyId: { "Fn::GetAtt": [keyIds[0], "Arn"] },
        SSEEnabled: true,
        SSEType: "KMS",
      });
    });

    it("has deletion protection enabled", function () {
      expect(table.Properties.DeletionProtectionEnabled).toEqual({
        "Fn::If": [conditions.enableDdbDeletionProtection, "True", "False"],
      });
    });
  });

  const maintenanceWindowTableLogicalId = "MaintenanceWindowTable";

  describe("maintenance window table", function () {
    const table = coreScheduler.findResources("AWS::DynamoDB::Table")[maintenanceWindowTableLogicalId];

    it("partition key is account-region", function () {
      const key = "account-region";

      expect(table.Properties.KeySchema).toEqual(
        expect.arrayContaining([
          {
            AttributeName: key,
            KeyType: "HASH",
          },
        ]),
      );
      expect(table.Properties.AttributeDefinitions).toEqual(
        expect.arrayContaining([
          {
            AttributeName: key,
            AttributeType: "S",
          },
        ]),
      );
    });

    it("sort key is name-id", function () {
      const key = "name-id";

      expect(table.Properties.KeySchema).toEqual(
        expect.arrayContaining([
          {
            AttributeName: key,
            KeyType: "RANGE",
          },
        ]),
      );
      expect(table.Properties.AttributeDefinitions).toEqual(
        expect.arrayContaining([
          {
            AttributeName: key,
            AttributeType: "S",
          },
        ]),
      );
    });

    it("is billed per-request", function () {
      expect(table.Properties.BillingMode).toStrictEqual("PAY_PER_REQUEST");
    });

    it("has point-in-time recovery enabled", function () {
      expect(table.Properties.PointInTimeRecoverySpecification).toStrictEqual({
        PointInTimeRecoveryEnabled: true,
      });
    });

    it("is encrypted with KMS key", function () {
      const keys = coreScheduler.findResources("AWS::KMS::Key");
      const keyIds = Object.getOwnPropertyNames(keys);
      expect(keyIds).toHaveLength(1);
      expect(table.Properties.SSESpecification).toStrictEqual({
        KMSMasterKeyId: { "Fn::GetAtt": [keyIds[0], "Arn"] },
        SSEEnabled: true,
        SSEType: "KMS",
      });
    });

    it("has deletion protection enabled", function () {
      expect(table.Properties.DeletionProtectionEnabled).toEqual({
        "Fn::If": [conditions.enableDdbDeletionProtection, "True", "False"],
      });
    });
  });

  const logGroups = coreScheduler.findResources("AWS::Logs::LogGroup");
  const logGroupIds = Object.getOwnPropertyNames(logGroups);
  expect(logGroupIds).toHaveLength(7);

  describe("setup custom resource", function () {
    const setupResources = coreScheduler.findResources("Custom::ServiceSetup");
    const setupResourceIds = Object.getOwnPropertyNames(setupResources);
    expect(setupResourceIds).toHaveLength(1);
    const setupResourceId = setupResourceIds[0];
    const setupResource = setupResources[setupResourceId];

    it("targets function", function () {
      expect(setupResource.Properties.ServiceToken).toEqual({
        "Fn::GetAtt": [mainFunctionId, "Arn"],
      });
    });

    it("has expected properties", function () {
      expect(setupResourceId).toEqual("SchedulerConfigHelper");
      expect(setupResource.Properties).toHaveProperty("log_retention_days", logRetentionDays);
      expect(setupResource.Properties).toHaveProperty("remote_account_ids", principals);
      expect(setupResource.Properties).toHaveProperty("timeout", 120);
    });

    it("is not retained", function () {
      expect(setupResource.DeletionPolicy).toStrictEqual("Delete");
    });
  });

  describe("orchestrator-rule", function () {
    const rules = coreScheduler.findResources("AWS::Events::Rule");

    const ruleName = Object.keys(rules).find((rule) => rule.includes("SchedulerEventRule"));
    const scheduleRule = ruleName ? rules[ruleName] : null;

    if (!scheduleRule) {
      throw new Error("Could not find schedule rule");
    }

    it("has expected rate expression", function () {
      const mappingLogicalId = "CronExpressionsForSchedulingIntervals";
      const mappings = coreScheduler.findMappings(mappingLogicalId);
      const mappingIds = Object.getOwnPropertyNames(mappings);
      expect(mappingIds).toHaveLength(1);

      const mappingKey = "IntervalMinutesToCron";
      expect(scheduleRule.Properties.ScheduleExpression).toEqual({
        "Fn::FindInMap": [mappingLogicalId, mappingKey, schedulingIntervalMinutes.toString()],
      });
      expect(mappings[mappingIds[0]][mappingKey][schedulingIntervalMinutes.toString()]).toEqual(
        `cron(0/${schedulingIntervalMinutes} * * * ? *)`,
      );
    });

    it("has expected state", function () {
      expect(scheduleRule.Properties.State).toEqual({
        "Fn::If": [conditions.schedulingEnabled, "ENABLED", "DISABLED"],
      });
    });

    it("targets orchestrator", function () {
      expect(scheduleRule.Properties.Targets).toEqual(
        expect.arrayContaining([
          {
            Arn: {
              "Fn::GetAtt": [expect.stringContaining("SchedulingOrchestrator"), "Arn"],
            },
            Id: expect.any(String),
            Input: JSON.stringify({ scheduled_action: "run_orchestrator" }),
            RetryPolicy: { MaximumRetryAttempts: 5 },
          },
        ]),
      );
    });
  });

  const topics = coreScheduler.findResources("AWS::SNS::Topic");
  const topicIds = Object.getOwnPropertyNames(topics);
  expect(topicIds).toHaveLength(1);
});
