// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { IPrincipal, Role } from "aws-cdk-lib/aws-iam";
import { Construct } from "constructs";
import { addCfnNagSuppressions } from "../cfn-nag";
import { AsgSchedulingPermissionsPolicy } from "./asg-scheduling-permissions-policy";

export interface AsgSchedulingRoleProps {
  assumedBy: IPrincipal;
  namespace: string;
}
export class AsgSchedulingRole extends Role {
  static roleName(namespace: string) {
    return `${namespace}-ASG-Scheduling-Role`;
  }
  constructor(scope: Construct, id: string, props: AsgSchedulingRoleProps) {
    super(scope, id, {
      assumedBy: props.assumedBy,
      roleName: AsgSchedulingRole.roleName(props.namespace),
    });

    new AsgSchedulingPermissionsPolicy(this, `ASGSchedulingPermissions`).attachToRole(this);

    addCfnNagSuppressions(this, {
      id: "W28",
      reason: "The role name is defined to allow cross account access from the hub account.",
    });
  }
}
