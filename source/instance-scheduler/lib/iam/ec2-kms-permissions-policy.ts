// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { Effect, Policy, PolicyStatement } from "aws-cdk-lib/aws-iam";
import { Construct } from "constructs";
import { NagSuppressions } from "cdk-nag";
export class Ec2KmsPermissionsPolicy extends Policy {
  constructor(scope: Construct, id: string, kmsKeyArns: string[]) {
    super(scope, id);

    this.addStatements(
      new PolicyStatement({
        actions: ["kms:CreateGrant"],
        resources: kmsKeyArns,
        effect: Effect.ALLOW,
        conditions: {
          Bool: {
            "kms:GrantIsForAWSResource": true,
          },
          StringLike: {
            "kms:ViaService": "ec2.*.amazonaws.com",
          },
          "ForAllValues:StringEquals": {
            "kms:GrantOperations": ["Decrypt"],
            "kms:EncryptionContextKeys": ["aws:ebs:id"],
          },
          Null: {
            "kms:EncryptionContextKeys": false,
            "kms:GrantOperations": false,
          },
        },
      }),
    );

    NagSuppressions.addResourceSuppressions(this, [
      {
        id: "AwsSolutions-IAM5",
        appliesTo: ["Resource::*"],
        reason:
          "Specific kms keys are unknown until runtime, for security, access is instead restricted to only granting decryption" +
          " permissions to the ec2 service for encrypted EBS volumes",
      },
    ]);
  }
}
