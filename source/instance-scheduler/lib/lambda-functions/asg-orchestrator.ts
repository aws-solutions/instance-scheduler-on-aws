// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { CfnCondition, Duration, Fn, RemovalPolicy } from "aws-cdk-lib";
import { Table } from "aws-cdk-lib/aws-dynamodb";
import { Policy, Role, ServicePrincipal } from "aws-cdk-lib/aws-iam";
import { Key } from "aws-cdk-lib/aws-kms";
import { Function as LambdaFunction } from "aws-cdk-lib/aws-lambda";
import { LogGroup, RetentionDays } from "aws-cdk-lib/aws-logs";
import { Topic } from "aws-cdk-lib/aws-sns";
import { NagSuppressions } from "cdk-nag";
import { Construct } from "constructs";
import { AnonymizedMetricsEnvironment } from "../anonymized-metrics-environment";
import { cfnConditionToTrueFalse } from "../cfn";
import { addCfnNagSuppressions } from "../cfn-nag";
import { FunctionFactory } from "./function-factory";

export interface AsgOrchestratorProps {
  readonly USER_AGENT_EXTRA: string;
  readonly memorySizeMB: number;
  readonly asgHandler: LambdaFunction;
  readonly configTable: Table;
  readonly enableDebugLogging: CfnCondition;
  readonly enableSchedulingHubAccount: CfnCondition;
  readonly encryptionKey: Key;
  readonly factory: FunctionFactory;
  readonly logRetentionDays: RetentionDays;
  readonly metricsEnv: AnonymizedMetricsEnvironment;
  readonly regions: string[];
  readonly snsErrorReportingTopic: Topic;
}

export class AsgOrchestrator {
  readonly lambdaFunction: LambdaFunction;

  constructor(scope: Construct, props: AsgOrchestratorProps) {
    const role = new Role(scope, "ASGOrchRole", {
      assumedBy: new ServicePrincipal("lambda.amazonaws.com"),
    });

    this.lambdaFunction = props.factory.createFunction(scope, "ASGOrchestrator", {
      description: `Instance Scheduler orchestrator for AutoScaling Groups version ${props.metricsEnv.SOLUTION_VERSION}`,
      index: "instance_scheduler/handler/asg_orchestrator.py",
      handler: "lambda_handler",
      memorySize: props.memorySizeMB,
      role,
      timeout: Duration.minutes(1),
      environment: {
        USER_AGENT_EXTRA: props.USER_AGENT_EXTRA,
        CONFIG_TABLE: props.configTable.tableName,
        ISSUES_TOPIC_ARN: props.snsErrorReportingTopic.topicArn,
        ENABLE_SCHEDULE_HUB_ACCOUNT: cfnConditionToTrueFalse(props.enableSchedulingHubAccount),
        SCHEDULE_REGIONS: Fn.join(",", props.regions),
        ASG_SCHEDULER_NAME: props.asgHandler.functionName,
        POWERTOOLS_LOG_LEVEL: Fn.conditionIf(props.enableDebugLogging.logicalId, "DEBUG", "INFO").toString(),
        POWERTOOLS_SERVICE_NAME: "asg_orch",
        ...props.metricsEnv,
      },
    });

    const lambdaDefaultLogGroup = new LogGroup(scope, "ASGOrchLogGroup", {
      logGroupName: `/aws/lambda/${this.lambdaFunction.functionName}`,
      removalPolicy: RemovalPolicy.RETAIN,
      retention: props.logRetentionDays,
    });

    if (!this.lambdaFunction.role) {
      throw new Error("lambdaFunction role is missing");
    }

    const asgOrchPolicy = new Policy(scope, "ASGOrchPolicy", {
      roles: [this.lambdaFunction.role],
    });

    lambdaDefaultLogGroup.grantWrite(asgOrchPolicy);
    props.configTable.grantReadData(asgOrchPolicy);
    props.snsErrorReportingTopic.grantPublish(asgOrchPolicy);
    props.encryptionKey.grantEncryptDecrypt(asgOrchPolicy);
    props.asgHandler.grantInvoke(this.lambdaFunction.role);

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
        appliesTo: ["Resource::<ASGHandler0F6D6751.Arn>:*"],
        reason: "permissions to invoke all versions of the ASG scheduling request handler",
      },
    ]);

    NagSuppressions.addResourceSuppressions(asgOrchPolicy, [
      {
        id: "AwsSolutions-IAM5",
        appliesTo: ["Action::kms:GenerateDataKey*", "Action::kms:ReEncrypt*"],
        reason: "Permission to use solution CMK with dynamo/sns",
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
  }
}
