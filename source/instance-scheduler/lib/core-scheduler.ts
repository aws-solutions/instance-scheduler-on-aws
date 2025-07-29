// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { Aws, CfnCondition, Fn, RemovalPolicy, Stack } from "aws-cdk-lib";
import { AttributeType, BillingMode, StreamViewType, Table, TableEncryption } from "aws-cdk-lib/aws-dynamodb";
import { CfnRule, Rule, RuleTargetInput, Schedule } from "aws-cdk-lib/aws-events";
import { LambdaFunction as LambdaFunctionTarget } from "aws-cdk-lib/aws-events-targets";
import { Role } from "aws-cdk-lib/aws-iam";
import { Alias, Key } from "aws-cdk-lib/aws-kms";
import { Function as LambdaFunction } from "aws-cdk-lib/aws-lambda";
import { LogGroup, RetentionDays } from "aws-cdk-lib/aws-logs";
import { Topic } from "aws-cdk-lib/aws-sns";
import { NagSuppressions } from "cdk-nag";
import { AnonymizedMetricsEnvironment } from "./anonymized-metrics-environment";
import { AsgScheduler } from "./asg-scheduler";
import { cfnConditionToTrueFalse, overrideRetentionPolicies, overrideLogicalId, overrideProperty } from "./cfn";
import { addCfnNagSuppressions } from "./cfn-nag";
import { OperationalInsightsDashboard } from "./dashboard/ops-insights-dashboard";
import { AsgSchedulingRole } from "./iam/asg-scheduling-role";
import { SchedulerRole } from "./iam/scheduler-role";
import { AsgHandler } from "./lambda-functions/asg-handler";
import { FunctionFactory } from "./lambda-functions/function-factory";
import { MainLambda } from "./lambda-functions/main";
import { MetricsUuidGenerator } from "./lambda-functions/metrics-uuid-generator";
import { SchedulingOrchestrator } from "./lambda-functions/scheduling-orchestrator";
import { SchedulingRequestHandlerLambda } from "./lambda-functions/scheduling-request-handler";
import { SpokeRegistrationLambda } from "./lambda-functions/spoke-registration";
import { SchedulingIntervalToCron } from "./scheduling-interval-mappings";

export interface CoreSchedulerProps {
  readonly solutionName: string;
  readonly solutionVersion: string;
  readonly solutionId: string;
  readonly memorySizeMB: number;
  readonly asgMemorySizeMB: number;
  readonly orchestratorMemorySizeMB: number;
  readonly principals: string[];
  readonly logRetentionDays: RetentionDays;
  readonly schedulingEnabled: CfnCondition;
  readonly schedulingIntervalMinutes: number;
  readonly namespace: string;
  readonly sendAnonymizedMetrics: CfnCondition;
  readonly enableDebugLogging: CfnCondition;
  readonly tagKey: string;
  readonly defaultTimezone: string;
  readonly enableEc2: CfnCondition;
  readonly enableRds: CfnCondition;
  readonly enableRdsClusters: CfnCondition;
  readonly enableNeptune: CfnCondition;
  readonly enableDocdb: CfnCondition;
  readonly enableRdsSnapshots: CfnCondition;
  readonly regions: string[];
  readonly enableSchedulingHubAccount: CfnCondition;
  readonly enableEc2SsmMaintenanceWindows: CfnCondition;
  readonly startTags: string;
  readonly stopTags: string;
  readonly enableAwsOrganizations: CfnCondition;
  readonly enableOpsInsights: CfnCondition;
  readonly kmsKeyArns: string[];
  readonly factory: FunctionFactory;
  readonly enableDdbDeletionProtection: CfnCondition;
  readonly enableAsgs: CfnCondition;
  readonly scheduledTagKey: string;
  readonly rulePrefix: string;
}

export class CoreScheduler {
  public readonly cfnScheduleCustomResourceHandler: LambdaFunction;
  public readonly hubSchedulerRole: Role;
  public readonly configTable: Table;
  public readonly topic: Topic;
  public readonly asgOrch: LambdaFunction;

