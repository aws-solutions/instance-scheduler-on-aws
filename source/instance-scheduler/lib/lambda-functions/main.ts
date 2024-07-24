// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { Aws, CfnCondition, CustomResource, Duration, Stack } from "aws-cdk-lib";
import { Table } from "aws-cdk-lib/aws-dynamodb";
import { Effect, PolicyStatement, Role, ServicePrincipal } from "aws-cdk-lib/aws-iam";
import { Function as LambdaFunction } from "aws-cdk-lib/aws-lambda";
import { LogGroup, RetentionDays } from "aws-cdk-lib/aws-logs";
import { Topic } from "aws-cdk-lib/aws-sns";
import { NagSuppressions } from "cdk-nag";
import { cfnConditionToTrueFalse, overrideLogicalId } from "../cfn";
import { FunctionFactory } from "./function-factory";
import { addCfnNagSuppressions } from "../cfn-nag";
import { AnonymizedMetricsEnvironment } from "../anonymized-metrics-environment";

export interface MainLambdaProps {
  readonly DEFAULT_TIMEZONE: string;
  readonly USER_AGENT_EXTRA: string;
  readonly metricsEnv: AnonymizedMetricsEnvironment;
  readonly configTable: Table;
  readonly snsErrorReportingTopic: Topic;
  readonly schedulerLogGroup: LogGroup;
  readonly enableDebugLogging: CfnCondition;
  readonly enableAwsOrganizations: CfnCondition;
  readonly principals: string[];
  readonly logRetentionDays: RetentionDays;
  readonly factory: FunctionFactory;
}
export class MainLambda {
  /*
  For backwards compatibility with <1.5.x this function encapsulates the CFN, CLI, and ServiceSetup handlers
   */

  readonly lambdaFunction: LambdaFunction;

  constructor(scope: Stack, props: MainLambdaProps) {
    const role = new Role(scope, "MainLambdaRole", {
      assumedBy: new ServicePrincipal("lambda.amazonaws.com"),
    });

    const functionName = Aws.STACK_NAME + "-InstanceSchedulerMain";
    this.lambdaFunction = props.factory.createFunction(scope, "scheduler-lambda", {
      functionName: functionName,
      description: "EC2 and RDS instance scheduler, version " + props.metricsEnv.SOLUTION_VERSION,
      index: "instance_scheduler/main.py",
      handler: "lambda_handler",
      role: role,
      memorySize: 128,
      timeout: Duration.seconds(300),
      environment: {
        LOG_GROUP: props.schedulerLogGroup.logGroupName,
        ISSUES_TOPIC_ARN: props.snsErrorReportingTopic.topicArn,
        TRACE: cfnConditionToTrueFalse(props.enableDebugLogging),
        USER_AGENT_EXTRA: props.USER_AGENT_EXTRA,
        DEFAULT_TIMEZONE: props.DEFAULT_TIMEZONE,
        ENABLE_AWS_ORGANIZATIONS: cfnConditionToTrueFalse(props.enableAwsOrganizations),
        CONFIG_TABLE: props.configTable.tableName,
        ...props.metricsEnv,
      },
    });

    //backwards compatibility (<1.5.x) override
    overrideLogicalId(this.lambdaFunction, "Main");

    const customService = new CustomResource(scope, "ServiceSetup", {
      serviceToken: this.lambdaFunction.functionArn,
      resourceType: "Custom::ServiceSetup",
      properties: {
        timeout: 120,
        remote_account_ids: props.principals,
        log_retention_days: props.logRetentionDays,
      },
    });
    overrideLogicalId(customService, "SchedulerConfigHelper");
    customService.node.addDependency(props.schedulerLogGroup);

    if (!this.lambdaFunction.role) {
      throw new Error("lambdaFunction role is missing");
    }

    props.configTable.grantReadWriteData(this.lambdaFunction.role);
    props.schedulerLogGroup.grantWrite(this.lambdaFunction.role);
    props.snsErrorReportingTopic.grantPublish(this.lambdaFunction.role);

    // basic logging permissions and permission to modify retention policy
    // https://docs.aws.amazon.com/lambda/latest/operatorguide/access-logs.html
    this.lambdaFunction.role.addToPrincipalPolicy(
      new PolicyStatement({
        actions: ["logs:CreateLogGroup"],
        effect: Effect.ALLOW,
        resources: [`arn:${Aws.PARTITION}:logs:${Aws.REGION}:${Aws.ACCOUNT_ID}:*`],
      }),
    );

    // specifying the function in the following two statements directly creates a circular dependency
    // these should go into a separate policy, but custom resources need to be sure to depend on it
    this.lambdaFunction.role.addToPrincipalPolicy(
      new PolicyStatement({
        actions: ["logs:CreateLogStream", "logs:PutLogEvents", "logs:PutRetentionPolicy"],
        effect: Effect.ALLOW,
        resources: [
          `arn:${Aws.PARTITION}:logs:${Aws.REGION}:${Aws.ACCOUNT_ID}:log-group:/aws/lambda/${functionName}:*`,
        ],
      }),
    );

    const defaultPolicy = this.lambdaFunction.role.node.tryFindChild("DefaultPolicy");
    if (!defaultPolicy) {
      throw Error("Unable to find default policy on lambda role");
    }

    addCfnNagSuppressions(
      defaultPolicy,
      {
        id: "W12",
        reason: "Wildcard required for xray",
      },
      {
        id: "W76",
        reason: "Acknowledged IAM policy document SPCM > 25",
      },
    );

    NagSuppressions.addResourceSuppressions(defaultPolicy, [
      {
        id: "AwsSolutions-IAM5",
        appliesTo: ["Action::kms:GenerateDataKey*", "Action::kms:ReEncrypt*"],
        reason: "Permission to use solution CMK with dynamo/sns",
      },
      {
        id: "AwsSolutions-IAM5",
        appliesTo: ["Resource::*"],
        reason: "required for xray",
      },
      {
        id: "AwsSolutions-IAM5",
        appliesTo: ["Resource::arn:<AWS::Partition>:logs:<AWS::Region>:<AWS::AccountId>:*"],
        reason: "Permission to use the solution's custom log group",
      },
      {
        id: "AwsSolutions-IAM5",
        appliesTo: [
          "Resource::arn:<AWS::Partition>:logs:<AWS::Region>:<AWS::AccountId>:log-group:/aws/lambda/<AWS::StackName>-InstanceSchedulerMain:*",
        ],
        reason: "Permission to modify own log group retention policy",
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
  }
}
