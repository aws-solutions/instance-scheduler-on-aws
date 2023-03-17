// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import { LambdaToDynamoDB, LambdaToDynamoDBProps } from "@aws-solutions-constructs/aws-lambda-dynamodb";
import { Aws, RemovalPolicy, Stack } from "aws-cdk-lib";
import { NagSuppressions } from "cdk-nag";

import * as iam from "aws-cdk-lib/aws-iam";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as cdk from "aws-cdk-lib";
import * as dynamodb from "aws-cdk-lib/aws-dynamodb";
import * as kms from "aws-cdk-lib/aws-kms";

export interface InstanceSchedulerLambdaProps {
  readonly solutionVersion: string;
  readonly solutionTradeMarkName: string;
  readonly solutionsBucket: s3.IBucket;
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
    const lambdaToDynamoDbConstruct = new LambdaToDynamoDB(
      scope,
      "instance-scheduler-lambda",
      extractLambdaToDynamoPropsFrom(props)
    );

    this.lambdaFunction = lambdaToDynamoDbConstruct.lambdaFunction;
    this.stateTable = lambdaToDynamoDbConstruct.dynamoTable;

    const cfnStateTable = this.stateTable.node.defaultChild as dynamodb.CfnTable;
    cfnStateTable.overrideLogicalId("StateTable");
    cfnStateTable.addPropertyOverride("SSESpecification", {
      KMSMasterKeyId: { Ref: "InstanceSchedulerEncryptionKey" },
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
      KMSMasterKeyId: { Ref: "InstanceSchedulerEncryptionKey" },
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
      ],
      effect: iam.Effect.ALLOW,
      resources: [cfnConfigTable.attrArn, cfnMaintenanceWindowTable.attrArn],
    });

    this.lambdaFunction.addToRolePolicy(dynamodbPolicy);

    NagSuppressions.addResourceSuppressions(lambdaToDynamoDbConstruct.node.findChild("LambdaFunctionServiceRole"), [
      {
        id: "AwsSolutions-IAM5",
        reason:
          "This Lambda function needs to be able to write a log streams for each scheduler execution (1 per account/region/service)",
      },
    ]);
  }
}

function extractLambdaToDynamoPropsFrom(props: InstanceSchedulerLambdaProps): LambdaToDynamoDBProps {
  return {
    lambdaFunctionProps: {
      functionName: Aws.STACK_NAME + "-InstanceSchedulerMain",
      description: "EC2 and RDS instance scheduler, version " + props.solutionVersion,
      code: lambda.Code.fromBucket(
        props.solutionsBucket,
        props.solutionTradeMarkName + "/" + props.solutionVersion + "/instance-scheduler.zip"
      ),
      runtime: lambda.Runtime.PYTHON_3_9,
      handler: "main.lambda_handler",
      role: props.schedulerRole,
      memorySize: props.memorySize,
      timeout: cdk.Duration.seconds(300),
      environment: props.environment,
    },
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
  };
}
