// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { Aws, CustomResource, Duration, RemovalPolicy } from "aws-cdk-lib";
import { Effect, Policy, PolicyStatement, Role, ServicePrincipal } from "aws-cdk-lib/aws-iam";
import { LogGroup, RetentionDays } from "aws-cdk-lib/aws-logs";
import { NagSuppressions } from "cdk-nag";
import { Construct } from "constructs";
import { addCfnNagSuppressions } from "../cfn-nag";
import { FunctionFactory } from "./function-factory";

export interface MetricsUuidGeneratorProps {
  readonly solutionName: string;
  readonly logRetentionDays: RetentionDays;
  readonly USER_AGENT_EXTRA: string;
  readonly UUID_KEY: string;
  readonly STACK_ID: string;
  readonly factory: FunctionFactory;
}
export class MetricsUuidGenerator {
  readonly metricsUuidCustomResource: CustomResource;
  readonly metricsUuid: string;

  constructor(scope: Construct, props: MetricsUuidGeneratorProps) {
    //todo: ensure custom resource depends on the policy that provides logging access
    const role = new Role(scope, "MetricsGeneratorRole", {
      assumedBy: new ServicePrincipal("lambda.amazonaws.com"),
    });

    const lambdaResourceProvider = props.factory.createFunction(scope, "MetricsUuidGenerator", {
      description: "Custom Resource Provider used to generate unique UUIDs for solution deployments",
      index: "instance_scheduler/handler/metrics_uuid_custom_resource.py",
      handler: "handle_metrics_uuid_request",
      memorySize: 128,
      role: role,
      timeout: Duration.minutes(1),
      environment: {
        USER_AGENT_EXTRA: props.USER_AGENT_EXTRA,
        UUID_KEY: props.UUID_KEY,
        STACK_ID: props.STACK_ID,
      },
    });

    const lambdaDefaultLogGroup = new LogGroup(scope, "MetricsUuidHandlerLogGroup", {
      logGroupName: `/aws/lambda/${lambdaResourceProvider.functionName}`,
      removalPolicy: RemovalPolicy.RETAIN,
      retention: props.logRetentionDays,
    });

    if (!lambdaResourceProvider.role) {
      throw new Error("lambdaFunction role is missing");
    }

    const metricsUuidPolicy = new Policy(scope, "MetricsUuidPermissionsPolicy", {
      roles: [lambdaResourceProvider.role],
    });

    lambdaDefaultLogGroup.grantWrite(metricsUuidPolicy);
    metricsUuidPolicy.addStatements(
      new PolicyStatement({
        actions: ["ssm:GetParameters", "ssm:GetParameter", "ssm:GetParameterHistory"],
        effect: Effect.ALLOW,
        resources: [
          `arn:${Aws.PARTITION}:ssm:${Aws.REGION}:${Aws.ACCOUNT_ID}:parameter/Solutions/${props.solutionName}/UUID/*`,
        ],
      }),
    );

    // CUSTOM RESOURCE
    this.metricsUuidCustomResource = new CustomResource(scope, "MetricsUuidProvider", {
      serviceToken: lambdaResourceProvider.functionArn,
      resourceType: "Custom::MetricsUuid",
    });

    //permissions policy must be applied before custom resource can be invoked
    this.metricsUuidCustomResource.node.addDependency(metricsUuidPolicy);
    this.metricsUuid = this.metricsUuidCustomResource.getAttString("Uuid");

    const defaultPolicy = lambdaResourceProvider.role.node.tryFindChild("DefaultPolicy");
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

    NagSuppressions.addResourceSuppressions(metricsUuidPolicy, [
      {
        id: "AwsSolutions-IAM5",
        appliesTo: [
          "Resource::arn:<AWS::Partition>:ssm:<AWS::Region>:<AWS::AccountId>:parameter/Solutions/instance-scheduler-on-aws/UUID/*",
        ],
        reason: "backwards compatibility (<=1.5.3) -- ability to read metrics UUID from ssm parameter",
      },
    ]);

    addCfnNagSuppressions(
      lambdaResourceProvider,
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
        reason: "Lambda function is a custom resource. Concurrent calls are very limited.",
      },
    );

    addCfnNagSuppressions(lambdaDefaultLogGroup, {
      id: "W84",
      reason:
        "This template has to be supported in gov cloud which doesn't yet have the feature to provide kms key id to cloudwatch log group",
    });
  }
}
