// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import { Stack } from "aws-cdk-lib";
import { LogGroup, RetentionDays } from "aws-cdk-lib/aws-logs";
import { Construct } from "constructs";
import { KmsKeys } from "../helpers/kms";
import { addCfnGuardSuppression } from "../helpers/cfn-guard";
import { cfnConditionToValue, overrideRetentionPolicies } from "../cfn";
import { InstanceSchedulerStack } from "../instance-scheduler-stack";
import { ServicePrincipal } from "aws-cdk-lib/aws-iam";
import { TargetStack } from "../stack-types";
import { SpokeStack } from "../remote-stack";

export class ISLogGroups {
  private static logGroups: { [key: string]: LogGroup } = {};
  public static adminLogGroup(scope: Construct, targetStack: TargetStack = TargetStack.HUB): LogGroup {
    const stack = Stack.of(scope);
    const logGroupId = `${stack.stackName}-AdminLogGroup`;
    if (!ISLogGroups.logGroups[logGroupId]) {
      const logGroup = ISLogGroups.createLogGroup(stack, {
        logicalName: "AdministrationLogs",
        logGroupName: "administrative-logs",
        targetStack: targetStack,
      });
      ISLogGroups.logGroups[logGroupId] = logGroup;
    }
    return ISLogGroups.logGroups[logGroupId]!;
  }

  public static schedulingLogGroup(scope: Construct): LogGroup {
    const stack = Stack.of(scope);
    const logGroupId = `${stack.stackName}-SchedulingLogGroup`;
    if (!ISLogGroups.logGroups[logGroupId]) {
      const logGroup = ISLogGroups.createLogGroup(stack, {
        logicalName: "SchedulingLogs",
        logGroupName: "scheduling-logs",
      });
      ISLogGroups.logGroups[logGroupId] = logGroup;
    }
    return ISLogGroups.logGroups[logGroupId]!;
  }

  // the remote stack doesn't have parameters for log retention and removal policy
  // no CMK either as each key costs $1 per stack instance per month in addition to usage cost
  public static remoteLogGroup(scope: Construct): LogGroup {
    const stack = Stack.of(scope);
    const logGroupId = `${stack.stackName}-SpokeRegistrationLogGroup`;
    if (!ISLogGroups.logGroups[logGroupId]) {
      const logGroup = ISLogGroups.createLogGroup(stack, {
        logicalName: "SpokeRegistrationLogs",
        logGroupName: "spoke-registration-logs",
        targetStack: TargetStack.REMOTE,
      });
      addCfnGuardSuppression(logGroup, ["CLOUDWATCH_LOG_GROUP_ENCRYPTED"]);
      ISLogGroups.logGroups[logGroupId] = logGroup;
    }
    return ISLogGroups.logGroups[logGroupId]!;
  }

  private static createLogGroup(
    stack: Stack,
    props: {
      logicalName: string;
      logGroupName: string;
      targetStack?: TargetStack;
    },
  ): LogGroup {
    const remoteStack = props.targetStack === TargetStack.REMOTE;
    const kmsKey = remoteStack ? undefined : KmsKeys.get(stack);
    const namespace = remoteStack ? SpokeStack.sharedConfig.namespace : InstanceSchedulerStack.sharedConfig.namespace;
    kmsKey && kmsKey.grantEncryptDecrypt(new ServicePrincipal("logs.amazonaws.com"));
    const logGroup = new LogGroup(stack, props.logicalName, {
      logGroupName: `${stack.stackName}-${namespace}-${props.logGroupName}`,
      encryptionKey: kmsKey,
      retention: remoteStack ? RetentionDays.ONE_YEAR : InstanceSchedulerStack.sharedConfig.logRetentionDays,
    });
    overrideRetentionPolicies(
      logGroup,
      remoteStack
        ? "Retain"
        : cfnConditionToValue(InstanceSchedulerStack.sharedConfig.retainDataAndLogsCondition, "Retain", "Delete"),
    );
    addCfnGuardSuppression(logGroup, ["CW_LOGGROUP_RETENTION_PERIOD_CHECK"]); // Retention period is defined in CfnMapping and evades the CFN Guard check
    return logGroup;
  }
}
