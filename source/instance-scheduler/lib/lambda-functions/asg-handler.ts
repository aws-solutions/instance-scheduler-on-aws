// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { Aws, CfnCondition, Duration, Fn, RemovalPolicy } from "aws-cdk-lib";
import { Table } from "aws-cdk-lib/aws-dynamodb";
import { Effect, IRole, Policy, PolicyStatement, Role, ServicePrincipal } from "aws-cdk-lib/aws-iam";
import { Key } from "aws-cdk-lib/aws-kms";
import { Function as LambdaFunction } from "aws-cdk-lib/aws-lambda";
import { LogGroup, RetentionDays } from "aws-cdk-lib/aws-logs";
import { Topic } from "aws-cdk-lib/aws-sns";
import { NagSuppressions } from "cdk-nag";
import { Construct } from "constructs";
import { AnonymizedMetricsEnvironment } from "../anonymized-metrics-environment";
import { addCfnNagSuppressions } from "../cfn-nag";
import { FunctionFactory } from "./function-factory";

export interface AsgHandlerProps {
  readonly DEFAULT_TIMEZONE: string;
  readonly USER_AGENT_EXTRA: string;
  readonly asgSchedulingRoleName: string;
  readonly configTable: Table;
  readonly encryptionKey: Key;
  readonly enableDebugLogging: CfnCondition;
  readonly factory: FunctionFactory;
  readonly logRetentionDays: RetentionDays;
  readonly metricsEnv: AnonymizedMetricsEnvironment;
  readonly namespace: string;
  readonly rulePrefix: string;
  readonly scheduledTagKey: string;
  readonly snsErrorReportingTopic: Topic;
  readonly tagKey: string;
  readonly memorySizeMB: number;
}

export class AsgHandler {
  readonly role: IRole;
  readonly lambdaFunction: LambdaFunction;

  static roleName(namespace: string) {
    return `${namespace}-AsgRequestHandler-Role`;
  }

  constructor(scope: Construct, props: AsgHandlerProps) {
    this.role = new Role(scope, "ASGRole", {
      assumedBy: new ServicePrincipal("lambda.amazonaws.com"),
      roleName: AsgHandler.roleName(props.namespace),
    });

    this.lambdaFunction = props.factory.createFunction(scope, "ASGHandler", {
      description: `Instance Scheduler for AutoScaling Groups version ${props.metricsEnv.SOLUTION_VERSION}`,
      index: "instance_scheduler/handler/asg.py",
      handler: "lambda_handler",
      memorySize: props.memorySizeMB,
      role: this.role,
      timeout: Duration.minutes(5),
      environment: {
        CONFIG_TABLE: props.configTable.tableName,
        USER_AGENT_EXTRA: props.USER_AGENT_EXTRA,
        ISSUES_TOPIC_ARN: props.snsErrorReportingTopic.topicArn,
        POWERTOOLS_LOG_LEVEL: Fn.conditionIf(props.enableDebugLogging.logicalId, "DEBUG", "INFO").toString(),
        POWERTOOLS_SERVICE_NAME: "asg",
        ASG_SCHEDULING_ROLE_NAME: props.asgSchedulingRoleName,
        DEFAULT_TIMEZONE: props.DEFAULT_TIMEZONE,
        SCHEDULE_TAG_KEY: props.tagKey,
        SCHEDULED_TAG_KEY: props.scheduledTagKey,
        RULE_PREFIX: props.rulePrefix,
        ...props.metricsEnv,
      },
    });

    const lambdaDefaultLogGroup = new LogGroup(scope, "ASGHandlerLogGroup", {
      logGroupName: `/aws/lambda/${this.lambdaFunction.functionName}`,
      removalPolicy: RemovalPolicy.RETAIN,
      retention: props.logRetentionDays,
    });

    if (!this.lambdaFunction.role) {
      throw new Error("lambdaFunction role is missing");
    }

    const schedulingRequestHandlerPolicy = new Policy(scope, "ASGPolicy", {
      roles: [this.lambdaFunction.role],
    });

    lambdaDefaultLogGroup.grantWrite(schedulingRequestHandlerPolicy);
    props.configTable.grantReadData(schedulingRequestHandlerPolicy);
    props.snsErrorReportingTopic.grantPublish(schedulingRequestHandlerPolicy);
    props.encryptionKey.grantEncryptDecrypt(schedulingRequestHandlerPolicy);

    schedulingRequestHandlerPolicy.addStatements(
      new PolicyStatement({
        actions: ["sts:AssumeRole"],
        effect: Effect.ALLOW,
        resources: [`arn:${Aws.PARTITION}:iam::*:role/${props.asgSchedulingRoleName}`],
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
    ]);

    addCfnNagSuppressions(schedulingRequestHandlerPolicy, {
      id: "W76",
      reason: "Acknowledged IAM policy document SPCM > 25",
    });

    NagSuppressions.addResourceSuppressions(schedulingRequestHandlerPolicy, [
      {
        id: "AwsSolutions-IAM5",
        appliesTo: ["Action::kms:GenerateDataKey*", "Action::kms:ReEncrypt*"],
        reason: "Permission to use solution CMK with dynamo/sns",
      },
      {
        id: "AwsSolutions-IAM5",
        appliesTo: ["Resource::arn:<AWS::Partition>:iam::*:role/<Namespace>-ASG-Scheduling-Role"],
        reason: "This handler's primary purpose is to assume role into spoke accounts for scheduling purposes",
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

    addCfnNagSuppressions(this.role, {
      id: "W28",
      reason: "Explicit role name required for assumedBy arn principle in spoke stack",
    });
  }
}
