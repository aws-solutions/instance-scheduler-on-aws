// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { CfnCondition, Duration, Fn } from "aws-cdk-lib";
import { Role, ServicePrincipal, Policy, PolicyStatement, Effect } from "aws-cdk-lib/aws-iam";
import { Function as LambdaFunction } from "aws-cdk-lib/aws-lambda";
import { CfnRule, Rule, Schedule } from "aws-cdk-lib/aws-events";
import { LambdaFunction as LambdaFunctionTarget } from "aws-cdk-lib/aws-events-targets";
import { Topic } from "aws-cdk-lib/aws-sns";
import { Key } from "aws-cdk-lib/aws-kms";
import { NagSuppressions } from "cdk-nag";
import { Construct } from "constructs";
import { AnonymizedMetricsEnvironment } from "../anonymized-metrics-environment";
import { cfnConditionToTrueFalse } from "../cfn";
import { FunctionFactory } from "./function-factory";
import { InstanceSchedulerDataLayer } from "../instance-scheduler-data-layer";
import { ISLogGroups } from "../observability/log-groups";

export interface HeartbeatMetricReporterProps {
  readonly description: string;
  readonly dataLayer: InstanceSchedulerDataLayer;
  readonly memorySizeMB: number;
  readonly snsErrorReportingTopic: Topic;
  readonly snsKmsKey: Key;
  readonly USER_AGENT_EXTRA: string;
  readonly metricsEnv: AnonymizedMetricsEnvironment;
  readonly factory: FunctionFactory;
  readonly schedulingEnabled: CfnCondition;
  readonly solutionVersion: string;
  readonly defaultTimezone: string;
  readonly enableRdsSnapshots: CfnCondition;
  readonly enableAwsOrganizations: CfnCondition;
  readonly enableEc2SsmMaintenanceWindows: CfnCondition;
  readonly enableOpsInsights: CfnCondition;
}

export class HeartbeatMetricReporter {
  readonly lambdaFunction: LambdaFunction;

  constructor(scope: Construct, props: HeartbeatMetricReporterProps) {
    const role = new Role(scope, "HeartbeatMetricsReporterRole", {
      assumedBy: new ServicePrincipal("lambda.amazonaws.com"),
    });

    this.lambdaFunction = props.factory.createFunction(scope, "HeartbeatMetricsReporter", {
      description: props.description,
      index: "instance_scheduler/handler/heartbeat_metrics_reporter.py",
      handler: "report_heartbeat_metric",
      memorySize: props.memorySizeMB,
      role: role,
      timeout: Duration.minutes(5),
      logGroup: ISLogGroups.adminLogGroup(scope),
      environment: {
        USER_AGENT_EXTRA: props.USER_AGENT_EXTRA,
        CONFIG_TABLE: props.dataLayer.configTable.tableName,
        REGISTRY_TABLE: props.dataLayer.registry.tableName,
        DEFAULT_TIMEZONE: props.defaultTimezone,
        ENABLE_RDS_SNAPSHOTS: cfnConditionToTrueFalse(props.enableRdsSnapshots),
        ENABLE_AWS_ORGANIZATIONS: cfnConditionToTrueFalse(props.enableAwsOrganizations),
        ENABLE_EC2_SSM_MAINTENANCE_WINDOWS: cfnConditionToTrueFalse(props.enableEc2SsmMaintenanceWindows),
        OPS_DASHBOARD_ENABLED: cfnConditionToTrueFalse(props.enableOpsInsights),
        ...props.metricsEnv,
      },
    });

    if (!this.lambdaFunction.role) {
      throw new Error("lambdaFunction role is missing");
    }

    const metricsPolicy = new Policy(scope, "MetricsGathererPermissionsPolicy", {
      roles: [this.lambdaFunction.role],
    });

    props.dataLayer.configTable.grantReadData(metricsPolicy);
    props.dataLayer.registry.grantReadData(metricsPolicy);
    ISLogGroups.adminLogGroup(scope).grantWrite(metricsPolicy);

    metricsPolicy.addStatements(
      new PolicyStatement({
        actions: ["kms:Decrypt", "kms:GenerateDataKey*"],
        effect: Effect.ALLOW,
        resources: [props.snsKmsKey.keyArn],
      }),
    );

    const metricsRule = new Rule(scope, "MetricsGathererEventRule", {
      description: `Instance Scheduler - Rule to trigger heartbeat metrics function version ${props.solutionVersion}`,
      schedule: Schedule.rate(Duration.hours(24)),
      targets: [
        new LambdaFunctionTarget(this.lambdaFunction, {
          retryAttempts: 1,
        }),
      ],
    });

    const cfnMetricsRule = metricsRule.node.defaultChild as CfnRule;
    cfnMetricsRule.addPropertyOverride(
      "State",
      Fn.conditionIf(props.schedulingEnabled.logicalId, "ENABLED", "DISABLED"),
    );

    const defaultPolicy = this.lambdaFunction.role.node.tryFindChild("DefaultPolicy");
    if (!defaultPolicy) {
      throw Error("Unable to find default policy on lambda role");
    }

    NagSuppressions.addResourceSuppressions(defaultPolicy, [
      {
        id: "AwsSolutions-IAM5",
        appliesTo: ["Resource::*"],
        reason: "required for xray",
      },
    ]);
  }
}
