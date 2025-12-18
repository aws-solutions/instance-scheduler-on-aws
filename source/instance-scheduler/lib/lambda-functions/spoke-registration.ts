// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { Aws, CfnCondition, Duration, Fn, Stack } from "aws-cdk-lib";
import { Effect, Policy, PolicyStatement, Role, ServicePrincipal, CfnRole, CfnPolicy } from "aws-cdk-lib/aws-iam";
import { Function as LambdaFunction } from "aws-cdk-lib/aws-lambda";
import { NagSuppressions } from "cdk-nag";
import { FunctionFactory } from "./function-factory";
import { InstanceSchedulerDataLayer } from "../instance-scheduler-data-layer";
import { ISLogGroups } from "../observability/log-groups";
import { EventBus } from "aws-cdk-lib/aws-events";
import { SchedulerRole } from "../iam/scheduler-role";
import { RegionRegistrationCustomResource } from "./region-registration";
import { addCfnGuardSuppression, addCfnGuardSuppressionCfnResource } from "../helpers/cfn-guard";
import { updateSSMParams } from "../iam/ssm-params-region-registration-permission";

export interface SpokeRegistrationLambdaProps {
  readonly dataLayer: InstanceSchedulerDataLayer;
  readonly solutionVersion: string;
  readonly USER_AGENT_EXTRA: string;
  readonly schedulingIntervalMinutes: number;
  readonly scheduleTagKey: string;
  readonly asgRulePrefix: string;
  readonly asgMetadataTagKey: string;
  readonly localEventBusName: string;
  readonly globalEventBus: EventBus;
  readonly namespace: string;
  readonly enableAwsOrganizations: CfnCondition;
  readonly principals: string[];
  readonly factory: FunctionFactory;
  readonly ssmParamUpdateRoleName: string;
  readonly ssmParamPathName: string;
}
export class SpokeRegistrationLambda {
  static getFunctionName(namespace: string) {
    return `InstanceScheduler-${namespace}-SpokeRegistration`;
  }
  static roleName(namespace: string) {
    return `${namespace}-SpokeRegistrationHandler-Role`;
  }
  static roleNameForSpokeTemplateInvokeFunction(namespace: string) {
    return `${namespace}-SpokeRegistrationInvokeFunction-Role`;
  }

  readonly lambdaFunction: LambdaFunction;

