// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import { Effect, Policy, PolicyStatement } from "aws-cdk-lib/aws-iam";
import { Construct } from "constructs";

export interface EventBusPermissionsPolicyProps {
  readonly eventBusArn: string;
}

export class EventBusPermissionsPolicy extends Policy {
  constructor(scope: Construct, id: string, props: EventBusPermissionsPolicyProps) {
    super(scope, id);

    this.addStatements(
      new PolicyStatement({
        actions: ["events:PutEvents"],
        effect: Effect.ALLOW,
        resources: [props.eventBusArn],
      }),
    );
  }
}
