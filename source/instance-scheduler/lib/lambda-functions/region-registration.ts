// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import { Construct } from "constructs";
import { FunctionFactory } from "./function-factory";
import {
  ArnPrincipal,
  CfnRole,
  Effect,
  Policy,
  PolicyDocument,
  PolicyStatement,
  Role,
  ServicePrincipal,
} from "aws-cdk-lib/aws-iam";
import { Aws, CfnCondition, Duration, Fn } from "aws-cdk-lib";
import { TargetStack } from "../stack-types";
import { ISLogGroups } from "../observability/log-groups";
import { Provider } from "aws-cdk-lib/custom-resources";
import { roleArnFor } from "../iam/roles";
import { SpokeRegistrationLambda } from "./spoke-registration";
import { getSSMParams, describeSSMParams, updateSSMParams } from "../iam/ssm-params-region-registration-permission";
import { addCfnGuardSuppression } from "../helpers/cfn-guard";

export interface RegionRegistrationCustomResourceProps {
  readonly hubAccountId: string;
  readonly namespace: string;
  readonly factory: FunctionFactory;
  readonly USER_AGENT_EXTRA: string;
  readonly version: string;
  readonly targetStack: TargetStack;
  readonly hubRegisterRegionRoleName: string;
  readonly hubRegisterRegionFunctionName: string;
}

export class RegionRegistrationCustomResource {
  readonly regionRegistrationCustomResourceProvider: Provider;
  readonly spokeRegistrationUpdateSSMParamRoleCfnResource: CfnRole;
  readonly regionRegistrationCustomResourceLambdaRoleCfnResource: CfnRole;
  readonly regionRegistrationWaitLambdaRoleCfnResource: CfnRole;

  static ssmParamPathName(namespace: string) {
    return `/IS/${namespace}/regions`;
  }

  static ssmParamUpdateRoleName(namespace: string) {
    return `${namespace}-SpokeRegistrationUpdateSSMParamRole`;
  }

  static invokeFunctionRemoteRoleName(namespace: string) {
    return `${namespace}-InvokeHubFunctionRemoteRole`;
  }

  static functionArnFor(functionName: string, accountId: string) {
    return `arn:aws:lambda:${Aws.REGION}:${accountId}:function:${functionName}`;
  }

