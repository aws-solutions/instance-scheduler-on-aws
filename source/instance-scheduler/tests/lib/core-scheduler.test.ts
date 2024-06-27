// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import {
  conditions,
  coreScheduler,
  defaultTimezone,
  logRetentionDays,
  memorySizeMB,
  namespace,
  principals,
  regions,
  schedulingIntervalMinutes,
  solutionId,
  solutionName,
  solutionVersion,
  startTags,
  stopTags,
  tagKey,
} from "../test_utils/stack-factories";

describe("core scheduler", function () {
  const functions = coreScheduler.findResources("AWS::Lambda::Function");
  const functionIds = Object.getOwnPropertyNames(functions);
  expect(functionIds).toHaveLength(8);
  const mainFunctionId = functionIds.find((funcId: string) => funcId == "Main");
  if (!mainFunctionId) {
    throw Error("unable to locate main function");
  }
  const lambdaFunction = functions[mainFunctionId];

  const roleId = lambdaFunction.Properties.Role["Fn::GetAtt"][0];
  const roles = coreScheduler.findResources("AWS::IAM::Role");
  const role = roles[roleId];

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
  const topicId = topicIds[0];

  describe("function", function () {
    it("has expected id", function () {
      expect(mainFunctionId).toEqual("Main");
    });

    it("has expected memory", function () {
      expect(lambdaFunction.Properties.MemorySize).toEqual(memorySizeMB);
    });

    describe("environment", function () {
      const env = lambdaFunction.Properties.Environment.Variables;

      it("has scheduler interval", function () {
        expect(env).toEqual(
          expect.objectContaining({
            SCHEDULER_FREQUENCY: schedulingIntervalMinutes.toString(),
          }),
        );
      });

      it("has stack name", function () {
        expect(env).toEqual(
          expect.objectContaining({
            STACK_NAME: { Ref: "AWS::StackName" },
          }),
        );
      });

      it("has send metrics", function () {
        expect(env).toEqual(
          expect.objectContaining({
            SEND_METRICS: { "Fn::If": [conditions.sendMetrics, "True", "False"] },
          }),
        );
      });

      it("has solution id", function () {
        expect(env).toEqual(
          expect.objectContaining({
            SOLUTION_ID: solutionId,
          }),
        );
      });

      it("has solution version", function () {
        expect(env).toEqual(
          expect.objectContaining({
            SOLUTION_VERSION: solutionVersion,
          }),
        );
      });

      it("has enable debug logging", function () {
        expect(env).toEqual(
          expect.objectContaining({
            TRACE: { "Fn::If": [conditions.enableDebugLogging, "True", "False"] },
          }),
        );
      });

      it("has user agent extra", function () {
        expect(env).toEqual(
          expect.objectContaining({
            USER_AGENT_EXTRA: `AwsSolution/${solutionId}/${solutionVersion}`,
          }),
        );
      });

      it("has metrics url", function () {
        expect(env).toEqual(
          expect.objectContaining({
            METRICS_URL: "https://metrics.awssolutionsbuilder.com/generic",
          }),
        );
      });

      it("has stack id", function () {
        expect(env).toEqual(
          expect.objectContaining({
            STACK_ID: { Ref: "AWS::StackId" },
          }),
        );
      });

      it("has uuid key", function () {
        expect(env).toEqual(
          expect.objectContaining({
            UUID_KEY: `/Solutions/${solutionName}/UUID/`,
          }),
        );
      });

      it("has start ec2 batch size", function () {
        expect(env).toEqual(
          expect.objectContaining({
            START_EC2_BATCH_SIZE: "5",
          }),
        );
      });

      it("has schedule tag key", function () {
        expect(env).toEqual(
          expect.objectContaining({
            SCHEDULE_TAG_KEY: tagKey,
          }),
        );
      });

      it("has default timezone", function () {
        expect(env).toEqual(
          expect.objectContaining({
            DEFAULT_TIMEZONE: defaultTimezone,
          }),
        );
      });

      it("has enable ec2", function () {
        expect(env).toEqual(
          expect.objectContaining({
            ENABLE_EC2_SERVICE: { "Fn::If": [conditions.enableEc2, "True", "False"] },
          }),
        );
      });

      it("has enable rds", function () {
        expect(env).toEqual(
          expect.objectContaining({
            ENABLE_RDS_SERVICE: { "Fn::If": [conditions.enableRds, "True", "False"] },
          }),
        );
      });

      it("has enable rds clusters", function () {
        expect(env).toEqual(
          expect.objectContaining({
            ENABLE_RDS_CLUSTERS: { "Fn::If": [conditions.enableRdsClusters, "True", "False"] },
          }),
        );
      });

      it("has enable neptune", function () {
        expect(env).toEqual(
          expect.objectContaining({
            ENABLE_NEPTUNE_SERVICE: { "Fn::If": [conditions.enableNeptune, "True", "False"] },
          }),
        );
      });

      it("has enable docdb", function () {
        expect(env).toEqual(
          expect.objectContaining({
            ENABLE_DOCDB_SERVICE: { "Fn::If": [conditions.enableDocDb, "True", "False"] },
          }),
        );
      });

      it("has enable rds snapshots", function () {
        expect(env).toEqual(
          expect.objectContaining({
            ENABLE_RDS_SNAPSHOTS: { "Fn::If": [conditions.enableRdsSnapshots, "True", "False"] },
          }),
        );
      });

      it("has schedule regions", function () {
        expect(env).toEqual(
          expect.objectContaining({
            SCHEDULE_REGIONS: regions.join(","),
          }),
        );
      });

      it("has namespace", function () {
        expect(env).toEqual(
          expect.objectContaining({
            APP_NAMESPACE: namespace,
          }),
        );
      });

      it("has scheduler role name", function () {
        expect(env).toEqual(
          expect.objectContaining({
            SCHEDULER_ROLE_NAME: "Scheduler-Role",
          }),
        );
      });

      it("has enable schedule hub account", function () {
        expect(env).toEqual(
          expect.objectContaining({
            ENABLE_SCHEDULE_HUB_ACCOUNT: { "Fn::If": [conditions.enableHubAcctScheduling, "True", "False"] },
          }),
        );
      });

      it("has enable ec2 ssm maintenance windows", function () {
        expect(env).toEqual(
          expect.objectContaining({
            ENABLE_EC2_SSM_MAINTENANCE_WINDOWS: {
              "Fn::If": [conditions.enableEc2MaintWindows, "True", "False"],
            },
          }),
        );
      });

      it("has start tags", function () {
        expect(env).toEqual(
          expect.objectContaining({
            START_TAGS: startTags,
          }),
        );
      });

      it("has stop tags", function () {
        expect(env).toEqual(
          expect.objectContaining({
            STOP_TAGS: stopTags,
          }),
        );
      });

      it("has enable aws organizations", function () {
        expect(env).toEqual(
          expect.objectContaining({
            ENABLE_AWS_ORGANIZATIONS: { "Fn::If": [conditions.enableAwsOrgs, "True", "False"] },
          }),
        );
      });

      it("has topic arn", function () {
        expect(env).toEqual(
          expect.objectContaining({
            ISSUES_TOPIC_ARN: { Ref: topicId },
          }),
        );
      });

      it("has state table name", function () {
        expect(env).toEqual(
          expect.objectContaining({
            STATE_TABLE: { Ref: stateTableLogicalId },
          }),
        );
      });

      it("has config table name", function () {
        expect(env).toEqual(
          expect.objectContaining({
            CONFIG_TABLE: { Ref: configTableLogicalId },
          }),
        );
      });

      it("has maintenance window table name", function () {
        expect(env).toEqual(
          expect.objectContaining({
            MAINTENANCE_WINDOW_TABLE: { Ref: maintenanceWindowTableLogicalId },
          }),
        );
      });
    });

    describe("role", function () {
      describe("trust relationship", function () {
        it("includes lambda", function () {
          expect(role.Properties.AssumeRolePolicyDocument.Statement).toEqual(
            expect.arrayContaining([
              {
                Action: "sts:AssumeRole",
                Effect: "Allow",
                Principal: { Service: "lambda.amazonaws.com" },
              },
            ]),
          );
        });
      });

      describe("policy", function () {
        const policies = coreScheduler.findResources("AWS::IAM::Policy", {
          Properties: {
            Roles: [{ Ref: roleId }],
          },
        });
        const policyIds = Object.getOwnPropertyNames(policies);
        const defaultPolicyId = policyIds.find((policyId: string) => policyId.includes("DefaultPolicy"));
        if (!defaultPolicyId) {
          throw new Error("Could not find default policy");
        }
        const policy = policies[defaultPolicyId];

        it("has xray permissions", function () {
          expect(policy.Properties.PolicyDocument.Statement).toEqual(
            expect.arrayContaining([
              {
                Action: expect.arrayContaining(["xray:PutTraceSegments", "xray:PutTelemetryRecords"]),
                Effect: "Allow",
                Resource: "*",
              },
            ]),
          );
        });

        const readWritePermissions = [
          "dynamodb:BatchGetItem",
          "dynamodb:GetRecords",
          "dynamodb:GetShardIterator",
          "dynamodb:Query",
          "dynamodb:GetItem",
          "dynamodb:Scan",
          "dynamodb:ConditionCheckItem",
          "dynamodb:BatchWriteItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:DescribeTable",
        ];

        it("has config table permissions", function () {
          expect(policy.Properties.PolicyDocument.Statement).toEqual(
            expect.arrayContaining([
              {
                Action: expect.arrayContaining(readWritePermissions),
                Effect: "Allow",
                Resource: expect.arrayContaining([
                  {
                    ["Fn::GetAtt"]: [configTableLogicalId, "Arn"],
                  },
                ]),
              },
            ]),
          );
        });

        it("has key permissions", function () {
          const keys = coreScheduler.findResources("AWS::KMS::Key");
          const keyIds = Object.getOwnPropertyNames(keys);
          expect(keyIds).toHaveLength(1);
          expect(policy.Properties.PolicyDocument.Statement).toEqual(
            expect.arrayContaining([
              {
                Action: expect.arrayContaining([
                  "kms:Decrypt",
                  "kms:DescribeKey",
                  "kms:Encrypt",
                  "kms:ReEncrypt*",
                  "kms:GenerateDataKey*",
                ]),
                Effect: "Allow",
                Resource: { "Fn::GetAtt": [keyIds[0], "Arn"] },
              },
            ]),
          );
        });

        const functionName = lambdaFunction.Properties.FunctionName;
        const functionNameSuffix = "-InstanceSchedulerMain";
        expect(functionName).toEqual({ "Fn::Join": ["", [{ Ref: "AWS::StackName" }, functionNameSuffix]] });

        it("has basic logging permissions", function () {
          expect(policy.Properties.PolicyDocument.Statement).toEqual(
            expect.arrayContaining([
              {
                Action: "logs:CreateLogGroup",
                Effect: "Allow",
                Resource: {
                  "Fn::Join": [
                    "",
                    [
                      "arn:",
                      { Ref: "AWS::Partition" },
                      ":logs:",
                      { Ref: "AWS::Region" },
                      ":",
                      { Ref: "AWS::AccountId" },
                      ":*",
                    ],
                  ],
                },
              },
            ]),
          );

          expect(policy.Properties.PolicyDocument.Statement).toEqual(
            expect.arrayContaining([
              {
                Action: expect.arrayContaining([
                  "logs:CreateLogStream",
                  "logs:PutLogEvents",
                  "logs:PutRetentionPolicy",
                ]),
                Effect: "Allow",
                Resource: {
                  "Fn::Join": [
                    "",
                    [
                      "arn:",
                      { Ref: "AWS::Partition" },
                      ":logs:",
                      { Ref: "AWS::Region" },
                      ":",
                      { Ref: "AWS::AccountId" },
                      ":log-group:/aws/lambda/",
                      { Ref: "AWS::StackName" },
                      `${functionNameSuffix}:*`,
                    ],
                  ],
                },
              },
            ]),
          );
        });

        it("has sns permissions", function () {
          expect(policy.Properties.PolicyDocument.Statement).toEqual(
            expect.arrayContaining([
              {
                Action: "sns:Publish",
                Effect: "Allow",
                Resource: { Ref: topicId },
              },
            ]),
          );
        });
      });
    });
  });
});
