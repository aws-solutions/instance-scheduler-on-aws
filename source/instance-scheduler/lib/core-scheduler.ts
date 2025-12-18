// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { Aws, CfnCondition, Fn, Stack } from "aws-cdk-lib";
import { CfnRule, EventBus, Rule, RuleTargetInput, Schedule } from "aws-cdk-lib/aws-events";
import { LambdaFunction as LambdaFunctionTarget } from "aws-cdk-lib/aws-events-targets";
import { CfnPolicy, CfnRole, CompositePrincipal, Role } from "aws-cdk-lib/aws-iam";
import { Function as LambdaFunction } from "aws-cdk-lib/aws-lambda";
import { Topic } from "aws-cdk-lib/aws-sns";
import { NagSuppressions } from "cdk-nag";
import { AnonymizedMetricsEnvironment } from "./anonymized-metrics-environment";
import { cfnConditionToTrueFalse } from "./cfn";
import { OperationalInsightsDashboard } from "./dashboard/ops-insights-dashboard";
import { SchedulerRole } from "./iam/scheduler-role";
import { FunctionFactory } from "./lambda-functions/function-factory";
import { MainLambda } from "./lambda-functions/main";
import { MetricsUuidGenerator } from "./lambda-functions/metrics-uuid-generator";
import { SchedulingOrchestrator } from "./lambda-functions/scheduling-orchestrator";
import { SchedulingRequestHandlerLambda } from "./lambda-functions/scheduling-request-handler";
import { SchedulingIntervalToCron } from "./scheduling-interval-mappings";
import { InstanceSchedulerDataLayer } from "./instance-scheduler-data-layer";
import { LogInsightsQueries } from "./observability/log-insights-queries";
import { KmsKeys } from "./helpers/kms";
import { HubResourceRegistration } from "./lambda-functions/resource-registration";
import { IceErrorRetry } from "./lambda-functions/ice-error-retry";
import { HeartbeatMetricReporter } from "./lambda-functions/heartbeat-metric-reporter";
import { SnsLogSubscriber } from "./observability/log-sns-forwarding";
import { SpokeRegistrationLambda } from "./lambda-functions/spoke-registration";
import { RegionRegistrationCustomResource } from "./lambda-functions/region-registration";
export interface CoreSchedulerProps {
  readonly solutionName: string;
  readonly solutionVersion: string;
  readonly solutionId: string;
  readonly memorySizeMB: number;
  readonly orchestratorMemorySizeMB: number;
  readonly principals: string[];
  readonly schedulingEnabled: CfnCondition;
  readonly schedulingIntervalMinutes: number;
  readonly namespace: string;
  readonly sendAnonymizedMetrics: CfnCondition;
  readonly tagKey: string;
  readonly defaultTimezone: string;
  readonly enableRdsSnapshots: CfnCondition;
  readonly regions: string[];
  readonly enableEc2SsmMaintenanceWindows: CfnCondition;
  readonly enableAwsOrganizations: CfnCondition;
  readonly enableOpsInsights: CfnCondition;
  readonly kmsKeyArns: string[];
  readonly licenseManagerArns: string[];
  readonly factory: FunctionFactory;
  readonly asgMetadataTagKey: string;
  readonly rulePrefix: string;
}

export class CoreScheduler {
  public readonly cfnScheduleCustomResourceHandler: LambdaFunction;
  public readonly hubSchedulerRole: Role;
  public readonly topic: Topic;
  public readonly asgOrch: LambdaFunction;
  public readonly dataLayer: InstanceSchedulerDataLayer;
  public readonly regionalEventBusName: string;
  public readonly globalEventBus: EventBus;

