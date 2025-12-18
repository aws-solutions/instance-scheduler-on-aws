// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import { Aws, CfnCondition, Duration, Stack } from "aws-cdk-lib";
import { Effect, Policy, PolicyStatement, Role, ServicePrincipal } from "aws-cdk-lib/aws-iam";
import { Function as LambdaFunction } from "aws-cdk-lib/aws-lambda";
import { NagSuppressions } from "cdk-nag";
import { AnonymizedMetricsEnvironment } from "../anonymized-metrics-environment";
import { cfnConditionToTrueFalse } from "../cfn";
import { FunctionFactory } from "./function-factory";
import { Metrics } from "../dashboard/metrics";
import { InstanceSchedulerDataLayer } from "../instance-scheduler-data-layer";
import { ISLogGroups } from "../observability/log-groups";
import { addCfnGuardSuppression } from "../helpers/cfn-guard";
import { Queue } from "aws-cdk-lib/aws-sqs";
import { EventBus } from "aws-cdk-lib/aws-events";

export interface SchedulingRequestHandlerProps {
  readonly description: string;
  readonly dataLayer: InstanceSchedulerDataLayer;
  readonly namespace: string;
  readonly memorySizeMB: number;
  readonly iceErrorRetryQueue: Queue;
  readonly metricsEnv: AnonymizedMetricsEnvironment;
  readonly tagKey: string;
  readonly schedulerRoleName: string;
  readonly USER_AGENT_EXTRA: string;
  readonly STACK_ID: string;
  readonly STACK_NAME: string;
  readonly DEFAULT_TIMEZONE: string;
  readonly enableOpsMonitoring: CfnCondition;
  readonly enableEc2SsmMaintenanceWindows: CfnCondition;
  readonly enableRdsSnapshots: CfnCondition;
  readonly schedulingIntervalMinutes: number;
  readonly solutionName: string;
  readonly asgScheduledRulesPrefix: string;
  readonly asgMetadataTagKey: string;
  readonly regionalEventBusName: string;
  readonly globalEventBus: EventBus;
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
    addCfnGuardSuppression(role, ["CFN_NO_EXPLICIT_RESOURCE_NAMES"]);

    this.lambdaFunction = props.factory.createFunction(scope, "schedulingRequestHandlerLambda", {
      description: props.description,
      index: "instance_scheduler/handler/scheduling_request.py",
      handler: "handle_scheduling_request",
      memorySize: props.memorySizeMB,
      role: role,
      timeout: Duration.minutes(5),
      logGroup: ISLogGroups.schedulingLogGroup(scope),
      environment: {
        CONFIG_TABLE: props.dataLayer.configTable.tableName,
        REGISTRY_TABLE: props.dataLayer.registry.tableName,
        MAINT_WINDOW_TABLE: props.dataLayer.mwTable.tableName,
        USER_AGENT_EXTRA: props.USER_AGENT_EXTRA,
        STACK_ID: props.STACK_ID,
        ICE_RETRY_SQS_URL: props.iceErrorRetryQueue.queueUrl,
        SCHEDULER_ROLE_NAME: props.schedulerRoleName,
        DEFAULT_TIMEZONE: props.DEFAULT_TIMEZONE,
        SCHEDULE_TAG_KEY: props.tagKey,
        ENABLE_EC2_SSM_MAINTENANCE_WINDOWS: cfnConditionToTrueFalse(props.enableEc2SsmMaintenanceWindows),
        ENABLE_RDS_SNAPSHOTS: cfnConditionToTrueFalse(props.enableRdsSnapshots),
        ENABLE_OPS_MONITORING: cfnConditionToTrueFalse(props.enableOpsMonitoring),
        LOCAL_EVENT_BUS_NAME: props.regionalEventBusName,
        GLOBAL_EVENT_BUS_NAME: props.globalEventBus.eventBusName,
        HUB_STACK_NAME: props.STACK_NAME,
        ASG_SCHEDULED_RULES_PREFIX: props.asgScheduledRulesPrefix,
        ASG_METADATA_TAG_KEY: props.asgMetadataTagKey,
        ...props.metricsEnv,
      },
    });

    if (!this.lambdaFunction.role) {
      throw new Error("lambdaFunction role is missing");
    }

    const schedulingRequestHandlerPolicy = new Policy(scope, "schedulingRequestHandlerPolicy", {
      roles: [this.lambdaFunction.role],
    });

    props.dataLayer.configTable.grantReadData(schedulingRequestHandlerPolicy);
    props.dataLayer.stateTable.grantReadWriteData(schedulingRequestHandlerPolicy);
    props.dataLayer.registry.grantReadWriteData(schedulingRequestHandlerPolicy);
    props.dataLayer.mwTable.grantReadWriteData(schedulingRequestHandlerPolicy);
    props.iceErrorRetryQueue.grantSendMessages(schedulingRequestHandlerPolicy);
    props.globalEventBus.grantPutEventsTo(schedulingRequestHandlerPolicy);
    ISLogGroups.schedulingLogGroup(scope).grantWrite(schedulingRequestHandlerPolicy);

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
  }
}
