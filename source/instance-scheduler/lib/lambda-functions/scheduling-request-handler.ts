// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import { Aws, CfnCondition, Duration, RemovalPolicy, Stack } from "aws-cdk-lib";
import { Table } from "aws-cdk-lib/aws-dynamodb";
import { Effect, Policy, PolicyStatement, Role, ServicePrincipal } from "aws-cdk-lib/aws-iam";
import { Function as LambdaFunction } from "aws-cdk-lib/aws-lambda";
import { LogGroup, RetentionDays } from "aws-cdk-lib/aws-logs";
import { Topic } from "aws-cdk-lib/aws-sns";
import { NagSuppressions } from "cdk-nag";
import { AnonymizedMetricsEnvironment } from "../anonymized-metrics-environment";
import { cfnConditionToTrueFalse } from "../cfn";
import { addCfnNagSuppressions } from "../cfn-nag";
import { FunctionFactory } from "./function-factory";
import { Metrics } from "../dashboard/metrics";

export interface SchedulingRequestHandlerProps {
  readonly description: string;
  readonly namespace: string;
  readonly logRetentionDays: RetentionDays;
  readonly memorySizeMB: number;
  readonly configTable: Table;
  readonly stateTable: Table;
  readonly maintWindowTable: Table;
  readonly scheduleLogGroup: LogGroup;
  readonly snsErrorReportingTopic: Topic;
  readonly enableDebugLogging: CfnCondition;
  readonly metricsEnv: AnonymizedMetricsEnvironment;
  readonly startTags: string;
  readonly stopTags: string;
  readonly tagKey: string;
  readonly schedulerRoleName: string;
  readonly USER_AGENT_EXTRA: string;
  readonly STACK_NAME: string;
  readonly DEFAULT_TIMEZONE: string;
  readonly enableOpsMonitoring: CfnCondition;
  readonly enableEc2SsmMaintenanceWindows: CfnCondition;
  readonly enableRds: CfnCondition;
  readonly enableRdsClusters: CfnCondition;
  readonly enableNeptune: CfnCondition;
  readonly enableDocdb: CfnCondition;
  readonly enableRdsSnapshots: CfnCondition;
  readonly schedulingIntervalMinutes: number;
  readonly solutionName: string;
  readonly factory: FunctionFactory;
}

export class SchedulingRequestHandlerLambda {
  readonly lambdaFunction: LambdaFunction;

