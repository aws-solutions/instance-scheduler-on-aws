/*****************************************************************************
 *  Copyright 2020 Amazon.com, Inc. or its affiliates. All Rights Reserved.   *
 *                                                                            *
 *  Licensed under the Apache License, Version 2.0 (the "License"). You may   *
 *  not use this file except in compliance with the License. A copy of the    *
 *  License is located at                                                     *
 *                                                                            *
 *      http://www.apache.org/licenses/LICENSE-2.0                            *
 *                                                                            *
 *  or in the 'license' file accompanying this file. This file is distributed *
 *  on an 'AS IS' BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND,        *
 *  express or implied. See the License for the specific language governing   *
 *  permissions and limitations under the License.                            *
 *****************************************************************************/

import {LambdaToDynamoDB} from "@aws-solutions-constructs/aws-lambda-dynamodb";
import {Aws, RemovalPolicy, Stack} from "aws-cdk-lib";

import * as iam from "aws-cdk-lib/aws-iam"
import * as s3 from "aws-cdk-lib/aws-s3"
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as cdk from "aws-cdk-lib";
import * as dynamodb from "aws-cdk-lib/aws-dynamodb";
import * as kms from "aws-cdk-lib/aws-kms";
import * as python from "@aws-cdk/aws-lambda-python-alpha"

export interface InstanceSchedulerLambdaProps {

  readonly solutionVersion: string
  readonly solutionsBucket?: s3.IBucket
  readonly memorySize: number
  readonly schedulerRole: iam.Role
  readonly kmsEncryptionKey: kms.Key
  /**
   * Lambda Function environment variables
   */
  readonly environment?: {
    [key: string]: string;
  }
}
export class CoreScheduler {

  public readonly lambdaFunction: lambda.Function;
  public readonly configTable: dynamodb.Table
  private readonly stateTable: dynamodb.Table
  private readonly maintenanceWindowTable: dynamodb.Table

