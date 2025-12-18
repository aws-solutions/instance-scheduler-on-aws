// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { Stack, Aws } from "aws-cdk-lib";
import { Key } from "aws-cdk-lib/aws-kms";
import { Construct } from "constructs";
import { InstanceSchedulerStack } from "../instance-scheduler-stack";
import { cfnConditionToValue, overrideLogicalId, overrideRetentionPolicies } from "../cfn";

export class KmsKeys {
  private static instances: { [key: string]: Key } = {};
  public static get(scope: Construct): Key {
    const stack = Stack.of(scope);
    const isKeyId = stack.stackName;
    if (!KmsKeys.instances[isKeyId]) {
      const key = new Key(Stack.of(scope), "InstanceSchedulerEncryptionKey", {
        enabled: true,
        enableKeyRotation: true,
        description: `Instance Scheduler CMK - ${Aws.STACK_NAME}`,
        alias: `AwsSolutions/InstanceScheduler/${InstanceSchedulerStack.sharedConfig.namespace}/${isKeyId}`,
      });
      overrideRetentionPolicies(
        key,
        cfnConditionToValue(InstanceSchedulerStack.sharedConfig.retainDataAndLogsCondition, "Retain", "Delete"),
      );
      overrideLogicalId(key, "InstanceSchedulerEncryptionKey");
      overrideLogicalId(key.node.findChild("Alias"), "InstanceSchedulerEncryptionKeyAlias");

      KmsKeys.instances[isKeyId] = key;
    }
    return KmsKeys.instances[isKeyId]!;
  }
}