  static roleName(namespace: string) {
    return `${namespace}-SchedulingRequestHandler-Role`;
  }
  constructor(scope: Stack, props: SchedulingRequestHandlerProps) {
    const role = new Role(scope, "schedulingRequestHandlerRole", {
      roleName: SchedulingRequestHandlerLambda.roleName(props.namespace),
      assumedBy: new ServicePrincipal("lambda.amazonaws.com"),
    });

    this.lambdaFunction = props.factory.createFunction(scope, "schedulingRequestHandlerLambda", {
      description: props.description,
      index: "instance_scheduler/handler/scheduling_request.py",
      handler: "handle_scheduling_request",
      memorySize: props.memorySizeMB,
      role: role,
      timeout: Duration.minutes(5),
      environment: {
        CONFIG_TABLE: props.configTable.tableName,
        STATE_TABLE: props.stateTable.tableName,
        MAINT_WINDOW_TABLE: props.maintWindowTable.tableName,
        USER_AGENT_EXTRA: props.USER_AGENT_EXTRA,
        STACK_NAME: props.STACK_NAME,
        LOG_GROUP: props.scheduleLogGroup.logGroupName,
        ISSUES_TOPIC_ARN: props.snsErrorReportingTopic.topicArn,
        ENABLE_DEBUG_LOGS: cfnConditionToTrueFalse(props.enableDebugLogging),
        SCHEDULER_ROLE_NAME: props.schedulerRoleName,
        DEFAULT_TIMEZONE: props.DEFAULT_TIMEZONE,
        START_TAGS: props.startTags,
        STOP_TAGS: props.stopTags,
        SCHEDULE_TAG_KEY: props.tagKey,
        ENABLE_EC2_SSM_MAINTENANCE_WINDOWS: cfnConditionToTrueFalse(props.enableEc2SsmMaintenanceWindows),
        ENABLE_RDS_SERVICE: cfnConditionToTrueFalse(props.enableRds),
        ENABLE_RDS_CLUSTERS: cfnConditionToTrueFalse(props.enableRdsClusters),
        ENABLE_NEPTUNE_SERVICE: cfnConditionToTrueFalse(props.enableNeptune),
        ENABLE_DOCDB_SERVICE: cfnConditionToTrueFalse(props.enableDocdb),
        ENABLE_RDS_SNAPSHOTS: cfnConditionToTrueFalse(props.enableRdsSnapshots),
        ENABLE_OPS_MONITORING: cfnConditionToTrueFalse(props.enableOpsMonitoring),
        ...props.metricsEnv,
      },
    });

    const lambdaDefaultLogGroup = new LogGroup(scope, "schedulingRequestHandlerLogGroup", {
      logGroupName: `/aws/lambda/${this.lambdaFunction.functionName}`,
      removalPolicy: RemovalPolicy.RETAIN,
      retention: props.logRetentionDays,
    });

    if (!this.lambdaFunction.role) {
      throw new Error("lambdaFunction role is missing");
    }

    const schedulingRequestHandlerPolicy = new Policy(scope, "schedulingRequestHandlerPolicy", {
      roles: [this.lambdaFunction.role],
    });

    lambdaDefaultLogGroup.grantWrite(schedulingRequestHandlerPolicy);
    props.configTable.grantReadData(schedulingRequestHandlerPolicy);
    props.stateTable.grantReadWriteData(schedulingRequestHandlerPolicy);
    props.maintWindowTable.grantReadWriteData(schedulingRequestHandlerPolicy);
    props.snsErrorReportingTopic.grantPublish(schedulingRequestHandlerPolicy);
    props.scheduleLogGroup.grantWrite(schedulingRequestHandlerPolicy);

    schedulingRequestHandlerPolicy.addStatements(
      //assume scheduler role in hub/spoke accounts
      new PolicyStatement({
        actions: ["sts:AssumeRole"],
        effect: Effect.ALLOW,
        resources: [`arn:${Aws.PARTITION}:iam::*:role/${props.schedulerRoleName}`],
      }),

      // put metric data for ops dashboard metrics
      new PolicyStatement({
        actions: ["cloudwatch:PutMetricData"],
        effect: Effect.ALLOW,
        resources: ["*"],
        conditions: {
          StringEquals: {
            "cloudwatch:namespace": Metrics.metricNamespace,
          },
        },
      }),
    );

    const defaultPolicy = this.lambdaFunction.role.node.tryFindChild("DefaultPolicy");
    if (!defaultPolicy) {
      throw Error("Unable to find default policy on lambda role");
    }

    addCfnNagSuppressions(defaultPolicy, {
      id: "W12",
      reason: "Wildcard required for xray",
    });

    NagSuppressions.addResourceSuppressions(defaultPolicy, [
      {
        id: "AwsSolutions-IAM5",
        appliesTo: ["Resource::*"],
        reason: "required for xray",
      },
      {
        id: "AwsSolutions-IAM5",
        appliesTo: ["Resource::<SpokeRegistrationHandler923F17AC.Arn>:*"],
        reason: "ability to call spoke-registration handler",
      },
    ]);

    addCfnNagSuppressions(
      schedulingRequestHandlerPolicy,
      {
        id: "W12",
        reason: "cloudwatch:PutMetricData action requires wildcard",
      },
      {
        id: "W76",
        reason: "Acknowledged IAM policy document SPCM > 25",
      },
    );

    NagSuppressions.addResourceSuppressions(schedulingRequestHandlerPolicy, [
      {
        id: "AwsSolutions-IAM5",
        appliesTo: ["Action::kms:GenerateDataKey*", "Action::kms:ReEncrypt*"],
        reason: "Permission to use solution CMK with dynamo/sns",
      },
      {
        id: "AwsSolutions-IAM5",
        appliesTo: ["Resource::arn:<AWS::Partition>:iam::*:role/<Namespace>-Scheduler-Role"],
        reason: "This handler's primary purpose is to assume role into spoke accounts for scheduling purposes",
      },
      {
        id: "AwsSolutions-IAM5",
        appliesTo: ["Resource::*"],
        reason: "Ability to publish custom metrics to cloudwatch",
      },
    ]);

    addCfnNagSuppressions(
      this.lambdaFunction,
      {
        id: "W89",
        reason: "This Lambda function does not need to access any resource provisioned within a VPC.",
      },
      {
        id: "W58",
        reason: "This Lambda function has permission provided to write to CloudWatch logs using the iam roles.",
      },
      {
        id: "W92",
        reason: "Need to investigate appropriate ReservedConcurrentExecutions for this lambda",
      },
    );

    addCfnNagSuppressions(lambdaDefaultLogGroup, {
      id: "W84",
      reason:
        "This template has to be supported in gov cloud which doesn't yet have the feature to provide kms key id to cloudwatch log group",
    });

    addCfnNagSuppressions(role, {
      id: "W28",
      reason: "Explicit role name required for assumedBy arn principle in spoke stack",
    });
  }
}
