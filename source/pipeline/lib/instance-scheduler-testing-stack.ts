// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { CfnCondition, CfnOutput, Fn, Stack } from "aws-cdk-lib";
import { Construct } from "constructs";
import { CoreScheduler } from "../../instance-scheduler/lib/core-scheduler";
import { InstanceSchedulerStackProps } from "../../instance-scheduler/lib/instance-scheduler-stack";
import { PythonFunctionFactory } from "../../instance-scheduler/lib/lambda-functions/function-factory";

export class InstanceSchedulerTestingStack extends Stack {
  readonly configTableArn: CfnOutput;
  readonly topicArn: CfnOutput;
  readonly schedulerRoleArn: CfnOutput;

  constructor(scope: Construct, id: string, props: InstanceSchedulerStackProps) {
    super(scope, id, props);

    const enabledCondition = new CfnCondition(this, "EnabledCondition", { expression: Fn.conditionEquals(true, true) });
    const disabledCondition = new CfnCondition(this, "DisabledCondition", {
      expression: Fn.conditionEquals(false, true),
    });

    const coreScheduler = new CoreScheduler(this, {
      solutionName: props.solutionName,
      solutionVersion: props.solutionVersion,
      solutionId: props.solutionId,
      memorySizeMB: 128,
      principals: [],
      logRetentionDays: 90,
      schedulingEnabled: enabledCondition,
      schedulingIntervalMinutes: 1,
      namespace: "e2etesting",
      sendAnonymizedMetrics: disabledCondition,
      enableDebugLogging: enabledCondition,
      tagKey: "Schedule",
      defaultTimezone: "UTC",
      enableEc2: enabledCondition,
      enableRds: enabledCondition,
      enableRdsClusters: enabledCondition,
      enableNeptune: enabledCondition,
      enableDocdb: enabledCondition,
      enableRdsSnapshots: enabledCondition,
      regions: [""], // must have a value or Fn::Join will error
      enableSchedulingHubAccount: enabledCondition,
      enableEc2SsmMaintenanceWindows: enabledCondition,
      startTags: "InstanceScheduler-LastAction=Started By {scheduler} {year}/{month}/{day} {hour}:{minute}{timezone}",
      stopTags: "InstanceScheduler-LastAction=Stopped By {scheduler} {year}/{month}/{day} {hour}:{minute}{timezone}",
      enableAwsOrganizations: disabledCondition,
      appregSolutionName: props.appregSolutionName,
      appregApplicationName: props.appregApplicationName,
      enableOpsInsights: enabledCondition,
      factory: new PythonFunctionFactory(),
      enableDdbDeletionProtection: disabledCondition,
      kmsKeyArns: ["*"],
      enableAsgs: enabledCondition,
      scheduledTagKey: "scheduled",
      rulePrefix: "is-",
    });

    this.configTableArn = new CfnOutput(this, "ConfigTableArn", { value: coreScheduler.configTable.tableArn });
    this.topicArn = new CfnOutput(this, "TopicArn", { value: coreScheduler.topic.topicArn });
    this.schedulerRoleArn = new CfnOutput(this, "SchedulerRoleArn", { value: coreScheduler.hubSchedulerRole.roleArn });
    new CfnOutput(this, "AsgOrchName", { value: coreScheduler.asgOrch.functionName });
  }
}
