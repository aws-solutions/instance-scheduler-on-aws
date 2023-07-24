// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import { LambdaToDynamoDB } from "@aws-solutions-constructs/aws-lambda-dynamodb";
import { Aws, RemovalPolicy, Stack } from "aws-cdk-lib";

import * as iam from "aws-cdk-lib/aws-iam";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as cdk from "aws-cdk-lib";
import * as dynamodb from "aws-cdk-lib/aws-dynamodb";
import * as kms from "aws-cdk-lib/aws-kms";
import * as python from "@aws-cdk/aws-lambda-python-alpha";
export interface InstanceSchedulerLambdaProps {
  readonly solutionVersion: string;
  readonly memorySize: number;
  readonly schedulerRole: iam.Role;
  readonly kmsEncryptionKey: kms.Key;
  /**
   * Lambda Function environment variables
   */
  readonly environment?: {
    [key: string]: string;
  };
}
export class CoreScheduler {
  public readonly lambdaFunction: lambda.Function;
  public readonly configTable: dynamodb.Table;
  private readonly stateTable: dynamodb.Table;
  private readonly maintenanceWindowTable: dynamodb.Table;

  constructor(scope: Stack, props: InstanceSchedulerLambdaProps) {
    this.lambdaFunction = new python.PythonFunction(scope, "scheduler-lambda", {
      functionName: Aws.STACK_NAME + "-InstanceSchedulerMain",
      description: "EC2 and RDS instance scheduler, version " + props.solutionVersion,
      entry: `${__dirname}/../../app`,
      index: "instance_scheduler/main.py",
      handler: "lambda_handler",
      runtime: lambda.Runtime.PYTHON_3_10,
      role: props.schedulerRole,
      memorySize: props.memorySize,
      timeout: cdk.Duration.seconds(300),
      environment: props.environment,
      tracing: lambda.Tracing.ACTIVE,
      bundling: {
        assetExcludes: [".mypy_cache", ".tox", "__pycache__"],
      },
    });

    const lambdaToDynamoDbConstruct = new LambdaToDynamoDB(scope, "instance-scheduler-lambda", {
      existingLambdaObj: this.lambdaFunction,
      dynamoTableProps: {
        partitionKey: {
          name: "service",
          type: dynamodb.AttributeType.STRING,
        },
        sortKey: {
          name: "account-region",
          type: dynamodb.AttributeType.STRING,
        },
        billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
        removalPolicy: RemovalPolicy.DESTROY,
        pointInTimeRecovery: true,
      },
      tablePermissions: "ReadWrite",
    });

    this.stateTable = lambdaToDynamoDbConstruct.dynamoTable;

    const cfnStateTable = this.stateTable.node.defaultChild as dynamodb.CfnTable;
    cfnStateTable.overrideLogicalId("StateTable");
    cfnStateTable.addPropertyOverride("SSESpecification", {
      KMSMasterKeyId: props.kmsEncryptionKey.keyId,
      SSEEnabled: true,
      SSEType: "KMS",
    });

    this.configTable = new dynamodb.Table(scope, "ConfigTable", {
      sortKey: {
        name: "name",
        type: dynamodb.AttributeType.STRING,
      },
      partitionKey: {
        name: "type",
        type: dynamodb.AttributeType.STRING,
      },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      removalPolicy: RemovalPolicy.DESTROY,
      pointInTimeRecovery: true,
    });

    const cfnConfigTable = this.configTable.node.defaultChild as dynamodb.CfnTable;
    cfnConfigTable.overrideLogicalId("ConfigTable");
    cfnConfigTable.addPropertyOverride("SSESpecification", {
      KMSMasterKeyId: props.kmsEncryptionKey.keyId,
      SSEEnabled: true,
      SSEType: "KMS",
    });

    this.maintenanceWindowTable = new dynamodb.Table(scope, "MaintenanceWindowTable", {
      partitionKey: {
        name: "Name",
        type: dynamodb.AttributeType.STRING,
      },
      sortKey: {
        name: "account-region",
        type: dynamodb.AttributeType.STRING,
      },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      removalPolicy: RemovalPolicy.DESTROY,
      pointInTimeRecovery: true,
    });

    const cfnMaintenanceWindowTable = this.maintenanceWindowTable.node.defaultChild as dynamodb.CfnTable;
    cfnMaintenanceWindowTable.overrideLogicalId("MaintenanceWindowTable");
    cfnMaintenanceWindowTable.addPropertyOverride("SSESpecification", {
      KMSMasterKeyId: props.kmsEncryptionKey.keyId,
      SSEEnabled: true,
      SSEType: "KMS",
    });

    this.lambdaFunction.addEnvironment("CONFIG_TABLE", cfnConfigTable.ref);
    this.lambdaFunction.addEnvironment("MAINTENANCE_WINDOW_TABLE", cfnMaintenanceWindowTable.ref);
    this.lambdaFunction.addEnvironment("STATE_TABLE", cfnStateTable.ref);

    const dynamodbPolicy = new iam.PolicyStatement({
      actions: [
        "dynamodb:DeleteItem",
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:Query",
        "dynamodb:Scan",
        "dynamodb:BatchWriteItem",
        "dynamodb:UpdateItem",
      ],
      effect: iam.Effect.ALLOW,
      resources: [cfnConfigTable.attrArn, cfnMaintenanceWindowTable.attrArn],
    });

    this.lambdaFunction.addToRolePolicy(dynamodbPolicy);
  }
}
