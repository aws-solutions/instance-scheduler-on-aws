// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { Effect, Policy, PolicyStatement } from "aws-cdk-lib/aws-iam";
import { Construct } from "constructs";

export class Ec2LmsPermissionsPolicy extends Policy {
  constructor(scope: Construct, id: string, LmsKeyArns: string[]) {
    super(scope, id);

    this.addStatements(
      new PolicyStatement({
        actions: ["ec2:StartInstances"],
        resources: LmsKeyArns,
        effect: Effect.ALLOW,
      }),
    );
  }
}
