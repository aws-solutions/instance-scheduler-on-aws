// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import * as events from "aws-cdk-lib/aws-events";
import * as cdk from "aws-cdk-lib";

export interface SchedulerEventBusProps {
  organizationId: string[];
  namespace: string;
  lambdaFunctionArn: string;
  eventBusName: string;
  isMemberOfOrganizationsCondition: cdk.CfnCondition;
}

export class SchedulerEventBusResources {
  readonly eventRuleCrossAccount: events.CfnRule;
  constructor(scope: cdk.Stack, props: SchedulerEventBusProps) {
    const schedulerEventBus = new events.CfnEventBus(scope, "scheduler-event-bus", {
      name: props.namespace + "-" + props.eventBusName,
    });

    const eventBusPolicy = new events.CfnEventBusPolicy(scope, "scheduler-event-bus-policy", {
      eventBusName: schedulerEventBus.attrName,
      statementId: schedulerEventBus.attrName,
      action: "events:PutEvents",
      principal: "*",
      condition: {
        type: "StringEquals",
        key: "aws:PrincipalOrgID",
        value: cdk.Fn.select(0, props.organizationId),
      },
    });

    this.eventRuleCrossAccount = new events.CfnRule(scope, "scheduler-ssm-parameter-cross-account-events", {
      description:
        "Event rule to invoke Instance Scheduler lambda function to store spoke account id(s) in configuration.",
      eventBusName: schedulerEventBus.attrName,
      state: "ENABLED",
      targets: [
        {
          arn: props.lambdaFunctionArn,
          id: "Scheduler-Lambda-Function",
        },
      ],
      eventPattern: {
        source: ["aws.ssm"],
        "detail-type": ["Parameter Store Change"],
        detail: {
          name: ["/instance-scheduler/do-not-delete-manually"],
          operation: ["Create", "Delete"],
          type: ["String"],
        },
      },
    });

    schedulerEventBus.cfnOptions.condition = props.isMemberOfOrganizationsCondition;
    eventBusPolicy.cfnOptions.condition = props.isMemberOfOrganizationsCondition;
    this.eventRuleCrossAccount.cfnOptions.condition = props.isMemberOfOrganizationsCondition;
  }
}
