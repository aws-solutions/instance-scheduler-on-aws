// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { Aws, CfnCondition, Duration, Fn, RemovalPolicy } from "aws-cdk-lib";
import { Table } from "aws-cdk-lib/aws-dynamodb";
import { Effect, Policy, PolicyStatement, Role, ServicePrincipal } from "aws-cdk-lib/aws-iam";
import { Function as LambdaFunction } from "aws-cdk-lib/aws-lambda";
import { LogGroup, RetentionDays } from "aws-cdk-lib/aws-logs";
import { Topic } from "aws-cdk-lib/aws-sns";
import { NagSuppressions } from "cdk-nag";
import { Construct } from "constructs";
import { AnonymizedMetricsEnvironment } from "../anonymized-metrics-environment";
import { cfnConditionToTrueFalse } from "../cfn";
import { addCfnNagSuppressions } from "../cfn-nag";
import { FunctionFactory } from "./function-factory";
import { Key } from "aws-cdk-lib/aws-kms";

export interface SchedulingOrchestratorProps {
  readonly description: string;
  readonly logRetentionDays: RetentionDays;
  readonly memorySizeMB: number;
  readonly schedulingRequestHandlerLambda: LambdaFunction;
  readonly enableDebugLogging: CfnCondition;
  readonly configTable: Table;
  readonly snsErrorReportingTopic: Topic;
  readonly snsKmsKey: Key;
  readonly scheduleLogGroup: LogGroup;
  readonly USER_AGENT_EXTRA: string;
  readonly enableSchedulingHubAccount: CfnCondition;
  readonly enableEc2: CfnCondition;
  readonly enableRds: CfnCondition;
  readonly enableRdsClusters: CfnCondition;
  readonly enableNeptune: CfnCondition;
  readonly enableDocdb: CfnCondition;
  readonly enableAsgs: CfnCondition;
  readonly regions: string[];
  readonly defaultTimezone: string;
  readonly enableRdsSnapshots: CfnCondition;
  readonly enableAwsOrganizations: CfnCondition;
  readonly enableEc2SsmMaintenanceWindows: CfnCondition;
  readonly opsDashboardEnabled: CfnCondition;
  readonly startTags: string;
  readonly stopTags: string;
  readonly metricsEnv: AnonymizedMetricsEnvironment;
  readonly factory: FunctionFactory;
}

export class SchedulingOrchestrator {
  readonly lambdaFunction: LambdaFunction;

