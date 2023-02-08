import {LambdaToDynamoDB, LambdaToDynamoDBProps} from "@aws-solutions-constructs/aws-lambda-dynamodb";
import {Aws, RemovalPolicy} from "aws-cdk-lib";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as cdk from "aws-cdk-lib";
import * as dynamodb from "aws-cdk-lib/aws-dynamodb";
import {Construct} from "constructs";
import {Effect, PolicyStatement} from "aws-cdk-lib/aws-iam";
export enum DeploymentType {
  SOLUTIONS_S3, CDK_DEPLOY
}
export interface InstanceSchedulerLambdaProps {
  deploymentType: DeploymentType

  solutionVersion: string
  solutionTradeMarkName: string
  solutionsBucket?: cdk.aws_s3.IBucket

  memorySize: number
  schedulerRole: cdk.aws_iam.Role

  /**
   * Lambda Function environment variables
   */
  environment?: {
    [key: string]: string;
  }
}
export class CoreScheduler extends Construct {

  public readonly lambdaFunction: lambda.Function;
  public readonly configTable: dynamodb.Table
  private readonly stateTable: dynamodb.Table
  private readonly maintenanceWindowTable: dynamodb.Table

  constructor(scope: Construct, id: string, props: InstanceSchedulerLambdaProps) {
    super(scope, id);

    const lambdaToDynamoDbConstruct = new LambdaToDynamoDB(this, 'instance-scheduler-lambda', this.lambdaToDynamoPropsFrom(props))

    this.lambdaFunction = lambdaToDynamoDbConstruct.lambdaFunction;
    this.stateTable = lambdaToDynamoDbConstruct.dynamoTable;

    const cfnStateTable = this.stateTable.node.defaultChild as dynamodb.CfnTable
    cfnStateTable.overrideLogicalId('StateTable')
    cfnStateTable.addPropertyOverride("SSESpecification", {
      "KMSMasterKeyId": { "Ref": "InstanceSchedulerEncryptionKey" },
      "SSEEnabled": true,
      "SSEType": 'KMS'
    })

    this.configTable = new dynamodb.Table(this, 'ConfigTable', {
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
      "KMSMasterKeyId": { "Ref": "InstanceSchedulerEncryptionKey" },
      "SSEEnabled": true,
      "SSEType": 'KMS'
    })

    this.maintenanceWindowTable = new dynamodb.Table(this, 'MaintenanceWindowTable', {
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


    const dynamodbPolicy = new PolicyStatement({
      actions: [
        'dynamodb:DeleteItem',
        'dynamodb:GetItem',
        'dynamodb:PutItem',
        'dynamodb:Query',
        'dynamodb:Scan',
        'dynamodb:BatchWriteItem'
      ],
      effect: Effect.ALLOW,
      resources: [
        cfnConfigTable.attrArn,
        cfnMaintenanceWindowTable.attrArn
      ]
    })

    this.lambdaFunction.addToRolePolicy(dynamodbPolicy)
  }

  lambdaToDynamoPropsFrom(props: InstanceSchedulerLambdaProps) : LambdaToDynamoDBProps {

    //to be able to cdk deploy:
    //lambda.Code.fromAsset("../app")

    return {
     lambdaFunctionProps: {
       functionName: Aws.STACK_NAME + '-InstanceSchedulerMain',
       description: 'EC2 and RDS instance scheduler, version ' + props["solutionVersion"],
       code: lambda.Code.fromBucket(props.solutionsBucket!, props["solutionTradeMarkName"] + '/' + props["solutionVersion"] + '/instance-scheduler.zip'),
       runtime: lambda.Runtime.PYTHON_3_9,
       handler: 'main.lambda_handler',
       role: props.schedulerRole,
       memorySize: props.memorySize,
       timeout: cdk.Duration.seconds(300),
       environment: props.environment
     },
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
    }

  }

  // const dependenciesLayer = new lambda.LayerVersion() {
  // }


}

