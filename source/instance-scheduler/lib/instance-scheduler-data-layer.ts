// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { Aws, RemovalPolicy, Stack } from "aws-cdk-lib";
import { cfnConditionToValue, overrideLogicalId, overrideProperty, overrideRetentionPolicies } from "./cfn";
import { AttributeType, BillingMode, CfnTable, StreamViewType, Table, TableEncryption } from "aws-cdk-lib/aws-dynamodb";
import { KmsKeys } from "./helpers/kms";
import { InstanceSchedulerStack } from "./instance-scheduler-stack";

export class InstanceSchedulerDataLayer {
  readonly configTable: Table;
  readonly stateTable: Table;
  readonly mwTable: Table;
  readonly registry: Table;

  constructor(scope: Stack) {
    const kmsKey = KmsKeys.get(scope);
    const retainDataAndLogsCondition = InstanceSchedulerStack.sharedConfig.retainDataAndLogsCondition;
    const useSolutionManagedKeyCondition = InstanceSchedulerStack.sharedConfig.useSolutionManagedKeyCondition;
    const conditionalSseSpec = {
      "Fn::If": [
        useSolutionManagedKeyCondition.logicalId,
        {
          KMSMasterKeyId: kmsKey.keyArn,
          SSEEnabled: true,
          SSEType: "KMS",
        },
        Aws.NO_VALUE,
      ],
    };
    this.registry = new Table(scope, "ResourceRegistry", {
      partitionKey: { name: "account", type: AttributeType.STRING },
      sortKey: { name: "sk", type: AttributeType.STRING },
      billingMode: BillingMode.PAY_PER_REQUEST,
      pointInTimeRecoverySpecification: {
        pointInTimeRecoveryEnabled: true,
      },
      encryption: TableEncryption.CUSTOMER_MANAGED,
      encryptionKey: kmsKey,
    });
    overrideRetentionPolicies(this.registry, cfnConditionToValue(retainDataAndLogsCondition, "Retain", "Delete"));
    overrideProperty(
      this.registry,
      "DeletionProtectionEnabled",
      cfnConditionToValue(retainDataAndLogsCondition, "True", "False"),
    );
    (this.registry.node.defaultChild as CfnTable).addPropertyOverride("SSESpecification", conditionalSseSpec);

    this.stateTable = new Table(scope, "StateTable", {
      partitionKey: { name: "service", type: AttributeType.STRING },
      sortKey: { name: "account-region", type: AttributeType.STRING },
      billingMode: BillingMode.PAY_PER_REQUEST,
      pointInTimeRecoverySpecification: {
        pointInTimeRecoveryEnabled: true,
      },
      encryption: TableEncryption.CUSTOMER_MANAGED,
      encryptionKey: kmsKey,
    });
    overrideLogicalId(this.stateTable, "StateTable");
    overrideRetentionPolicies(this.stateTable, cfnConditionToValue(retainDataAndLogsCondition, "Retain", "Delete"));
    overrideProperty(
      this.stateTable,
      "DeletionProtectionEnabled",
      cfnConditionToValue(retainDataAndLogsCondition, "True", "False"),
    );
    (this.stateTable.node.defaultChild as CfnTable).addPropertyOverride("SSESpecification", conditionalSseSpec);

    this.configTable = new Table(scope, "ConfigTable", {
      sortKey: { name: "name", type: AttributeType.STRING },
      partitionKey: { name: "type", type: AttributeType.STRING },
      billingMode: BillingMode.PAY_PER_REQUEST,
      removalPolicy: RemovalPolicy.DESTROY,
      pointInTimeRecoverySpecification: {
        pointInTimeRecoveryEnabled: true,
      },
      encryption: TableEncryption.CUSTOMER_MANAGED,
      encryptionKey: kmsKey,
      stream: StreamViewType.KEYS_ONLY,
    });
    overrideLogicalId(this.configTable, "ConfigTable");
    overrideRetentionPolicies(this.configTable, cfnConditionToValue(retainDataAndLogsCondition, "Retain", "Delete"));
    overrideProperty(
      this.configTable,
      "DeletionProtectionEnabled",
      cfnConditionToValue(retainDataAndLogsCondition, "True", "False"),
    );
    (this.configTable.node.defaultChild as CfnTable).addPropertyOverride("SSESpecification", conditionalSseSpec);

    this.mwTable = new Table(scope, "MaintenanceWindowTable", {
      partitionKey: { name: "account-region", type: AttributeType.STRING },
      sortKey: { name: "name-id", type: AttributeType.STRING },
      billingMode: BillingMode.PAY_PER_REQUEST,
      removalPolicy: RemovalPolicy.DESTROY,
      pointInTimeRecoverySpecification: {
        pointInTimeRecoveryEnabled: true,
      },
      encryption: TableEncryption.CUSTOMER_MANAGED,
      encryptionKey: kmsKey,
    });
    overrideLogicalId(this.mwTable, "MaintenanceWindowTable");
    overrideRetentionPolicies(this.mwTable, cfnConditionToValue(retainDataAndLogsCondition, "Retain", "Delete"));
    overrideProperty(
      this.mwTable,
      "DeletionProtectionEnabled",
      cfnConditionToValue(retainDataAndLogsCondition, "True", "False"),
    );
    (this.mwTable.node.defaultChild as CfnTable).addPropertyOverride("SSESpecification", conditionalSseSpec);
  }
}
