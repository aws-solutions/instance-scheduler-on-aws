// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { ArnFormat, Aspects, CfnCondition, Duration, Fn, Stack } from "aws-cdk-lib";
import { Table } from "aws-cdk-lib/aws-dynamodb";
import { Effect, Policy, PolicyStatement, Role, ServicePrincipal } from "aws-cdk-lib/aws-iam";
import { CfnPermission, Function as LambdaFunction } from "aws-cdk-lib/aws-lambda";
import { LogGroup, RetentionDays } from "aws-cdk-lib/aws-logs";
import { Topic } from "aws-cdk-lib/aws-sns";
import { NagSuppressions } from "cdk-nag";
import { ConditionAspect, cfnConditionToTrueFalse } from "../cfn";
import { addCfnNagSuppressions } from "../cfn-nag";
import { FunctionFactory } from "./function-factory";
import { SpokeDeregistrationRunbook } from "../runbooks/spoke-deregistration";

export interface SpokeRegistrationLambdaProps {
  readonly solutionVersion: string;
  readonly logRetentionDays: RetentionDays;
  readonly configTable: Table;
  readonly snsErrorReportingTopic: Topic;
  readonly scheduleLogGroup: LogGroup;
  readonly USER_AGENT_EXTRA: string;
  readonly enableDebugLogging: CfnCondition;
  readonly principals: string[];
  readonly namespace: string;
  readonly enableAwsOrganizations: CfnCondition;
  readonly factory: FunctionFactory;
}
export class SpokeRegistrationLambda {
  static getFunctionName(namespace: string) {
    return `InstanceScheduler-${namespace}-SpokeRegistration`;
  }
  readonly lambdaFunction: LambdaFunction;

  constructor(scope: Stack, props: SpokeRegistrationLambdaProps) {
    const role = new Role(scope, "SpokeRegistrationRole", {
      assumedBy: new ServicePrincipal("lambda.amazonaws.com"),
    });

    const functionName = SpokeRegistrationLambda.getFunctionName(props.namespace);

    this.lambdaFunction = props.factory.createFunction(scope, "SpokeRegistrationHandler", {
      functionName: functionName,
      description: "spoke account registration handler, version " + props.solutionVersion,
      index: "instance_scheduler/handler/spoke_registration.py",
      handler: "handle_spoke_registration_event",
      memorySize: 128,
      role: role,
      timeout: Duration.minutes(1),
      environment: {
        CONFIG_TABLE: props.configTable.tableName,
        USER_AGENT_EXTRA: props.USER_AGENT_EXTRA,
        LOG_GROUP: props.scheduleLogGroup.logGroupName,
        ISSUES_TOPIC_ARN: props.snsErrorReportingTopic.topicArn,
        ENABLE_DEBUG_LOGS: cfnConditionToTrueFalse(props.enableDebugLogging),
      },
    });

    if (!this.lambdaFunction.role) {
      throw new Error("lambdaFunction role is missing");
    }

    // GovCloud and GCR regions do not support logging config property which was used to prevent
    // log group name collisions since the lambda name must be well known.
    // To work around this a lambda-managed log group and appropriate policy must be used to prevent name collisions.
    // Thus, log retention cannot be set until these regions reach feature parity.
    const spokeRegistrationPolicy = new Policy(scope, "SpokeRegistrationPolicy", {
      roles: [this.lambdaFunction.role],
      statements: [
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: ["logs:CreateLogGroup"],
          resources: [
            scope.formatArn({
              service: "logs",
              resource: "log-group",
              resourceName: `/aws/lambda/${functionName}:*`,
              arnFormat: ArnFormat.COLON_RESOURCE_NAME,
            }),
          ],
        }),
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: ["logs:CreateLogStream", "logs:PutLogEvents"],
          resources: [
            scope.formatArn({
              service: "logs",
              resource: "log-group",
              resourceName: `/aws/lambda/${functionName}:log-stream:*`,
              arnFormat: ArnFormat.COLON_RESOURCE_NAME,
            }),
          ],
        }),
      ],
    });

    props.configTable.grantReadWriteData(spokeRegistrationPolicy);
    props.snsErrorReportingTopic.grantPublish(spokeRegistrationPolicy);
    props.scheduleLogGroup.grantWrite(spokeRegistrationPolicy);

    // Must use the L1 construct to conditionally create the resource based permission.
    const permission = new CfnPermission(scope, "SpokeRegistrationLambdaCrossAccountPermission", {
      functionName: this.lambdaFunction.functionName,
      principal: "*",
      principalOrgId: Fn.select(0, props.principals),
      action: "lambda:InvokeFunction",
    });
    Aspects.of(permission).add(new ConditionAspect(props.enableAwsOrganizations));

    new SpokeDeregistrationRunbook(scope, {
      lambdaFunction: this.lambdaFunction,
      namespace: props.namespace,
    });

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

    NagSuppressions.addResourceSuppressions(spokeRegistrationPolicy, [
      {
        id: "AwsSolutions-IAM5",
        appliesTo: ["Action::kms:GenerateDataKey*", "Action::kms:ReEncrypt*"],
        reason: "Permission to use solution CMK with dynamo/sns",
      },
      {
        id: "AwsSolutions-IAM5",
        appliesTo: [
          "Resource::arn:<AWS::Partition>:logs:<AWS::Region>:<AWS::AccountId>:log-group:/aws/lambda/InstanceScheduler-<Namespace>-SpokeRegistration:*",
          "Resource::arn:<AWS::Partition>:logs:<AWS::Region>:<AWS::AccountId>:log-group:/aws/lambda/InstanceScheduler-<Namespace>-SpokeRegistration:log-stream:*",
        ],
        reason: "Wildcard required for creating and writing to log group and stream",
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
        reason:
          "Lambda function is invoke by new account registration/deregistration events and is not likely to have much concurrency",
      },
      {
        id: "F13",
        reason:
          "This lambda scopes invoke permissions to members of the same AWS organization. This is the narrowest possible" +
          " scope that still allows new spoke accounts to register themselves with the hub after being deployed",
      },
    );

    // This L1 resource does not work with the addCfnNagSuppressions helper function
    permission.addMetadata("cfn_nag", {
      rules_to_suppress: [
        {
          id: "F13",
          reason:
            "Lambda permission policy requires principal wildcard for spoke accounts to self register by invoking this function." +
            "This is acceptable as we are narrowing the authorized accounts to only those contained within the org via principalOrgId",
        },
      ],
    });
  }
}
