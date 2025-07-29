// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { Stack } from "aws-cdk-lib";
import { Template } from "aws-cdk-lib/assertions";
import { AttributeType, BillingMode, StreamViewType, Table, TableEncryption } from "aws-cdk-lib/aws-dynamodb";
import { Key } from "aws-cdk-lib/aws-kms";
import { Topic } from "aws-cdk-lib/aws-sns";
import { AnonymizedMetricsEnvironment } from "../../lib/anonymized-metrics-environment";
import { AsgScheduler } from "../../lib/asg-scheduler";
import { trueCondition } from "../../lib/cfn";
import { CoreScheduler } from "../../lib/core-scheduler";
import { AsgSchedulingRole } from "../../lib/iam/asg-scheduling-role";
import { AsgHandler } from "../../lib/lambda-functions/asg-handler";
import { TestFunctionFactory } from "../../lib/lambda-functions/function-factory";

export const solutionName = "my-solution-name";
export const solutionVersion = "v9.9.9";
export const solutionId = "my-solution-id";
export const memorySizeMB = 128;
export const logRetentionDays = 90;
export const principals: string[] = [];
export const schedulingIntervalMinutes = 5;
export const namespace = "prod";
export const tagKey = "my-tag-key";
export const defaultTimezone = "my-timezone";
export const regions = ["us-east-1", "us-west-2"];
export const startTags = "my-start-tags";
export const stopTags = "my-stop-tags";
export const appregApplicationName = "my-appreg-application-name";
export const appregSolutionName = "my-appreg-solution-name";
export const scheduledTagKey = "scheduled";
export const rulePrefix = "is-";
export const userAgentExtra = `AwsSolution/${solutionId}/${solutionVersion}`;
export const metricsEnv: AnonymizedMetricsEnvironment = {
  SEND_METRICS: "True",
  METRICS_URL: "https://example.com",
  SOLUTION_ID: solutionId,
  SOLUTION_VERSION: solutionVersion,
  SCHEDULING_INTERVAL_MINUTES: schedulingIntervalMinutes.toString(),
  METRICS_UUID: "metrics-uuid",
};

/**
 * testable condition values for use in tests of the format:
 * expect(myCfnObject).toHaveProperty("Condition", conditions.ConditionToTest);
 */
export const conditions = {
  schedulingEnabled: "SchedulingEnabledCond",
  enableDebugLogging: "EnableDebugLoggingCond",
  enableCloudwatchMetrics: "EnableCloudwatchMetricsCond",
  sendMetrics: "SendMetricsCond",
  enableEc2: "EnableEc2Cond",
  enableRds: "EnableRdsCond",
  enableRdsClusters: "EnableRdsClustersCond",
  enableNeptune: "EnableNeptuneCond",
  enableDocDb: "EnableDocdbCond",
  enableRdsSnapshots: "EnableRdsSnapshotCond",
  enableHubAcctScheduling: "EnableHubAccountSchedulingCond",
  enableEc2MaintWindows: "EnableEc2MaintenanceWindowsCond",
  enableAwsOrgs: "EnableAwsOrgsCond",
  enableDdbDeletionProtection: "EnableDdbDeletionProtectionCond",
  enableAsgs: "EnableAsgsCond",
  provideKmsToScheduler: "ProvideKmsAccesstoScheduler",
  deployOpsInsightsDashboard: "DeployPropsInsightsDashboardCond",
  gatherPerInstanceTypeMetrics: "GatherPerInstanceTypeMetricsCond",
  gatherPerScheduleMetrics: "GatherPerScheduleMetricsCond",
};

