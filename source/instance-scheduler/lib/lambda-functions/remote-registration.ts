// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  Aspects,
  Aws,
  CfnCondition,
  CustomResource,
  Duration,
  CfnWaitConditionHandle,
  RemovalPolicy,
} from "aws-cdk-lib";
import { Effect, Policy, PolicyStatement, Role, ServicePrincipal } from "aws-cdk-lib/aws-iam";
import { NagSuppressions } from "cdk-nag";
import { FunctionFactory } from "./function-factory";
import { SpokeRegistrationLambda } from "./spoke-registration";
import { Construct } from "constructs";
import { ConditionAspect } from "../cfn";
import { LogGroup, RetentionDays } from "aws-cdk-lib/aws-logs";
import { addCfnNagSuppressions } from "../cfn-nag";

export interface RemoteRegistrationCustomResourceProps {
  readonly hubAccountId: string;
  readonly namespace: string;
  readonly shouldRegisterSpokeAccountCondition: CfnCondition;
  readonly factory: FunctionFactory;
  readonly USER_AGENT_EXTRA: string;
}

export class RemoteRegistrationCustomResource {
  constructor(scope: Construct, id: string, props: RemoteRegistrationCustomResourceProps) {
    const shouldRegisterSpokeAccountAspect = new ConditionAspect(props.shouldRegisterSpokeAccountCondition);

    const role = new Role(scope, "RegisterSpokeAccountCustomResourceLambdaRole", {
      assumedBy: new ServicePrincipal("lambda.amazonaws.com"),
    });
    Aspects.of(role).add(shouldRegisterSpokeAccountAspect);

    const hubRegistrationLambdaArn = `arn:${Aws.PARTITION}:lambda:${Aws.REGION}:${
      props.hubAccountId
    }:function:${SpokeRegistrationLambda.getFunctionName(props.namespace)}`;

    const lambdaFunction = props.factory.createFunction(scope, "RegisterSpokeAccountCustomResourceLambda", {
      description: "Custom Resource Provider used for spoke account self registration via aws organization",
      index: "instance_scheduler/handler/remote_registration_custom_resource.py",
      handler: "handle_remote_registration_request",
      memorySize: 128,
      role: role,
      timeout: Duration.minutes(1),
      environment: {
        USER_AGENT_EXTRA: props.USER_AGENT_EXTRA,
        HUB_REGISTRATION_LAMBDA_ARN: hubRegistrationLambdaArn,
      },
    });
    Aspects.of(lambdaFunction).add(shouldRegisterSpokeAccountAspect);

    const policy = new Policy(scope, "RegisterSpokeAccountCustomResourceLambdaPolicy", {
      roles: [role],
      statements: [
        new PolicyStatement({
          actions: ["lambda:InvokeFunction"],
          resources: [hubRegistrationLambdaArn],
          effect: Effect.ALLOW,
        }),
      ],
    });
    Aspects.of(policy).add(shouldRegisterSpokeAccountAspect);

    // Retention set to ONE_YEAR to not introduce new CfnParameters.
    // Logs are for custom resource lambda and will rarely be generated.
    const lambdaDefaultLogGroup = new LogGroup(scope, "SpokeRegistrationLogGroup", {
      logGroupName: `/aws/lambda/${lambdaFunction.functionName}`,
      removalPolicy: RemovalPolicy.RETAIN,
      retention: RetentionDays.ONE_YEAR,
    });
    Aspects.of(lambdaDefaultLogGroup).add(shouldRegisterSpokeAccountAspect);
    lambdaDefaultLogGroup.grantWrite(policy);

    const registerSpokeAccountCustomResource = new CustomResource(scope, id, {
      serviceToken: lambdaFunction.functionArn,
      resourceType: "Custom::RegisterSpokeAccount",
    });
    Aspects.of(registerSpokeAccountCustomResource).add(shouldRegisterSpokeAccountAspect);

    // CfnWaitConditionHandle adds some time between the policy and custom resource creation as the addDependency method is potentially unreliable here.
    const waitConditionHandle = new CfnWaitConditionHandle(
      scope,
      "RegisterSpokeAccountCustomResourceLambdaPolicyWaiter",
    );
    Aspects.of(waitConditionHandle).add(shouldRegisterSpokeAccountAspect);
    registerSpokeAccountCustomResource.node.addDependency(waitConditionHandle);
    waitConditionHandle.node.addDependency(policy);

    const defaultPolicy = role.node.tryFindChild("DefaultPolicy");
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

    addCfnNagSuppressions(
      lambdaFunction,
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

    NagSuppressions.addResourceSuppressions(lambdaFunction, [
      {
        id: "AwsSolutions-L1",
        reason: "Python 3.11 is the newest available runtime. This finding is a false positive.",
      },
    ]);

    addCfnNagSuppressions(lambdaDefaultLogGroup, {
      id: "W84",
      reason:
        "This template has to be supported in gov cloud which doesn't yet have the feature to provide kms key id to cloudwatch log group",
    });
  }
}
