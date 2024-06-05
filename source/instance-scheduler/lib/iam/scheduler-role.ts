// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { IPrincipal, Role } from "aws-cdk-lib/aws-iam";
import { Construct } from "constructs";
import { Aspects, CfnCondition, Fn } from "aws-cdk-lib";
import { ConditionAspect } from "../cfn";
import { Ec2KmsPermissionsPolicy } from "./ec2-kms-permissions-policy";
import { SchedulingPermissionsPolicy } from "./scheduling-permissions-policy";
import { addCfnNagSuppressions } from "../cfn-nag";

export interface ScheduleRoleProps {
  assumedBy: IPrincipal;
  namespace: string;
  kmsKeys: string[];
}
export class SchedulerRole extends Role {
  static roleName(namespace: string) {
    return `${namespace}-Scheduler-Role`;
  }
  constructor(scope: Construct, id: string, props: ScheduleRoleProps) {
    super(scope, id, {
      assumedBy: props.assumedBy,
      roleName: SchedulerRole.roleName(props.namespace),
    });

    new SchedulingPermissionsPolicy(this, `SchedulingPermissions`).attachToRole(this);

    //optional KMS permissions
    const kmsCondition = new CfnCondition(this, "kmsAccessCondition", {
      expression: Fn.conditionNot(Fn.conditionEquals(Fn.select(0, props.kmsKeys), "")),
    });
    const kmsConditionAspect = new ConditionAspect(kmsCondition);
    const kmsAccess = new Ec2KmsPermissionsPolicy(this, `KmsPermissions`, props.kmsKeys);
    kmsAccess.attachToRole(this);
    Aspects.of(kmsAccess).add(kmsConditionAspect);

    addCfnNagSuppressions(this, {
      id: "W28",
      reason: "The role name is defined to allow cross account access from the hub account.",
    });
  }
}
