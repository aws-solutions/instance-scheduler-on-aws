// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { Aws, Duration } from "aws-cdk-lib";
import { Effect, Policy, PolicyStatement, Role, ServicePrincipal } from "aws-cdk-lib/aws-iam";
import { Function as LambdaFunction } from "aws-cdk-lib/aws-lambda";
import { NagSuppressions } from "cdk-nag";
import { Construct } from "constructs";
import { FunctionFactory } from "./function-factory";
import { InstanceSchedulerDataLayer } from "../instance-scheduler-data-layer";
import { ISLogGroups } from "../observability/log-groups";

export interface SchedulingOrchestratorProps {
  readonly description: string;
  readonly dataLayer: InstanceSchedulerDataLayer;
  readonly schedulingRequestHandlerLambda: LambdaFunction;
  readonly USER_AGENT_EXTRA: string;
  readonly factory: FunctionFactory;
  readonly memorySizeMB: number;
}

export class SchedulingOrchestrator {
  readonly lambdaFunction: LambdaFunction;

  constructor(scope: Construct, props: SchedulingOrchestratorProps) {
    const role = new Role(scope, "SchedulingOrchestratorRole", {
      assumedBy: new ServicePrincipal("lambda.amazonaws.com"),
    });

    this.lambdaFunction = props.factory.createFunction(scope, "SchedulingOrchestrator", {
      description: props.description,
      index: "instance_scheduler/handler/scheduling_orchestrator.py",
      handler: "lambda_handler",
      memorySize: props.memorySizeMB,
      role: role,
      timeout: Duration.minutes(5),
      logGroup: ISLogGroups.schedulingLogGroup(scope),
      environment: {
        USER_AGENT_EXTRA: props.USER_AGENT_EXTRA,
        CONFIG_TABLE: props.dataLayer.configTable.tableName,
        REGISTRY_TABLE: props.dataLayer.registry.tableName,
        SCHEDULING_REQUEST_HANDLER_NAME: props.schedulingRequestHandlerLambda.functionName,
      },
    });
    if (!this.lambdaFunction.role) {
      throw new Error("lambdaFunction role is missing");
    }

    const orchestratorPolicy = new Policy(scope, "SchedulingOrchestratorPermissionsPolicy", {
      roles: [this.lambdaFunction.role],
    });

    //invoke must be applied to the base lambda role, not a policy
    props.schedulingRequestHandlerLambda.grantInvoke(this.lambdaFunction.role);

    props.dataLayer.configTable.grantReadData(orchestratorPolicy);
    props.dataLayer.registry.grantReadData(orchestratorPolicy);
    ISLogGroups.schedulingLogGroup(scope).grantWrite(orchestratorPolicy);

    orchestratorPolicy.addStatements(
      new PolicyStatement({ actions: ["ssm:DescribeParameters"], effect: Effect.ALLOW, resources: ["*"] }),
    );

    orchestratorPolicy.addStatements(
      new PolicyStatement({
        actions: ["ssm:GetParameter", "ssm:GetParameters"],
        effect: Effect.ALLOW,
        resources: [`arn:${Aws.PARTITION}:ssm:*:${Aws.ACCOUNT_ID}:parameter/*`],
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
        appliesTo: ["Resource::<schedulingRequestHandlerLambdaC395DC9E.Arn>:*"],
        reason: "permission to invoke request handler lambda",
      },
    ]);

    NagSuppressions.addResourceSuppressions(orchestratorPolicy, [
      {
        id: "AwsSolutions-IAM5",
        appliesTo: ["Action::kms:GenerateDataKey*", "Action::kms:ReEncrypt*"],
        reason: "Permission to use solution CMK with dynamo/sns",
      },
      {
        id: "AwsSolutions-IAM5",
        appliesTo: ["Resource::arn:<AWS::Partition>:ssm:*:<AWS::AccountId>:parameter/*", "Resource::*"],
        reason:
          "Orchestrator requires access to SSM parameters for translating " +
          "{param: my-param} values to configured account ids",
      },
    ]);
  }
}