  constructor(scope: Construct, props: SchedulingOrchestratorProps) {
    const role = new Role(scope, "SchedulingOrchestratorRole", {
      assumedBy: new ServicePrincipal("lambda.amazonaws.com"),
    });

    this.lambdaFunction = props.factory.createFunction(scope, "SchedulingOrchestrator", {
      description: props.description,
      index: "instance_scheduler/handler/scheduling_orchestrator.py",
      handler: "handle_orchestration_request",
      memorySize: props.memorySizeMB,
      role: role,
      timeout: Duration.minutes(5),
      environment: {
        USER_AGENT_EXTRA: props.USER_AGENT_EXTRA,
        LOG_GROUP: props.scheduleLogGroup.logGroupName,
        ISSUES_TOPIC_ARN: props.snsErrorReportingTopic.topicArn,
        ENABLE_DEBUG_LOGS: cfnConditionToTrueFalse(props.enableDebugLogging),
        CONFIG_TABLE: props.configTable.tableName,
        SCHEDULING_REQUEST_HANDLER_NAME: props.schedulingRequestHandlerLambda.functionName,
        ENABLE_SCHEDULE_HUB_ACCOUNT: cfnConditionToTrueFalse(props.enableSchedulingHubAccount),
        ENABLE_EC2_SERVICE: cfnConditionToTrueFalse(props.enableEc2),
        ENABLE_RDS_SERVICE: cfnConditionToTrueFalse(props.enableRds),
        ENABLE_RDS_CLUSTERS: cfnConditionToTrueFalse(props.enableRdsClusters),
        ENABLE_NEPTUNE_SERVICE: cfnConditionToTrueFalse(props.enableNeptune),
        ENABLE_DOCDB_SERVICE: cfnConditionToTrueFalse(props.enableDocdb),
        ENABLE_ASG_SERVICE: cfnConditionToTrueFalse(props.enableAsgs),
        SCHEDULE_REGIONS: Fn.join(",", props.regions),
        DEFAULT_TIMEZONE: props.defaultTimezone,
        ENABLE_RDS_SNAPSHOTS: cfnConditionToTrueFalse(props.enableRdsSnapshots),
        ENABLE_AWS_ORGANIZATIONS: cfnConditionToTrueFalse(props.enableAwsOrganizations),
        ENABLE_EC2_SSM_MAINTENANCE_WINDOWS: cfnConditionToTrueFalse(props.enableEc2SsmMaintenanceWindows),
        OPS_DASHBOARD_ENABLED: cfnConditionToTrueFalse(props.opsDashboardEnabled),
        START_TAGS: props.startTags,
        STOP_TAGS: props.stopTags,
        ...props.metricsEnv,
      },
    });

    const lambdaDefaultLogGroup = new LogGroup(scope, "SchedulingOrchestratorLogGroup", {
      logGroupName: `/aws/lambda/${this.lambdaFunction.functionName}`,
      removalPolicy: RemovalPolicy.RETAIN,
      retention: props.logRetentionDays,
    });

    if (!this.lambdaFunction.role) {
      throw new Error("lambdaFunction role is missing");
    }

    const orchestratorPolicy = new Policy(scope, "SchedulingOrchestratorPermissionsPolicy", {
      roles: [this.lambdaFunction.role],
    });

    //invoke must be applied to the base lambda role, not a policy
    props.schedulingRequestHandlerLambda.grantInvoke(this.lambdaFunction.role);

    lambdaDefaultLogGroup.grantWrite(orchestratorPolicy);
    props.configTable.grantReadData(orchestratorPolicy);
    props.snsErrorReportingTopic.grantPublish(orchestratorPolicy);
    props.scheduleLogGroup.grantWrite(orchestratorPolicy);

    orchestratorPolicy.addStatements(
      new PolicyStatement({ actions: ["ssm:DescribeParameters"], effect: Effect.ALLOW, resources: ["*"] }),
    );

    orchestratorPolicy.addStatements(
      new PolicyStatement({
        actions: ["kms:Decrypt", "kms:GenerateDataKey*"],
        effect: Effect.ALLOW,
        resources: [props.snsKmsKey.keyArn],
      }),
    );

    orchestratorPolicy.addStatements(
      new PolicyStatement({
        actions: ["ssm:GetParameter", "ssm:GetParameters"],
        effect: Effect.ALLOW,
        resources: [`arn:${Aws.PARTITION}:ssm:*:${Aws.ACCOUNT_ID}:parameter/*`],
      }),
    );

    const defaultPolicy = this.lambdaFunction.role.node.tryFindChild("DefaultPolicy");
    if (!defaultPolicy) {
      throw Error("Unable to find default policy on lambda role");
    }

    addCfnNagSuppressions(defaultPolicy, {
      id: "W12",
      reason: "Wildcard required for xray",
    });

    NagSuppressions.addResourceSuppressions(defaultPolicy, [
      {
        id: "AwsSolutions-IAM5",
        appliesTo: ["Resource::*"],
        reason: "required for xray",
      },
      {
        id: "AwsSolutions-IAM5",
        appliesTo: ["Resource::<schedulingRequestHandlerLambdaC395DC9E.Arn>:*"],
        reason: "permission to invoke request handler lambda",
      },
    ]);

    addCfnNagSuppressions(
      orchestratorPolicy,
      {
        id: "W12",
        reason: "Wildcard required for ssm:DescribeParameters",
      },
      {
        id: "W76",
        reason: "Acknowledged IAM policy document SPCM > 25",
      },
    );

    NagSuppressions.addResourceSuppressions(orchestratorPolicy, [
      {
        id: "AwsSolutions-IAM5",
        appliesTo: ["Action::kms:GenerateDataKey*", "Action::kms:ReEncrypt*"],
        reason: "Permission to use solution CMK with dynamo/sns",
      },
      {
        id: "AwsSolutions-IAM5",
        appliesTo: ["Resource::arn:<AWS::Partition>:ssm:*:<AWS::AccountId>:parameter/*", "Resource::*"],
        reason:
          "Orchestrator requires access to SSM parameters for translating " +
          "{param: my-param} values to configured account ids",
      },
    ]);

    addCfnNagSuppressions(
      this.lambdaFunction,
      {
        id: "W89",
        reason: "This Lambda function does not need to access any resource provisioned within a VPC.",
      },
      {
        id: "W58",
        reason: "This Lambda function has permission provided to write to CloudWatch logs using the iam roles.",
      },
      {
        id: "W92",
        reason: "Lambda function is invoked by a scheduled rule, it does not run concurrently",
      },
    );

    addCfnNagSuppressions(lambdaDefaultLogGroup, {
      id: "W84",
      reason:
        "This template has to be supported in gov cloud which doesn't yet have the feature to provide kms key id to cloudwatch log group",
    });
  }
}
