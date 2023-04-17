// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import { Construct } from "constructs";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import { NagSuppressions } from "cdk-nag";

const testVpcs = new Map<Construct, ec2.Vpc>();

/**
 * create a default testVPC for a given scope
 * <p>
 *   if a vpc has already been defined for this scope, it will be returned instead of creating a new one
 * </p>
 */
export function defaultTestVPC(scope: Construct): ec2.Vpc {
  if (!testVpcs.has(scope)) {
    testVpcs.set(scope, createNewVpcInScope(scope));
  }

  // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
  return testVpcs.get(scope)!;
}

function createNewVpcInScope(scope: Construct) {
  const vpc = new ec2.Vpc(scope, "basic-test-vpc", {
    natGateways: 0,
    ipAddresses: ec2.IpAddresses.cidr("10.0.0.0/16"),
    subnetConfiguration: [
      {
        cidrMask: 24,
        name: "ingress",
        subnetType: ec2.SubnetType.PUBLIC,
      },
      {
        cidrMask: 24,
        name: "application",
        subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
      },
      {
        cidrMask: 28,
        name: "rds",
        subnetType: ec2.SubnetType.PRIVATE_ISOLATED,
      },
    ],
  });

  NagSuppressions.addResourceSuppressions(vpc, [
    {
      id: "AwsSolutions-VPC7",
      reason: "The VPC  is for test instances that only ever need to be started/stopped (no traffic)",
    },
  ]);

  return vpc;
}