export const coreScheduler = newCoreScheduler();
export function findResource(resourceType: string, partialId: string) {
  const resources = coreScheduler.findResources(resourceType);
  const resourceIds = Object.getOwnPropertyNames(resources);
  const foundResourceId = resourceIds.find((id: string) => id.includes(partialId));
  if (foundResourceId) {
    return resources[foundResourceId];
  } else {
    throw new Error(
      `unable to find resource of type ${resourceType} containing ${partialId}.\nResources searched: ${resourceIds}`,
    );
  }
}
export function newCoreScheduler(): Template {
  const stack = new Stack();

  new CoreScheduler(stack, {
    solutionName,
    solutionVersion,
    solutionId,
    memorySizeMB,
    orchestratorMemorySizeMB: 128,
    asgMemorySizeMB: 128,
    principals,
    logRetentionDays,
    schedulingEnabled: trueCondition(stack, conditions.schedulingEnabled),
    schedulingIntervalMinutes,
    namespace,
    sendAnonymizedMetrics: trueCondition(stack, conditions.sendMetrics),
    enableDebugLogging: trueCondition(stack, conditions.enableDebugLogging),
    tagKey,
    defaultTimezone,
    enableEc2: trueCondition(stack, conditions.enableEc2),
    enableRds: trueCondition(stack, conditions.enableRds),
    enableRdsClusters: trueCondition(stack, conditions.enableRdsClusters),
    enableNeptune: trueCondition(stack, conditions.enableNeptune),
    enableDocdb: trueCondition(stack, conditions.enableDocDb),
    enableRdsSnapshots: trueCondition(stack, conditions.enableRdsSnapshots),
    regions,
    enableSchedulingHubAccount: trueCondition(stack, conditions.enableHubAcctScheduling),
    enableEc2SsmMaintenanceWindows: trueCondition(stack, conditions.enableEc2MaintWindows),
    startTags,
    stopTags,
    enableAwsOrganizations: trueCondition(stack, conditions.enableAwsOrgs),
    enableOpsInsights: trueCondition(stack, conditions.deployOpsInsightsDashboard),
    kmsKeyArns: ["*"],
    factory: new TestFunctionFactory(),
    enableDdbDeletionProtection: trueCondition(stack, conditions.enableDdbDeletionProtection),
    enableAsgs: trueCondition(stack, conditions.enableAsgs),
    scheduledTagKey,
    rulePrefix,
  });

  return Template.fromStack(stack);
}

export function createAsgSchedulerStack(id: string): Stack {
  const stack = new Stack();
  const key = new Key(stack, "Key");
  const configTable = new Table(stack, "ConfigTable", {
    sortKey: { name: "name", type: AttributeType.STRING },
    partitionKey: { name: "type", type: AttributeType.STRING },
    billingMode: BillingMode.PAY_PER_REQUEST,
    pointInTimeRecovery: true,
    encryption: TableEncryption.CUSTOMER_MANAGED,
    encryptionKey: key,
    stream: StreamViewType.KEYS_ONLY,
  });
  const topic = new Topic(stack, "Topic");
  const enableDebugLogging = trueCondition(stack, conditions.enableDebugLogging);

  const asgHandler = new AsgHandler(stack, {
    USER_AGENT_EXTRA: userAgentExtra,
    DEFAULT_TIMEZONE: defaultTimezone,
    asgSchedulingRoleName: AsgSchedulingRole.roleName(namespace),
    memorySizeMB: 128,
    configTable,
    enableDebugLogging,
    encryptionKey: key,
    factory: new TestFunctionFactory(),
    logRetentionDays,
    metricsEnv,
    namespace,
    rulePrefix,
    scheduledTagKey,
    snsErrorReportingTopic: topic,
    tagKey,
  });

  new AsgScheduler(stack, id, {
    USER_AGENT_EXTRA: userAgentExtra,
    asgHandler,
    configTable,
    orchestratorMemorySizeMB: 128,
    enableAsgs: trueCondition(stack, conditions.enableAsgs),
    enableDebugLogging,
    enableSchedulingHubAccount: trueCondition(stack, conditions.enableHubAcctScheduling),
    encryptionKey: key,
    factory: new TestFunctionFactory(),
    logRetentionDays,
    metricsEnv,
    namespace,
    regions,
    snsErrorReportingTopic: topic,
    solutionVersion,
  });

  return stack;
}
