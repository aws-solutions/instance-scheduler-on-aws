// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { App, Stack } from "aws-cdk-lib";
import { Template } from "aws-cdk-lib/assertions";
import { trueCondition } from "../../lib/cfn";
import { CoreScheduler } from "../../lib/core-scheduler";
import { TestFunctionFactory } from "../../lib/lambda-functions/function-factory";
import { InstanceSchedulerDataLayer } from "../../lib/instance-scheduler-data-layer";
import { InstanceSchedulerStack } from "../../lib/instance-scheduler-stack";
import { RetentionDays } from "aws-cdk-lib/aws-logs";
import { AnonymizedMetricsEnvironment } from "../../lib/anonymized-metrics-environment";

export const solutionName = "my-solution-name";
export const solutionVersion = "v9.9.9";
export const solutionId = "my-solution-id";
export const memorySizeMB = 128;
export const principals: string[] = [];
export const schedulingIntervalMinutes = 5;
export const namespace = "prod";
export const stackName = "TestStack";
export const tagKey = "my-tag-key";
export const defaultTimezone = "my-timezone";
export const regions = ["us-east-1", "us-west-2"];
export const scheduledTagKey = "scheduled";
export const rulePrefix = "is-";
export const metricsEnv: AnonymizedMetricsEnvironment = {
  SEND_METRICS: "True",
  METRICS_URL: "https://example.com",
  SOLUTION_ID: solutionId,
  SOLUTION_VERSION: solutionVersion,
  SCHEDULING_INTERVAL_MINUTES: schedulingIntervalMinutes.toString(),
  METRICS_UUID: "metrics-uuid",
  HUB_ACCOUNT_ID: "123456789012",
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

export function findResourceWithPartialId(template: Template, resourceType: string, partialId: string) {
  const resources = template.findResources(resourceType);
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
export function mockCoreScheduler(): Template {
  const stack = new Stack(new App(), "TestStack", {
    stackName,
  });

  initializeInstanceSchedulerStackClass(stack);

  new CoreScheduler(stack, {
    solutionName,
    solutionVersion,
    solutionId,
    memorySizeMB,
    orchestratorMemorySizeMB: 128,
    principals,
    schedulingEnabled: trueCondition(stack, conditions.schedulingEnabled),
    schedulingIntervalMinutes,
    namespace,
    sendAnonymizedMetrics: trueCondition(stack, conditions.sendMetrics),
    tagKey,
    defaultTimezone,
    enableRdsSnapshots: trueCondition(stack, conditions.enableRdsSnapshots),
    regions,
    enableEc2SsmMaintenanceWindows: trueCondition(stack, conditions.enableEc2MaintWindows),
    enableAwsOrganizations: trueCondition(stack, conditions.enableAwsOrgs),
    enableOpsInsights: trueCondition(stack, conditions.deployOpsInsightsDashboard),
    kmsKeyArns: ["*"],
    licenseManagerArns: [
      "arn:aws:license-manager:us-west-2:111122223333:license-configuration:lic-1acd1326f60740b63daf8ac62d8aa9ce",
    ],
    factory: new TestFunctionFactory(),
    asgMetadataTagKey: scheduledTagKey,
    rulePrefix,
  });

  return Template.fromStack(stack);
}

export function mockDataLayer(scope: Stack) {
  return new InstanceSchedulerDataLayer(scope);
}

export function initializeInstanceSchedulerStackClass(stack: Stack) {
  InstanceSchedulerStack.sharedConfig = {
    retainDataAndLogsCondition: trueCondition(stack, conditions.enableDdbDeletionProtection),
    enableDebugLoggingCondition: trueCondition(stack, conditions.enableDebugLogging),
    logRetentionDays: RetentionDays.ONE_WEEK,
    namespace: namespace,
  };
}