  constructor(scope: Stack, props: InstanceSchedulerLambdaProps) {

    this.lambdaFunction = new python.PythonFunction(scope, "scheduler-lambda",{
      functionName: Aws.STACK_NAME + '-InstanceSchedulerMain',
      description: 'EC2 and RDS instance scheduler, version ' + props.solutionVersion,
      entry: "../app",
      index: "main.py",
      handler: 'lambda_handler',
      runtime: lambda.Runtime.PYTHON_3_9,
      role: props.schedulerRole,
      memorySize: props.memorySize,
      timeout: cdk.Duration.seconds(300),
      environment: props.environment,
      tracing: lambda.Tracing.ACTIVE,

      bundling: {
        commandHooks: {
          beforeBundling(inputDir: string, outputDir: string): string[] {
             return [`pip install --target ${outputDir} -e ${inputDir}`]
           },
          afterBundling(): string[] {
            return []
          }
        }
      }
    })

    const lambdaToDynamoDbConstruct = new LambdaToDynamoDB(scope, 'instance-scheduler-lambda', {
      existingLambdaObj: this.lambdaFunction,
      dynamoTableProps: {
        partitionKey: {
          name: 'service',
          type: dynamodb.AttributeType.STRING
        },
        sortKey: {
          name: 'account-region',
          type: dynamodb.AttributeType.STRING
        },
        billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
        removalPolicy: RemovalPolicy.DESTROY,
        pointInTimeRecovery: true
      },
      tablePermissions: "ReadWrite",
    })


    this.stateTable = lambdaToDynamoDbConstruct.dynamoTable;

    const cfnStateTable = this.stateTable.node.defaultChild as dynamodb.CfnTable
    cfnStateTable.overrideLogicalId('StateTable')
    cfnStateTable.addPropertyOverride("SSESpecification", {
      "KMSMasterKeyId": { "Ref": "InstanceSchedulerEncryptionKey" },
      "SSEEnabled": true,
      "SSEType": 'KMS'
    })

    this.configTable = new dynamodb.Table(scope, 'ConfigTable', {
      sortKey: {
        name: 'name',
        type: dynamodb.AttributeType.STRING
      },
      partitionKey: {
        name: 'type',
        type: dynamodb.AttributeType.STRING
      },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      removalPolicy: RemovalPolicy.DESTROY,
      pointInTimeRecovery: true
    })

    const cfnConfigTable = this.configTable.node.defaultChild as dynamodb.CfnTable
    cfnConfigTable.overrideLogicalId('ConfigTable')
    cfnConfigTable.addPropertyOverride("SSESpecification", {
      "KMSMasterKeyId": props.kmsEncryptionKey.keyId,
      "SSEEnabled": true,
      "SSEType": 'KMS'
    })

    this.maintenanceWindowTable = new dynamodb.Table(scope, 'MaintenanceWindowTable', {
      partitionKey: {
        name: 'Name',
        type: dynamodb.AttributeType.STRING
      },
      sortKey: {
        name: "account-region",
        type: dynamodb.AttributeType.STRING
      },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      removalPolicy: RemovalPolicy.DESTROY,
      pointInTimeRecovery: true
    })

    const cfnMaintenanceWindowTable = this.maintenanceWindowTable.node.defaultChild as dynamodb.CfnTable
    cfnMaintenanceWindowTable.overrideLogicalId('MaintenanceWindowTable')
    cfnMaintenanceWindowTable.addPropertyOverride("SSESpecification", {
      "KMSMasterKeyId": { "Ref": "InstanceSchedulerEncryptionKey" },
      "SSEEnabled": true,
      "SSEType": 'KMS'
    })

    this.lambdaFunction.addEnvironment('CONFIG_TABLE', cfnConfigTable.ref)
    this.lambdaFunction.addEnvironment('MAINTENANCE_WINDOW_TABLE', cfnMaintenanceWindowTable.ref)
    this.lambdaFunction.addEnvironment('STATE_TABLE', cfnStateTable.ref)


    const dynamodbPolicy = new iam.PolicyStatement({
      actions: [
        'dynamodb:DeleteItem',
        'dynamodb:GetItem',
        'dynamodb:PutItem',
        'dynamodb:Query',
        'dynamodb:Scan',
        'dynamodb:BatchWriteItem'
      ],
      effect: iam.Effect.ALLOW,
      resources: [
        cfnConfigTable.attrArn,
        cfnMaintenanceWindowTable.attrArn
      ]
    })

    this.lambdaFunction.addToRolePolicy(dynamodbPolicy)

    // NagSuppressions.addResourceSuppressions(lambdaToDynamoDbConstruct.node.findChild("LambdaFunctionServiceRole"), [{
    //   id: "AwsSolutions-IAM5",
    //   reason: "This Lambda function needs to be able to write a log streams for each scheduler execution (1 per account/region/service)"
    // }])
  }

}

// function extractLambdaToDynamoPropsFrom(props: InstanceSchedulerLambdaProps) : LambdaToDynamoDBProps {
//
//   return {
//     lambdaFunctionProps: {
//       functionName: Aws.STACK_NAME + '-InstanceSchedulerMain',
//       description: 'EC2 and RDS instance scheduler, version ' + props.solutionVersion,
//       code: lambda.Code.fromAsset( "../app"),
//       runtime: lambda.Runtime.PYTHON_3_9,
//       handler: 'main.lambda_handler',
//       role: props.schedulerRole,
//       memorySize: props.memorySize,
//       timeout: cdk.Duration.seconds(300),
//       environment: props.environment
//     },
//     dynamoTableProps: {
//       partitionKey: {
//         name: 'service',
//         type: dynamodb.AttributeType.STRING
//       },
//       sortKey: {
//         name: 'account-region',
//         type: dynamodb.AttributeType.STRING
//       },
//       billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
//       removalPolicy: RemovalPolicy.DESTROY,
//       pointInTimeRecovery: true
//     },
//     tablePermissions: "ReadWrite",
//   }
//
// }