  constructor(scope: Stack, props: SpokeRegistrationLambdaProps) {
    const role = new Role(scope, "SpokeRegistrationRole", {
      assumedBy: new ServicePrincipal("lambda.amazonaws.com"),
      roleName: SpokeRegistrationLambda.roleName(props.namespace),
    });
    addCfnGuardSuppression(role, ["CFN_NO_EXPLICIT_RESOURCE_NAMES"]);

    const functionName = SpokeRegistrationLambda.getFunctionName(props.namespace);

    this.lambdaFunction = props.factory.createFunction(scope, "SpokeRegistrationHandler", {
      functionName: functionName,
      description: "spoke account registration handler, version " + props.solutionVersion,
      index: "instance_scheduler/handler/spoke_registration.py",
      handler: "lambda_handler",
      memorySize: 512,
      logGroup: ISLogGroups.adminLogGroup(scope),
      role: role,
      timeout: Duration.minutes(15),
      environment: {
        USER_AGENT_EXTRA: props.USER_AGENT_EXTRA,
        CONFIG_TABLE: props.dataLayer.configTable.tableName,
        REGISTRY_TABLE: props.dataLayer.registry.tableName,
        SCHEDULER_ROLE_NAME: SchedulerRole.roleName(props.namespace),
        SCHEDULE_TAG_KEY: props.scheduleTagKey,
        HUB_STACK_NAME: Aws.STACK_NAME,
        SCHEDULING_INTERVAL_MINUTES: props.schedulingIntervalMinutes.toString(),
        ASG_SCHEDULED_RULES_PREFIX: props.asgRulePrefix,
        ASG_METADATA_TAG_KEY: props.asgMetadataTagKey,
        LOCAL_EVENT_BUS_NAME: props.localEventBusName,
        GLOBAL_EVENT_BUS_NAME: props.globalEventBus.eventBusName,
        SSM_PARAM_PATH_NAME: props.ssmParamPathName,
        SSM_PARAM_UPDATE_ROLE_NAME: props.ssmParamUpdateRoleName,
      },
    });

    if (!this.lambdaFunction.role) {
      throw new Error("lambdaFunction role is missing");
    }

    const spokeRegistrationPolicy = new Policy(scope, "SpokeRegistrationPolicy", {
      roles: [this.lambdaFunction.role],
      statements: [
        new PolicyStatement({
          actions: ["sts:AssumeRole"],
          effect: Effect.ALLOW,
          resources: [
            `arn:${Aws.PARTITION}:iam::*:role/${RegionRegistrationCustomResource.ssmParamUpdateRoleName(props.namespace)}`,
            `arn:${Aws.PARTITION}:iam::*:role/${SchedulerRole.roleName(props.namespace)}`,
          ],
        }),
        updateSSMParams(props.namespace),
      ],
    });

    props.dataLayer.configTable.grantReadData(spokeRegistrationPolicy);
    props.dataLayer.registry.grantReadWriteData(spokeRegistrationPolicy);
    props.globalEventBus.grantPutEventsTo(spokeRegistrationPolicy);
    ISLogGroups.adminLogGroup(scope).grantWrite(spokeRegistrationPolicy);

    const defaultPolicy = this.lambdaFunction.role.node.tryFindChild("DefaultPolicy");
    if (!defaultPolicy) {
      throw Error("Unable to find default policy on lambda role");
    }

    const isPrincipalsNotEmpty = new CfnCondition(scope, "isPrincipalsNotEmpty", {
      expression: Fn.conditionNot(
        new CfnCondition(scope, "isPrincipalsEmpty", {
          expression: Fn.conditionEquals(Fn.select(0, props.principals), ""),
        }),
      ),
    });

    // spoke account custom resource will use this role to invoke function to register account-regions.
    const spokeAccountInvokeFunctionRole = new CfnRole(scope, "SpokeAccountInvokeFunctionRole", {
      roleName: SpokeRegistrationLambda.roleNameForSpokeTemplateInvokeFunction(props.namespace),
      assumeRolePolicyDocument: Fn.conditionIf(
        props.enableAwsOrganizations.logicalId,
        {
          Version: "2012-10-17",
          Statement: [
            {
              Effect: "Allow",
              Principal: {
                AWS: "*",
              },
              Action: "sts:AssumeRole",
              Condition: {
                "ForAnyValue:StringEquals": {
                  "aws:PrincipalOrgID": Fn.select(0, props.principals),
                },
                ArnLike: {
                  "aws:PrincipalArn": `arn:aws:iam::*:role/${RegionRegistrationCustomResource.invokeFunctionRemoteRoleName(props.namespace)}`,
                },
              },
            },
          ],
        },
        {
          Version: "2012-10-17",
          Statement: [
            {
              Effect: "Allow",
              Principal: {
                AWS: props.principals,
              },
              Action: "sts:AssumeRole",
              Condition: {
                ArnLike: {
                  "aws:PrincipalArn": `arn:aws:iam::*:role/${RegionRegistrationCustomResource.invokeFunctionRemoteRoleName(props.namespace)}`,
                },
              },
            },
          ],
        },
      ),
    });

    spokeAccountInvokeFunctionRole.cfnOptions.condition = isPrincipalsNotEmpty;
    addCfnGuardSuppressionCfnResource(spokeAccountInvokeFunctionRole, ["CFN_NO_EXPLICIT_RESOURCE_NAMES"]);

    const spokeAccountInvokeFunctionPolicy = new Policy(scope, "SpokeAccountInvokeFunctionPolicy", {
      statements: [
        new PolicyStatement({
          actions: ["lambda:InvokeFunction"],
          effect: Effect.ALLOW,
          resources: [`arn:${Aws.PARTITION}:lambda:${Aws.REGION}:${Aws.ACCOUNT_ID}:function:${functionName}`],
        }),
      ],
    });
    spokeAccountInvokeFunctionPolicy.attachToRole(
      Role.fromRoleArn(scope, "SpokeAccountInvokeFunctionRoleRef", spokeAccountInvokeFunctionRole.attrArn),
    );
    spokeAccountInvokeFunctionPolicy.node.addDependency(spokeAccountInvokeFunctionRole);
    const spokeAccountInvokeFunctionPolicyCfnPolicy = spokeAccountInvokeFunctionPolicy.node.defaultChild as CfnPolicy;
    spokeAccountInvokeFunctionPolicyCfnPolicy.cfnOptions.condition = isPrincipalsNotEmpty;

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
    ]);
  }
}
