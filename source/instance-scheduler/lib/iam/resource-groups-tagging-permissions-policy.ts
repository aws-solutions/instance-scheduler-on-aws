// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import { Effect, Policy, PolicyStatement } from "aws-cdk-lib/aws-iam";
import { Construct } from "constructs";

export class ResourceGroupsTaggingPermissionsPolicy extends Policy {
  constructor(scope: Construct, id: string) {
    super(scope, id);

    this.addStatements(
      new PolicyStatement({
        actions: ["tag:TagResources", "tag:UntagResources"],
        effect: Effect.ALLOW,
        resources: ["*"],
      }),
    );
  }
}