  constructor(scope: Stack, props: CoreSchedulerProps) {
    const USER_AGENT_EXTRA = `AwsSolution/${props.solutionId}/${props.solutionVersion}`;
    const REGIONAL_EVENT_BUS_NAME = `IS-LocalEvents-${props.namespace}`;
    const GLOBAL_EVENT_BUS_NAME = `IS-GlobalEvents-${props.namespace}`;

    this.dataLayer = new InstanceSchedulerDataLayer(scope);

    const metricsUuidGenerator = new MetricsUuidGenerator(scope, {
      dataLayer: this.dataLayer,
      USER_AGENT_EXTRA: USER_AGENT_EXTRA,
      solutionName: props.solutionName,
      STACK_ID: Aws.STACK_ID,
      UUID_KEY: `/Solutions/${props.solutionName}/UUID/`,
      factory: props.factory,
    });

    this.topic = new SnsLogSubscriber(scope, "SnsReporting", {
      USER_AGENT_EXTRA: USER_AGENT_EXTRA,
      factory: props.factory,
    }).snsTopic;

    this.globalEventBus = new EventBus(scope, "globalEvents", {
      eventBusName: GLOBAL_EVENT_BUS_NAME,
    });

    const spokeRegistrationLambda = new SpokeRegistrationLambda(scope, {
      dataLayer: this.dataLayer,
      USER_AGENT_EXTRA: USER_AGENT_EXTRA,
      solutionVersion: props.solutionVersion,
      principals: props.principals,
      namespace: props.namespace,
      scheduleTagKey: props.tagKey,
      schedulingIntervalMinutes: props.schedulingIntervalMinutes,
      enableAwsOrganizations: props.enableAwsOrganizations,
      asgRulePrefix: props.rulePrefix,
      asgMetadataTagKey: props.asgMetadataTagKey,
      localEventBusName: REGIONAL_EVENT_BUS_NAME,
      globalEventBus: this.globalEventBus,
      factory: props.factory,
      ssmParamUpdateRoleName: RegionRegistrationCustomResource.ssmParamUpdateRoleName(props.namespace),
      ssmParamPathName: RegionRegistrationCustomResource.ssmParamPathName(props.namespace),
    });

    const resourceRegistration = new HubResourceRegistration(scope, "ResourceRegistration", {
      namespace: props.namespace,
      scheduleTagKey: props.tagKey,
      factory: props.factory,
      organizationsMode: props.enableAwsOrganizations,
      principals: props.principals,
      configTable: this.dataLayer.configTable,
      registryTable: this.dataLayer.registry,
      stackId: Aws.STACK_ID,
      stackName: Aws.STACK_NAME,
      schedulerRoleName: SchedulerRole.roleName(props.namespace),
      USER_AGENT_EXTRA: USER_AGENT_EXTRA,
      schedulingIntervalMinutes: props.schedulingIntervalMinutes,
      asgScheduledRulesPrefix: props.rulePrefix,
      asgMetadataTagKey: props.asgMetadataTagKey,
      solutionVersion: props.solutionVersion,
      regions: props.regions,
      regionalEventBusName: REGIONAL_EVENT_BUS_NAME,
      spokeRegistrationLambda: spokeRegistrationLambda.lambdaFunction,
      spokeRegistrationLambdaRoleName: SpokeRegistrationLambda.roleName(props.namespace),
      globalEventBus: this.globalEventBus,
    });

    this.regionalEventBusName = resourceRegistration.regionalEventBusName;

    const metricsEnv: AnonymizedMetricsEnvironment = {
      METRICS_URL: "https://metrics.awssolutionsbuilder.com/generic",
      SEND_METRICS: cfnConditionToTrueFalse(props.sendAnonymizedMetrics),
      SOLUTION_ID: props.solutionId,
      SOLUTION_VERSION: props.solutionVersion,
      SCHEDULING_INTERVAL_MINUTES: props.schedulingIntervalMinutes.toString(),
      METRICS_UUID: metricsUuidGenerator.metricsUuid,
      HUB_ACCOUNT_ID: Aws.ACCOUNT_ID,
    };

    const mainFunction = new MainLambda(scope, {
      dataLayer: this.dataLayer,
      USER_AGENT_EXTRA: USER_AGENT_EXTRA,
      DEFAULT_TIMEZONE: props.defaultTimezone,
      snsErrorReportingTopic: this.topic,
      principals: props.principals,
      enableAwsOrganizations: props.enableAwsOrganizations,
      factory: props.factory,
      metricsEnv: metricsEnv,
    });

    //ICE Retry lambda
    const iceErrorRetry = new IceErrorRetry(scope, "IceErrorRetry", {
      description: "Handles ICE error retry events, version " + props.solutionVersion,
      dataLayer: this.dataLayer,
      namespace: props.namespace,
      userAgentExtra: USER_AGENT_EXTRA,
      metricsEnv,
      schedulerRoleName: SchedulerRole.roleName(props.namespace),
      stackId: Aws.STACK_ID,
      stackName: Aws.STACK_NAME,
      enableOpsMonitoring: props.enableOpsInsights,
      solutionName: props.solutionName,
      factory: props.factory,
      tagKey: props.tagKey,
      schedulingIntervalMinutes: props.schedulingIntervalMinutes,
      asgScheduledRulesPrefix: props.rulePrefix,
      asgMetadataTagKey: props.asgMetadataTagKey,
      regionalEventBusName: REGIONAL_EVENT_BUS_NAME,
      globalEventBus: this.globalEventBus,
    });

    const schedulingRequestHandler = new SchedulingRequestHandlerLambda(scope, {
      dataLayer: this.dataLayer,
      description: "Handles scheduling requests for Instance Scheduler on AWS, version " + props.solutionVersion,
      namespace: props.namespace,
      memorySizeMB: props.memorySizeMB,
      schedulerRoleName: SchedulerRole.roleName(props.namespace),
      DEFAULT_TIMEZONE: props.defaultTimezone,
      STACK_ID: Aws.STACK_ID,
      STACK_NAME: Aws.STACK_NAME,
      iceErrorRetryQueue: iceErrorRetry.iceRetryQueue,
      asgScheduledRulesPrefix: props.rulePrefix,
      asgMetadataTagKey: props.asgMetadataTagKey,
      USER_AGENT_EXTRA: USER_AGENT_EXTRA,
      enableRdsSnapshots: props.enableRdsSnapshots,
      enableOpsMonitoring: props.enableOpsInsights,
      enableEc2SsmMaintenanceWindows: props.enableEc2SsmMaintenanceWindows,
      tagKey: props.tagKey,
      schedulingIntervalMinutes: props.schedulingIntervalMinutes,
      metricsEnv: metricsEnv,
      solutionName: props.solutionName,
      regionalEventBusName: REGIONAL_EVENT_BUS_NAME,
      globalEventBus: this.globalEventBus,
      factory: props.factory,
    });

    const orchestratorLambda = new SchedulingOrchestrator(scope, {
      description: "scheduling orchestrator for Instance Scheduler on AWS, version " + props.solutionVersion,
      dataLayer: this.dataLayer,
      memorySizeMB: props.orchestratorMemorySizeMB,
      schedulingRequestHandlerLambda: schedulingRequestHandler.lambdaFunction,
      USER_AGENT_EXTRA: USER_AGENT_EXTRA,
      factory: props.factory,
    });

    new HeartbeatMetricReporter(scope, {
      description: "metrics gatherer for Instance Scheduler on AWS, version " + props.solutionVersion,
      dataLayer: this.dataLayer,
      memorySizeMB: 256,
      snsErrorReportingTopic: this.topic,
      snsKmsKey: KmsKeys.get(scope),
      USER_AGENT_EXTRA: USER_AGENT_EXTRA,
      metricsEnv: metricsEnv,
      factory: props.factory,
      schedulingEnabled: props.schedulingEnabled,
      solutionVersion: props.solutionVersion,
      defaultTimezone: props.defaultTimezone,
      enableRdsSnapshots: props.enableRdsSnapshots,
      enableAwsOrganizations: props.enableAwsOrganizations,
      enableEc2SsmMaintenanceWindows: props.enableEc2SsmMaintenanceWindows,
      enableOpsInsights: props.enableOpsInsights,
    });

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
    const schedulerRole = new SchedulerRole(scope, "SchedulerRole", {
      assumedBy: new CompositePrincipal(
        schedulingRequestHandler.lambdaFunction.grantPrincipal,
        resourceRegistration.registrationLambda.grantPrincipal,
        iceErrorRetry.retryIceErrorLambda.grantPrincipal,
        spokeRegistrationLambda.lambdaFunction.grantPrincipal,
      ),
      namespace: props.namespace,
      kmsKeys: props.kmsKeyArns,
      licenseManagerArns: props.licenseManagerArns,
      regionalEventBusName: REGIONAL_EVENT_BUS_NAME,
    });
    this.hubSchedulerRole = schedulerRole;

    new OperationalInsightsDashboard(scope, {
      enabled: props.enableOpsInsights,
      schedulingRequestHandler: schedulingRequestHandler,
      orchestrator: orchestratorLambda,
      schedulingIntervalMinutes: props.schedulingIntervalMinutes,
      namespace: props.namespace,
    });

    new LogInsightsQueries(scope, "LogInsightsQueries", {
      namespace: props.namespace,
      dataLayer: this.dataLayer,
    });

    const cfnSchedulerRule = schedulerRule.node.defaultChild as CfnRule;
    cfnSchedulerRule.addPropertyOverride(
      "State",
      Fn.conditionIf(props.schedulingEnabled.logicalId, "ENABLED", "DISABLED"),
    );

    this.cfnScheduleCustomResourceHandler = mainFunction.lambdaFunction;

    const ec2PolicyCfnResource = schedulerRole.ec2Policy.node.defaultChild as CfnPolicy;
    resourceRegistration.regionRegistrationCfnResource.addDependency(ec2PolicyCfnResource);
    const rdsPolicyCfnResource = schedulerRole.rdsPolicy.node.defaultChild as CfnPolicy;
    resourceRegistration.regionRegistrationCfnResource.addDependency(rdsPolicyCfnResource);

    const asgPolicyCfnResource = schedulerRole.asgPolicy.node.defaultChild as CfnPolicy;
    resourceRegistration.regionRegistrationCfnResource.addDependency(asgPolicyCfnResource);

    const resourceTaggingPolicyCfnResource = schedulerRole.resourceTaggingPolicy.node.defaultChild as CfnPolicy;
    resourceRegistration.regionRegistrationCfnResource.addDependency(resourceTaggingPolicyCfnResource);

    const schedulerRoleCfnResource = schedulerRole.node.defaultChild as CfnRole;
    resourceRegistration.regionRegistrationCfnResource.addDependency(schedulerRoleCfnResource);

    NagSuppressions.addStackSuppressions(Stack.of(scope), [
      {
        id: "AwsSolutions-L1",
        reason: "Python 3.11 is the newest available runtime. This finding is a false positive.",
      },
    ]);
  }
}