  constructor(scope: Construct, id: string, props: RegionRegistrationCustomResourceProps) {
    const isNotHubStackDeployment = new CfnCondition(scope, "isNotHubStackDeployment", {
      expression: Fn.conditionEquals(TargetStack.REMOTE, props.targetStack),
    });

    const isHubStackDeployment = new CfnCondition(scope, "isHubStackDeployment", {
      expression: Fn.conditionEquals(TargetStack.HUB, props.targetStack),
    });

    const regionRegistrationCustomResourceLambdaRole = new Role(scope, "RegionRegistrationLambdaRole", {
      assumedBy: new ServicePrincipal("lambda.amazonaws.com"),
      roleName: RegionRegistrationCustomResource.invokeFunctionRemoteRoleName(props.namespace),
      inlinePolicies: {
        SpokeRegistrationUpdateSSMParamPolicy: new PolicyDocument({
          statements: [getSSMParams(props.namespace), describeSSMParams(), updateSSMParams(props.namespace)],
        }),
      },
    });
    addCfnGuardSuppression(regionRegistrationCustomResourceLambdaRole, [
      "CFN_NO_EXPLICIT_RESOURCE_NAMES",
      "IAM_NO_INLINE_POLICY_CHECK",
      "IAM_POLICYDOCUMENT_NO_WILDCARD_RESOURCE",
    ]);

    const regionRegistrationWaitLambdaRole = new Role(scope, "RegionRegistrationWaitingLambdaRole", {
      assumedBy: new ServicePrincipal("lambda.amazonaws.com"),
      inlinePolicies: {
        RegionRegistrationWaitLambdaPolicy: new PolicyDocument({
          statements: [getSSMParams(props.namespace), describeSSMParams(), updateSSMParams(props.namespace)],
        }),
      },
    });

    addCfnGuardSuppression(regionRegistrationWaitLambdaRole, [
      "IAM_NO_INLINE_POLICY_CHECK",
      "IAM_POLICYDOCUMENT_NO_WILDCARD_RESOURCE",
    ]);

    const spokeRegistrationUpdateSSMParamRole = new Role(scope, "SpokeRegistrationUpdateSSMParamRole", {
      roleName: RegionRegistrationCustomResource.ssmParamUpdateRoleName(props.namespace),
      assumedBy: new ArnPrincipal(roleArnFor(props.hubAccountId, SpokeRegistrationLambda.roleName(props.namespace))),
      inlinePolicies: {
        SpokeRegistrationUpdateSSMParamPolicy: new PolicyDocument({
          statements: [getSSMParams(props.namespace), describeSSMParams(), updateSSMParams(props.namespace)],
        }),
      },
    });

    addCfnGuardSuppression(spokeRegistrationUpdateSSMParamRole, [
      "CFN_NO_EXPLICIT_RESOURCE_NAMES",
      "IAM_NO_INLINE_POLICY_CHECK",
      "IAM_POLICYDOCUMENT_NO_WILDCARD_RESOURCE",
    ]);

    const spokeRegistrationUpdateSSMParamRoleCfnResource = spokeRegistrationUpdateSSMParamRole.node
      .defaultChild as CfnRole;
    spokeRegistrationUpdateSSMParamRoleCfnResource.cfnOptions.condition = isNotHubStackDeployment;
    this.spokeRegistrationUpdateSSMParamRoleCfnResource = spokeRegistrationUpdateSSMParamRoleCfnResource;

    const lambdaDefaultLogGroup = ISLogGroups.adminLogGroup(scope, props.targetStack);

    const regionRegistrationCustomResourceLambda = props.factory.createFunction(
      scope,
      "RegionRegistrationCustomResourceLambda",
      {
        description: "Custom Resource Provider used for region registration",
        index: "instance_scheduler/handler/region_registration_events_handler.py",
        handler: "lambda_handler",
        memorySize: 512,
        role: regionRegistrationCustomResourceLambdaRole,
        timeout: Duration.minutes(15),
        targetStack: props.targetStack,
        logGroup: lambdaDefaultLogGroup,
        environment: {
          USER_AGENT_EXTRA: props.USER_AGENT_EXTRA,
          HUB_ACCOUNT_ID: props.hubAccountId,
          STACK_ID: Aws.STACK_ID,
          SSM_PARAM_PATH: RegionRegistrationCustomResource.ssmParamPathName(props.namespace),
          HUB_REGISTRATION_FUNCTION_ARN: RegionRegistrationCustomResource.functionArnFor(
            props.hubRegisterRegionFunctionName,
            props.hubAccountId,
          ),
          HUB_REGISTRATION_ROLE_NAME: SpokeRegistrationLambda.roleNameForSpokeTemplateInvokeFunction(props.namespace),
        },
      },
    );

    const regionRegistrationWaitLambda = props.factory.createFunction(scope, "RegionRegistrationWaitLambda", {
      description: "Custom Resource lambda to wait and confirm region registrations.",
      index: "instance_scheduler/handler/region_registration_events_iscomplete_handler.py",
      handler: "lambda_handler",
      memorySize: 512,
      role: regionRegistrationWaitLambdaRole,
      timeout: Duration.minutes(15),
      targetStack: props.targetStack,
      logGroup: lambdaDefaultLogGroup,
      environment: {
        USER_AGENT_EXTRA: props.USER_AGENT_EXTRA,
        HUB_ACCOUNT_ID: props.hubAccountId,
        STACK_ID: Aws.STACK_ID,
        SSM_PARAM_PATH: RegionRegistrationCustomResource.ssmParamPathName(props.namespace),
        HUB_REGISTRATION_FUNCTION_ARN: RegionRegistrationCustomResource.functionArnFor(
          props.hubRegisterRegionFunctionName,
          props.hubAccountId,
        ),
        HUB_REGISTRATION_ROLE_NAME: SpokeRegistrationLambda.roleNameForSpokeTemplateInvokeFunction(props.namespace),
      },
    });

    const provider = new Provider(scope, "CustomResourceProvider", {
      onEventHandler: regionRegistrationCustomResourceLambda,
      isCompleteHandler: regionRegistrationWaitLambda,
      totalTimeout: Duration.minutes(20),
      queryInterval: Duration.seconds(30),
    });

    provider.node.children.forEach((child) => {
      if (
        child.node.id == "framework-onEvent" ||
        child.node.id == "framework-isComplete" ||
        child.node.id == "framework-onTimeout"
      ) {
        addCfnGuardSuppression(child, ["LAMBDA_INSIDE_VPC", "LAMBDA_CONCURRENCY_CHECK"]);
      }
    });

    const regionRegistrationCustomResourceLambdaPolicy = new Policy(
      scope,
      "RegionRegistrationCustomResourceLambdaPolicy",
      {
        roles: [regionRegistrationCustomResourceLambdaRole],
        statements: [
          new PolicyStatement({
            actions: ["sts:AssumeRole"],
            effect: Effect.ALLOW,
            resources: [
              roleArnFor(
                props.hubAccountId,
                SpokeRegistrationLambda.roleNameForSpokeTemplateInvokeFunction(props.namespace),
              ),
            ],
          }),
        ],
      },
    );

    const regionRegistrationCustomResourceLambdaPolicyCfnResource = regionRegistrationCustomResourceLambdaPolicy.node
      .defaultChild as CfnRole;
    regionRegistrationCustomResourceLambdaPolicyCfnResource.cfnOptions.condition = isNotHubStackDeployment;

    const hubLambdaInvokePolicy = new Policy(scope, "hubLambdaInvokePolicy", {
      roles: [regionRegistrationCustomResourceLambdaRole],
      statements: [
        new PolicyStatement({
          actions: ["lambda:InvokeFunction"],
          effect: Effect.ALLOW,
          resources: [
            RegionRegistrationCustomResource.functionArnFor(props.hubRegisterRegionFunctionName, props.hubAccountId),
          ],
        }),
      ],
    });

    const hubLambdaInvokePolicyCfnResource = hubLambdaInvokePolicy.node.defaultChild as CfnRole;
    hubLambdaInvokePolicyCfnResource.cfnOptions.condition = isHubStackDeployment;

    const regionRegistrationCustomResourceLambdaRoleCfnResource = regionRegistrationCustomResourceLambdaRole.node
      .defaultChild as CfnRole;
    this.regionRegistrationCustomResourceLambdaRoleCfnResource = regionRegistrationCustomResourceLambdaRoleCfnResource;

    const regionRegistrationWaitLambdaRoleCfnResource = regionRegistrationWaitLambdaRole.node.defaultChild as CfnRole;
    this.regionRegistrationWaitLambdaRoleCfnResource = regionRegistrationWaitLambdaRoleCfnResource;

    lambdaDefaultLogGroup.grantWrite(regionRegistrationCustomResourceLambdaPolicy);
    lambdaDefaultLogGroup.grantWrite(regionRegistrationWaitLambdaRole);

    this.regionRegistrationCustomResourceProvider = provider;
  }
}
