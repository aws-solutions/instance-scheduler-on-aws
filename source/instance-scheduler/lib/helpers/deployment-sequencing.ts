// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { Construct } from "constructs";
import { Aspects, CfnWaitConditionHandle, Stack, IAspect, CfnResource } from "aws-cdk-lib";
import { CfnRole, CfnPolicy } from "aws-cdk-lib/aws-iam";
import { CfnFunction } from "aws-cdk-lib/aws-lambda";
import { CfnTable } from "aws-cdk-lib/aws-dynamodb";

class DependsOnAllResourcesOfType implements IAspect {
  constructor(
    private parentResource: CfnResource,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    private resourceType: new (...args: any[]) => CfnResource,
  ) {}

  visit(node: Construct): void {
    const cfnResource = node as CfnResource;

    if (!(node instanceof this.resourceType)) {
      return;
    }
    if (Stack.of(node) !== Stack.of(this.parentResource)) {
      return; //exclude resources that are not members of the same stack
    }
    if (cfnResource.cfnOptions?.condition) {
      return; // exclude conditional resources (these can cause the stack to fail validation)
    }
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    if ((cfnResource as any).condition) {
      return; // exclude conditional resources (these can cause the stack to fail validation)
    }

    this.parentResource.addDependency(cfnResource);
  }
}

export class SequencingGates {
  private static rolesGates = new Map<Stack, CfnWaitConditionHandle>();
  private static lambdasGates = new Map<Stack, CfnWaitConditionHandle>();
  private static policiesGates = new Map<Stack, CfnWaitConditionHandle>();
  private static tablesGates = new Map<Stack, CfnWaitConditionHandle>();

  public static afterAllRoles(scope: Construct) {
    const stack = Stack.of(scope);
    if (!this.rolesGates.has(stack)) {
      const gate = new CfnWaitConditionHandle(scope, "IamRoleDeploymentGate", {});
      this.rolesGates.set(stack, gate);
      // Add with higher priority to run after condition aspects
      Aspects.of(stack).add(new DependsOnAllResourcesOfType(gate, CfnRole), { priority: 800 });
    }
    return this.rolesGates.get(stack)!;
  }

  public static afterAllLambdas(scope: Construct) {
    const stack = Stack.of(scope);
    if (!this.lambdasGates.has(stack)) {
      const gate = new CfnWaitConditionHandle(scope, "LambdaDeploymentGate", {});
      this.lambdasGates.set(stack, gate);
      // Add with higher priority to run after condition aspects
      Aspects.of(stack).add(new DependsOnAllResourcesOfType(gate, CfnFunction), { priority: 800 });
    }
    return this.lambdasGates.get(stack)!;
  }

  public static afterAllPolicies(scope: Construct) {
    const stack = Stack.of(scope);
    if (!this.policiesGates.has(stack)) {
      const gate = new CfnWaitConditionHandle(scope, "IamPolicyDeploymentGate", {});
      this.policiesGates.set(stack, gate);
      // Add with higher priority to run after condition aspects
      Aspects.of(stack).add(new DependsOnAllResourcesOfType(gate, CfnPolicy), { priority: 800 });
    }
    return this.policiesGates.get(stack)!;
  }

  public static afterAllTables(scope: Construct) {
    const stack = Stack.of(scope);
    if (!this.tablesGates.has(stack)) {
      const gate = new CfnWaitConditionHandle(scope, "DynamoDbTableDeploymentGate", {});
      this.tablesGates.set(stack, gate);
      // Add with higher priority to run after condition aspects
      Aspects.of(stack).add(new DependsOnAllResourcesOfType(gate, CfnTable), { priority: 800 });
    }
    return this.tablesGates.get(stack)!;
  }
}
