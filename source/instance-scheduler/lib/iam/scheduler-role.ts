// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { IPrincipal, Policy, Role } from "aws-cdk-lib/aws-iam";
import { Construct } from "constructs";
import { Aspects, Aws, CfnCondition, Fn } from "aws-cdk-lib";
import { ConditionAspect } from "../cfn";
import { Ec2KmsPermissionsPolicy } from "./ec2-kms-permissions-policy";
import { RdsSchedulingPermissionsPolicy } from "./rds-scheduling-permissions-policy";
import { addCfnGuardSuppression } from "../helpers/cfn-guard";
import { AsgSchedulingPermissionsPolicy } from "./asg-scheduling-permissions-policy";
import { Ec2SchedulingPermissionsPolicy } from "./ec2-scheduling-permissions-policy";
import { ResourceGroupsTaggingPermissionsPolicy } from "./resource-groups-tagging-permissions-policy";
import { Ec2LmsPermissionsPolicy } from "./ec2-licence-manager-permissions-policy";
import { EventBusPermissionsPolicy } from "./events-bus-permissions-policy";

export interface ScheduleRoleProps {
  assumedBy: IPrincipal;
  namespace: string;
  kmsKeys: string[];
  licenseManagerArns: string[];
  regionalEventBusName: string;
}
export class SchedulerRole extends Role {
  readonly ec2Policy: Policy;
  readonly rdsPolicy: Policy;
  readonly asgPolicy: Policy;
  readonly resourceTaggingPolicy: Policy;

  static roleName(namespace: string) {
    return `${namespace}-Scheduler-Role`;
  }
  constructor(scope: Construct, id: string, props: ScheduleRoleProps) {
    super(scope, id, {
      assumedBy: props.assumedBy,
      roleName: SchedulerRole.roleName(props.namespace),
    });

    addCfnGuardSuppression(this, ["CFN_NO_EXPLICIT_RESOURCE_NAMES"]);
    this.ec2Policy = new Ec2SchedulingPermissionsPolicy(this, "Ec2SchedulingPermissions");
    this.rdsPolicy = new RdsSchedulingPermissionsPolicy(this, "RdsSchedulingPermissions");
    this.asgPolicy = new AsgSchedulingPermissionsPolicy(this, "ASGSchedulingPermissions");
    this.resourceTaggingPolicy = new ResourceGroupsTaggingPermissionsPolicy(this, "ResourceGroupsTaggingPermissions");

    this.ec2Policy.attachToRole(this);
    this.rdsPolicy.attachToRole(this);
    this.asgPolicy.attachToRole(this);
    this.resourceTaggingPolicy.attachToRole(this);

    new EventBusPermissionsPolicy(this, "RegionalEventBusPermissions", {
      eventBusArn: `arn:aws:events:*:${Aws.ACCOUNT_ID}:event-bus/${props.regionalEventBusName}`,
    }).attachToRole(this);

    //optional KMS permissions
    const kmsCondition = new CfnCondition(this, "kmsAccessCondition", {
      expression: Fn.conditionNot(Fn.conditionEquals(Fn.select(0, props.kmsKeys), "")),
    });
    const kmsConditionAspect = new ConditionAspect(kmsCondition);
    const kmsAccess = new Ec2KmsPermissionsPolicy(this, `KmsPermissions`, props.kmsKeys);
    kmsAccess.attachToRole(this);
    Aspects.of(kmsAccess).add(kmsConditionAspect);

    //optional License Manager permissions
    const lmCondition = new CfnCondition(this, "lmConditionAspect", {
      expression: Fn.conditionNot(Fn.conditionEquals(Fn.select(0, props.licenseManagerArns), "")),
    });
    const lmConditionAspect = new ConditionAspect(lmCondition);
    const lmAccess = new Ec2LmsPermissionsPolicy(this, `LicenceManagerPermissions`, props.licenseManagerArns);
    lmAccess.attachToRole(this);
    Aspects.of(lmAccess).add(lmConditionAspect);
  }
}
