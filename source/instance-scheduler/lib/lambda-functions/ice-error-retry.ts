// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { Construct } from "constructs";
import { Aws, CfnCondition, Duration } from "aws-cdk-lib";
import { FunctionFactory } from "./function-factory";
import { InstanceSchedulerDataLayer } from "../instance-scheduler-data-layer";
import { Function as LambdaFunction } from "aws-cdk-lib/aws-lambda";
import { Effect, Policy, PolicyStatement, Role, ServicePrincipal } from "aws-cdk-lib/aws-iam";
import { SqsEventSource } from "aws-cdk-lib/aws-lambda-event-sources";
import { ISLogGroups } from "../observability/log-groups";
import { AnonymizedMetricsEnvironment } from "../anonymized-metrics-environment";
import { NagSuppressions } from "cdk-nag";
import { Queue, QueueEncryption } from "aws-cdk-lib/aws-sqs";
import { addCfnGuardSuppression } from "../helpers/cfn-guard";
import { KmsKeys } from "../helpers/kms";
import { EventBus } from "aws-cdk-lib/aws-events";

export interface IceErrorRetryProps {
  readonly description: string;
  readonly dataLayer: InstanceSchedulerDataLayer;
  readonly namespace: string;
  readonly tagKey: string;
  readonly schedulingIntervalMinutes: number;
  readonly metricsEnv: AnonymizedMetricsEnvironment;
  readonly schedulerRoleName: string;
  readonly userAgentExtra: string;
  readonly stackId: string;
  readonly stackName: string;
  readonly enableOpsMonitoring: CfnCondition;
  readonly solutionName: string;
  readonly asgScheduledRulesPrefix: string;
  readonly asgMetadataTagKey: string;
  readonly regionalEventBusName: string;
  readonly globalEventBus: EventBus;
  readonly factory: FunctionFactory;
}

export class IceErrorRetry extends Construct {
  readonly retryIceErrorLambda: LambdaFunction;
  readonly iceRetryQueue: Queue;

  static roleName(namespace: string) {
    return `${namespace}-IceErrorRetryHandler-Role`;
  }

  constructor(scope: Construct, id: string, props: IceErrorRetryProps) {
    super(scope, id);

    this.iceRetryQueue = new Queue(scope, "InstanceSchedulerIceRetryQueue", {
      encryptionMasterKey: KmsKeys.get(scope),
      visibilityTimeout: Duration.seconds(180),
      encryption: QueueEncryption.KMS,
      deadLetterQueue: {
        maxReceiveCount: 1,
        queue: new Queue(scope, "InstanceSchedulerIceRetryDLQueue", {
          encryption: QueueEncryption.KMS,
          encryptionMasterKey: KmsKeys.get(scope),
          enforceSSL: true,
        }),
      },
    });

    const iceErrorRetryLambdaRole = new Role(scope, "iceErrorRetryHandlerRole", {
      roleName: IceErrorRetry.roleName(props.namespace),
      assumedBy: new ServicePrincipal("lambda.amazonaws.com"),
    });

    addCfnGuardSuppression(iceErrorRetryLambdaRole, ["CFN_NO_EXPLICIT_RESOURCE_NAMES"]);

    this.retryIceErrorLambda = props.factory.createFunction(scope, "iceErrorRetryHandlerLambda", {
      description: props.description,
      index: "instance_scheduler/handler/ice_retry_handler.py",
      handler: "lambda_handler",
      memorySize: 128,
      role: iceErrorRetryLambdaRole,
      timeout: Duration.seconds(180),
      logGroup: ISLogGroups.schedulingLogGroup(scope),
      environment: {
        CONFIG_TABLE: props.dataLayer.configTable.tableName,
        REGISTRY_TABLE: props.dataLayer.registry.tableName,
        USER_AGENT_EXTRA: props.userAgentExtra,
        STACK_NAME: props.stackName,
        SCHEDULER_ROLE_NAME: props.schedulerRoleName,
        SCHEDULE_TAG_KEY: props.tagKey,
        ASG_SCHEDULED_RULES_PREFIX: props.asgScheduledRulesPrefix,
        ASG_METADATA_TAG_KEY: props.asgMetadataTagKey,
        LOCAL_EVENT_BUS_NAME: props.regionalEventBusName,
        GLOBAL_EVENT_BUS_NAME: props.globalEventBus.eventBusName,
        ...props.metricsEnv,
      },
    });

    if (!this.retryIceErrorLambda.role) {
      throw new Error("retry lambda function role is missing");
    }

    // Add SQS event source
    this.retryIceErrorLambda.addEventSource(
      new SqsEventSource(this.iceRetryQueue, {
        batchSize: 1,
      }),
    );

    const retryIceErrorHandlerPolicy = new Policy(scope, "retryIceErrorHandlerPolicy", {
      roles: [this.retryIceErrorLambda.role],
    });

    props.dataLayer.registry.grantReadWriteData(retryIceErrorHandlerPolicy);
    this.iceRetryQueue.grantConsumeMessages(retryIceErrorHandlerPolicy);
    props.globalEventBus.grantPutEventsTo(retryIceErrorHandlerPolicy);
    ISLogGroups.schedulingLogGroup(scope).grantWrite(retryIceErrorHandlerPolicy);

    retryIceErrorHandlerPolicy.addStatements(
      //assume scheduler role in hub/spoke accounts
      new PolicyStatement({
        actions: ["sts:AssumeRole"],
        effect: Effect.ALLOW,
        resources: [`arn:${Aws.PARTITION}:iam::*:role/${props.schedulerRoleName}`],
      }),
    );

    const defaultPolicy = this.retryIceErrorLambda.role.node.tryFindChild("DefaultPolicy");
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

    NagSuppressions.addResourceSuppressions(retryIceErrorHandlerPolicy, [
      {
        id: "AwsSolutions-IAM5",
        appliesTo: ["Action::kms:GenerateDataKey*", "Action::kms:ReEncrypt*"],
        reason: "Permission to use solution CMK with dynamo/sns",
      },
      {
        id: "AwsSolutions-IAM5",
        appliesTo: ["Resource::arn:<AWS::Partition>:iam::*:role/<Namespace>-Scheduler-Role"],
        reason:
          "This handler's primary purpose is to assume role into spoke accounts for retrying scheduling and modify instance attributes purposes",
      },
    ]);
  }
}
