// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { Aws, CustomResource, Duration } from "aws-cdk-lib";
import { Effect, Policy, PolicyStatement, Role, ServicePrincipal } from "aws-cdk-lib/aws-iam";
import { NagSuppressions } from "cdk-nag";
import { Construct } from "constructs";
import { FunctionFactory } from "./function-factory";
import { InstanceSchedulerDataLayer } from "../instance-scheduler-data-layer";
import { ISLogGroups } from "../observability/log-groups";

export interface MetricsUuidGeneratorProps {
  readonly solutionName: string;
  readonly dataLayer: InstanceSchedulerDataLayer;
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
      handler: "lambda_handler",
      memorySize: 128,
      role: role,
      timeout: Duration.minutes(1),
      logGroup: ISLogGroups.adminLogGroup(scope),
      environment: {
        USER_AGENT_EXTRA: props.USER_AGENT_EXTRA,
        UUID_KEY: props.UUID_KEY,
        STACK_ID: props.STACK_ID,
      },
    });

    if (!lambdaResourceProvider.role) {
      throw new Error("lambdaFunction role is missing");
    }

    const metricsUuidPolicy = new Policy(scope, "MetricsUuidPermissionsPolicy", {
      roles: [lambdaResourceProvider.role],
    });

    ISLogGroups.adminLogGroup(scope).grantWrite(metricsUuidPolicy);
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
  }
}