  constructor(scope: Stack, props: CoreSchedulerProps) {
    const USER_AGENT_EXTRA = `AwsSolution/${props.solutionId}/${props.solutionVersion}`;

    const metricsUuidGenerator = new MetricsUuidGenerator(scope, {
      solutionName: props.solutionName,
      logRetentionDays: props.logRetentionDays,
      USER_AGENT_EXTRA,
      STACK_ID: Aws.STACK_ID,
      UUID_KEY: `/Solutions/${props.solutionName}/UUID/`,
      factory: props.factory,
    });

    const key = new Key(scope, "InstanceSchedulerEncryptionKey", {
      description: "Key for SNS",
      enabled: true,
      enableKeyRotation: true,
      removalPolicy: RemovalPolicy.DESTROY,
    });
    overrideRetentionPolicies(key, Fn.conditionIf(props.enableDdbDeletionProtection.logicalId, "Retain", "Delete"));
    overrideLogicalId(key, "InstanceSchedulerEncryptionKey");

    const keyAlias = new Alias(scope, "InstanceSchedulerEncryptionKeyAlias", {
      aliasName: `alias/${Aws.STACK_NAME}-instance-scheduler-encryption-key`,
      targetKey: key,
    });

    overrideLogicalId(keyAlias, "InstanceSchedulerEncryptionKeyAlias");

    this.topic = new Topic(scope, "InstanceSchedulerSnsTopic", {
      masterKey: key,
    });
    overrideLogicalId(this.topic, "InstanceSchedulerSnsTopic");

    const schedulerLogGroup = new LogGroup(scope, "SchedulerLogGroup", {
      logGroupName: Aws.STACK_NAME + "-logs",
      removalPolicy: RemovalPolicy.DESTROY,
      retention: props.logRetentionDays,
    });
    overrideLogicalId(schedulerLogGroup, "SchedulerLogGroup");
    // todo: this may not be true anymore
    addCfnNagSuppressions(schedulerLogGroup, {
      id: "W84",
      reason:
        "CloudWatch log groups only have transactional data from the Lambda function, this template has to be supported in gov cloud which doesn't yet have the feature to provide kms key id to cloudwatch log group.",
    });

    const stateTable = new Table(scope, "StateTable", {
      partitionKey: { name: "service", type: AttributeType.STRING },
      sortKey: { name: "account-region", type: AttributeType.STRING },
      billingMode: BillingMode.PAY_PER_REQUEST,
      pointInTimeRecovery: true,
      encryption: TableEncryption.CUSTOMER_MANAGED,
      encryptionKey: key,
    });
    overrideLogicalId(stateTable, "StateTable");
    overrideRetentionPolicies(
      stateTable,
      Fn.conditionIf(props.enableDdbDeletionProtection.logicalId, "Retain", "Delete"),
    );
    overrideProperty(
      stateTable,
      "DeletionProtectionEnabled",
      Fn.conditionIf(props.enableDdbDeletionProtection.logicalId, "True", "False"),
    );

    this.configTable = new Table(scope, "ConfigTable", {
      sortKey: { name: "name", type: AttributeType.STRING },
      partitionKey: { name: "type", type: AttributeType.STRING },
      billingMode: BillingMode.PAY_PER_REQUEST,
      removalPolicy: RemovalPolicy.DESTROY,
      pointInTimeRecovery: true,
      encryption: TableEncryption.CUSTOMER_MANAGED,
      encryptionKey: key,
      stream: StreamViewType.KEYS_ONLY,
    });
    overrideLogicalId(this.configTable, "ConfigTable");
    overrideRetentionPolicies(
      this.configTable,
      Fn.conditionIf(props.enableDdbDeletionProtection.logicalId, "Retain", "Delete"),
    );
    overrideProperty(
      this.configTable,
      "DeletionProtectionEnabled",
      Fn.conditionIf(props.enableDdbDeletionProtection.logicalId, "True", "False"),
    );

    const mwTable = new Table(scope, "MaintenanceWindowTable", {
      partitionKey: { name: "account-region", type: AttributeType.STRING },
      sortKey: { name: "name-id", type: AttributeType.STRING },
      billingMode: BillingMode.PAY_PER_REQUEST,
      removalPolicy: RemovalPolicy.DESTROY,
      pointInTimeRecovery: true,
      encryption: TableEncryption.CUSTOMER_MANAGED,
      encryptionKey: key,
    });
    overrideLogicalId(mwTable, "MaintenanceWindowTable");
    overrideRetentionPolicies(mwTable, Fn.conditionIf(props.enableDdbDeletionProtection.logicalId, "Retain", "Delete"));
    overrideProperty(
      mwTable,
      "DeletionProtectionEnabled",
      Fn.conditionIf(props.enableDdbDeletionProtection.logicalId, "True", "False"),
    );

    new SpokeRegistrationLambda(scope, {
      snsErrorReportingTopic: this.topic,
      scheduleLogGroup: schedulerLogGroup,
      logRetentionDays: props.logRetentionDays,
      USER_AGENT_EXTRA: USER_AGENT_EXTRA,
      configTable: this.configTable,
      solutionVersion: props.solutionVersion,
      enableDebugLogging: props.enableDebugLogging,
      principals: props.principals,
      namespace: props.namespace,
      enableAwsOrganizations: props.enableAwsOrganizations,
      factory: props.factory,
    });

    const metricsEnv: AnonymizedMetricsEnvironment = {
      METRICS_URL: "https://metrics.awssolutionsbuilder.com/generic",
      SEND_METRICS: cfnConditionToTrueFalse(props.sendAnonymizedMetrics),
      SOLUTION_ID: props.solutionId,
      SOLUTION_VERSION: props.solutionVersion,
      SCHEDULING_INTERVAL_MINUTES: props.schedulingIntervalMinutes.toString(),
      METRICS_UUID: metricsUuidGenerator.metricsUuid,
    };

    const mainFunction = new MainLambda(scope, {
      USER_AGENT_EXTRA: USER_AGENT_EXTRA,
      DEFAULT_TIMEZONE: props.defaultTimezone,
      configTable: this.configTable,
      schedulerLogGroup: schedulerLogGroup,
      snsErrorReportingTopic: this.topic,
      principals: props.principals,
      logRetentionDays: props.logRetentionDays,
      enableDebugLogging: props.enableDebugLogging,
      enableAwsOrganizations: props.enableAwsOrganizations,
      factory: props.factory,
      metricsEnv: metricsEnv,
    });

    const schedulingRequestHandler = new SchedulingRequestHandlerLambda(scope, {
      description: "Handles scheduling requests for Instance Scheduler on AWS, version " + props.solutionVersion,
      namespace: props.namespace,
      logRetentionDays: props.logRetentionDays,
      memorySizeMB: props.memorySizeMB,
      schedulerRoleName: SchedulerRole.roleName(props.namespace),
      DEFAULT_TIMEZONE: props.defaultTimezone,
      STACK_NAME: Aws.STACK_NAME,
      scheduleLogGroup: schedulerLogGroup,
      snsErrorReportingTopic: this.topic,
      USER_AGENT_EXTRA: USER_AGENT_EXTRA,
      configTable: this.configTable,
      stateTable: stateTable,
      maintWindowTable: mwTable,
      startTags: props.startTags,
      stopTags: props.stopTags,
      enableRds: props.enableRds,
      enableRdsClusters: props.enableRdsClusters,
      enableNeptune: props.enableNeptune,
      enableDocdb: props.enableDocdb,
      enableRdsSnapshots: props.enableRdsSnapshots,
      enableOpsMonitoring: props.enableOpsInsights,
      enableDebugLogging: props.enableDebugLogging,
      enableEc2SsmMaintenanceWindows: props.enableEc2SsmMaintenanceWindows,
      tagKey: props.tagKey,
      schedulingIntervalMinutes: props.schedulingIntervalMinutes,
      metricsEnv: metricsEnv,
      solutionName: props.solutionName,
      factory: props.factory,
    });

    const orchestratorLambda = new SchedulingOrchestrator(scope, {
      description: "scheduling orchestrator for Instance Scheduler on AWS, version " + props.solutionVersion,
      logRetentionDays: props.logRetentionDays,
      memorySizeMB: props.orchestratorMemorySizeMB,
      schedulingRequestHandlerLambda: schedulingRequestHandler.lambdaFunction,
      enableDebugLogging: props.enableDebugLogging,
      configTable: this.configTable,
      snsErrorReportingTopic: this.topic,
      snsKmsKey: key,
      scheduleLogGroup: schedulerLogGroup,
      USER_AGENT_EXTRA: USER_AGENT_EXTRA,
      enableSchedulingHubAccount: props.enableSchedulingHubAccount,
      enableEc2: props.enableEc2,
      enableRds: props.enableRds,
      enableRdsClusters: props.enableRdsClusters,
      enableNeptune: props.enableNeptune,
      enableDocdb: props.enableDocdb,
      enableAsgs: props.enableAsgs,
      regions: props.regions,
      defaultTimezone: props.defaultTimezone,
      enableRdsSnapshots: props.enableRdsSnapshots,
      enableAwsOrganizations: props.enableAwsOrganizations,
      enableEc2SsmMaintenanceWindows: props.enableEc2SsmMaintenanceWindows,
      opsDashboardEnabled: props.enableOpsInsights,
      startTags: props.startTags,
      stopTags: props.stopTags,
      metricsEnv: metricsEnv,
      factory: props.factory,
    });

    const asgHandler = new AsgHandler(scope, {
      namespace: props.namespace,
      logRetentionDays: props.logRetentionDays,
      memorySizeMB: props.asgMemorySizeMB,
      configTable: this.configTable,
      snsErrorReportingTopic: this.topic,
      encryptionKey: key,
      enableDebugLogging: props.enableDebugLogging,
      metricsEnv,
      tagKey: props.tagKey,
      asgSchedulingRoleName: AsgSchedulingRole.roleName(props.namespace),
      scheduledTagKey: props.scheduledTagKey,
      rulePrefix: props.rulePrefix,
      USER_AGENT_EXTRA,
      DEFAULT_TIMEZONE: props.defaultTimezone,
      factory: props.factory,
    });

    const asgScheduler = new AsgScheduler(scope, "ASGScheduler", {
      USER_AGENT_EXTRA,
      asgHandler,
      orchestratorMemorySizeMB: props.orchestratorMemorySizeMB,
      configTable: this.configTable,
      enableAsgs: props.enableAsgs,
      enableDebugLogging: props.enableDebugLogging,
      enableSchedulingHubAccount: props.enableSchedulingHubAccount,
      encryptionKey: key,
      factory: props.factory,
      logRetentionDays: props.logRetentionDays,
      metricsEnv,
      namespace: props.namespace,
      regions: props.regions,
      snsErrorReportingTopic: this.topic,
      solutionVersion: props.solutionVersion,
    });
    this.asgOrch = asgScheduler.asgOrchestratorLambdaFunction;

    const schedulingIntervalToCron = new SchedulingIntervalToCron(scope, "CronExpressionsForSchedulingIntervals", {});

    const schedulerRule = new Rule(scope, "SchedulerEventRule", {
      description: `Instance Scheduler - Rule to trigger instance for scheduler function version ${props.solutionVersion}`,
      schedule: Schedule.expression(schedulingIntervalToCron.getMapping(props.schedulingIntervalMinutes.toString())),
      targets: [
        new LambdaFunctionTarget(orchestratorLambda.lambdaFunction, {
          event: RuleTargetInput.fromObject({
            scheduled_action: "run_orchestrator",
          }),
          retryAttempts: 5,
        }),
      ],
    });

    //local scheduling roles
    this.hubSchedulerRole = new SchedulerRole(scope, "SchedulerRole", {
      assumedBy: schedulingRequestHandler.lambdaFunction.grantPrincipal,
      namespace: props.namespace,
      kmsKeys: props.kmsKeyArns,
    });

    new OperationalInsightsDashboard(scope, {
      enabled: props.enableOpsInsights,
      schedulingRequestHandler: schedulingRequestHandler,
      asgHandler: asgHandler,
      orchestrator: orchestratorLambda,
      schedulingIntervalMinutes: props.schedulingIntervalMinutes,
      namespace: props.namespace,
    });

    const cfnSchedulerRule = schedulerRule.node.defaultChild as CfnRule;
    cfnSchedulerRule.addPropertyOverride(
      "State",
      Fn.conditionIf(props.schedulingEnabled.logicalId, "ENABLED", "DISABLED"),
    );

    this.cfnScheduleCustomResourceHandler = mainFunction.lambdaFunction;

    NagSuppressions.addStackSuppressions(Stack.of(scope), [
      {
        id: "AwsSolutions-L1",
        reason: "Python 3.11 is the newest available runtime. This finding is a false positive.",
      },
    ]);
  }
}
