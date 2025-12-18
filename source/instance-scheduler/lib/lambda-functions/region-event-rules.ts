// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import { Construct } from "constructs";
import { FunctionFactory } from "./function-factory";
import { Effect, Policy, PolicyStatement, Role, ServicePrincipal } from "aws-cdk-lib/aws-iam";
import { Aws, Duration } from "aws-cdk-lib";
import { TargetStack } from "../stack-types";
import { ISLogGroups } from "../observability/log-groups";
import { Function as LambdaFunction } from "aws-cdk-lib/aws-lambda";
import { addCfnGuardSuppression } from "../helpers/cfn-guard";

export interface RegionEventRulesCustomResourceProps {
  readonly hubAccountId: string;
  readonly namespace: string;
  readonly scheduleTagKey: string;
  readonly factory: FunctionFactory;
  readonly USER_AGENT_EXTRA: string;
  readonly taggingEventBusName: string;
  readonly regionalEventBusName: string;
  readonly version: string;
}

export class RegionEventRulesCustomResource {
  readonly regionalEventsCustomResourceLambda: LambdaFunction;
  readonly taggingEventRole: Role;
  readonly taggingEventBusArn: string;
  constructor(scope: Construct, id: string, props: RegionEventRulesCustomResourceProps) {
    const targetEventBusArn = `arn:${Aws.PARTITION}:events:${Aws.REGION}:${props.hubAccountId}:event-bus/${props.taggingEventBusName}`;
    const EVENT_RULE_NAME_PREFIX = "IS-Tagging";

    const role = new Role(scope, "CreateRegionalEventRulesLambdaRole", {
      assumedBy: new ServicePrincipal("lambda.amazonaws.com"),
    });

    const taggingEventRole = new Role(scope, "HubTagEventForwardingRole", {
      assumedBy: new ServicePrincipal("events.amazonaws.com"),
    });

    taggingEventRole.addToPolicy(
      new PolicyStatement({
        actions: ["events:PutEvents"],
        resources: [targetEventBusArn],
      }),
    );

    const lambdaCreateRegionalEventRuleLogGroup = ISLogGroups.adminLogGroup(scope, TargetStack.REMOTE);
    addCfnGuardSuppression(lambdaCreateRegionalEventRuleLogGroup, ["CLOUDWATCH_LOG_GROUP_ENCRYPTED"]);

    const lambdaFunction = props.factory.createFunction(scope, "CreateRegionalEventRulesLambda", {
      description: "Custom Resource for creating regional event rules for tagging resources.",
      index: "instance_scheduler/handler/create_region_event_rules_handler.py",
      handler: "lambda_handler",
      memorySize: 512,
      role: role,
      timeout: Duration.minutes(15),
      targetStack: TargetStack.REMOTE,
      logGroup: lambdaCreateRegionalEventRuleLogGroup,
      environment: {
        USER_AGENT_EXTRA: props.USER_AGENT_EXTRA,
        TAGGING_EVENT_RULE_ROLE_ARN: taggingEventRole.roleArn,
        TAGGING_EVENT_BUS_ARN: targetEventBusArn,
        EVENT_RULE_PREFIX: EVENT_RULE_NAME_PREFIX,
        VERSION: props.version,
        SCHEDULE_TAG_KEY: props.scheduleTagKey,
        REGIONAL_EVENT_BUS_NAME: props.regionalEventBusName,
      },
    });

    if (!lambdaFunction.role) {
      throw new Error("CreateRegionalEventRulesLambda function role is missing");
    }

    const rolePolicy = new Policy(scope, "CreateRegionalEventRulesPolicy", {
      roles: [lambdaFunction.role],
      statements: [
        new PolicyStatement({
          actions: ["events:DeleteRule", "events:PutTargets", "events:PutRule", "events:RemoveTargets"],
          resources: [`arn:aws:events:*:${Aws.ACCOUNT_ID}:rule/${EVENT_RULE_NAME_PREFIX}*`],
          effect: Effect.ALLOW,
        }),
        new PolicyStatement({
          actions: ["events:CreateEventBus", "events:DeleteEventBus"],
          resources: [`arn:aws:events:*:${Aws.ACCOUNT_ID}:event-bus/${props.regionalEventBusName}`],
          effect: Effect.ALLOW,
        }),
        new PolicyStatement({
          actions: ["events:ListRules", "events:DescribeRule"],
          resources: ["*"],
          effect: Effect.ALLOW,
        }),
        new PolicyStatement({
          actions: ["iam:PassRole"],
          resources: [taggingEventRole.roleArn],
          effect: Effect.ALLOW,
        }),
      ],
    });

    ISLogGroups.adminLogGroup(scope, TargetStack.REMOTE).grantWrite(rolePolicy);
    this.regionalEventsCustomResourceLambda = lambdaFunction;
    this.taggingEventRole = taggingEventRole;
    this.taggingEventBusArn = targetEventBusArn;
  }
}
