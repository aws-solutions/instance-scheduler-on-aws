// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { Aws, CfnMapping, CfnOutput, Stack, StackProps } from "aws-cdk-lib";
import { RetentionDays } from "aws-cdk-lib/aws-logs";
import { Construct } from "constructs";
import {
  EnabledDisabledParameter,
  EnabledDisabledType,
  ParameterWithLabel,
  YesNoParameter,
  YesNoType,
  addParameterGroup,
  yesNoCondition,
} from "./cfn";
import { CoreScheduler } from "./core-scheduler";
import { FunctionFactory, PythonFunctionFactory } from "./lambda-functions/function-factory";
import { SUPPORTED_TIME_ZONES } from "./time-zones";
import { schedulerIntervalValues } from "./scheduling-interval-mappings";

export interface InstanceSchedulerStackProps extends StackProps {
  readonly solutionId: string;
  readonly solutionName: string;
  readonly solutionVersion: string;
  readonly factory?: FunctionFactory;
}

export class InstanceSchedulerStack extends Stack {
  constructor(scope: Construct, id: string, props: InstanceSchedulerStackProps) {
    super(scope, id, props);

    const scheduleTagKey = new ParameterWithLabel(this, "TagName", {
      label: "Schedule tag key",
      description:
        "The tag key Instance Scheduler will read to determine the schedule for a resource. The value of the tag with this key on a resource specifies the name of the schedule.",
      default: "Schedule",
      minLength: 1,
      maxLength: 127,
    });

    const schedulerIntervalMinutes = new ParameterWithLabel(this, "SchedulerFrequency", {
      label: "Scheduling interval (minutes)",
      type: "Number",
      description: "Interval in minutes between scheduler executions. For EC2 and RDS",
      allowedValues: schedulerIntervalValues,
      default: "5",
    });

    const defaultTimezone = new ParameterWithLabel(this, "DefaultTimezone", {
      label: "Default time zone",
      description: "Default IANA time zone identifier used by schedules that do not specify a time zone.",
      default: "UTC",
      allowedValues: SUPPORTED_TIME_ZONES,
    });

    const enableScheduling = new YesNoParameter(this, "SchedulingActive", {
      label: "Enable scheduling",
      description: 'Set to "No" to disable scheduling for all services.',
      default: YesNoType.Yes,
    });

    addParameterGroup(this, {
      label: `Scheduler (${props.solutionVersion})`,
      parameters: [scheduleTagKey, schedulerIntervalMinutes, defaultTimezone, enableScheduling],
    });

    const enableEc2 = new EnabledDisabledParameter(this, "ScheduleEC2", {
      label: "Enable EC2 scheduling",
      description: "Enable scheduling EC2 instances.",
      default: EnabledDisabledType.Enabled,
    });

    const enableRds = new EnabledDisabledParameter(this, "ScheduleRds", {
      label: "Enable RDS instance scheduling",
      description: "Enable scheduling individual RDS instances (not clusters).",
      default: EnabledDisabledType.Enabled,
    });

    const enableRdsClusters = new EnabledDisabledParameter(this, "EnableRdsClusterScheduling", {
      label: "Enable RDS cluster scheduling",
      description: "Enable scheduling RDS clusters (multi-AZ and Aurora).",
      default: EnabledDisabledType.Enabled,
    });

    const enableNeptune = new EnabledDisabledParameter(this, "ScheduleNeptune", {
      label: "Enable Neptune cluster scheduling",
      description: "Enable scheduling Neptune clusters.",
      default: EnabledDisabledType.Enabled,
    });

    const enableDocDb = new EnabledDisabledParameter(this, "ScheduleDocDb", {
      label: "Enable DocumentDB cluster scheduling",
      description: "Enable scheduling DocumentDB clusters.",
      default: EnabledDisabledType.Enabled,
    });

    const enableAsgs = new EnabledDisabledParameter(this, "ScheduleASGs", {
      label: "Enable AutoScaling Group scheduling",
      description: "Enable scheduling AutoScaling Groups",
      default: EnabledDisabledType.Enabled,
    });

    addParameterGroup(this, {
      label: "Services",
      parameters: [enableEc2, enableRds, enableRdsClusters, enableNeptune, enableDocDb, enableAsgs],
    });

    const startTags = new ParameterWithLabel(this, "StartedTags", {
      label: "Start tags",
      description:
        "Comma-separated list of tag keys and values of the format key=value, key=value,... that are set on started instances. Leave blank to disable.",
      default: "InstanceScheduler-LastAction=Started By {scheduler} {year}-{month}-{day} {hour}:{minute} {timezone}",
    });

    const stopTags = new ParameterWithLabel(this, "StoppedTags", {
      label: "Stop tags",
      description:
        "Comma-separated list of tag keys and values of the format key=value, key=value,... that are set on stopped instances. Leave blank to disable.",
      default: "InstanceScheduler-LastAction=Stopped By {scheduler} {year}-{month}-{day} {hour}:{minute} {timezone}",
    });

    addParameterGroup(this, { label: "Tagging", parameters: [startTags, stopTags] });

    const enableEc2SsmMaintenanceWindows = new YesNoParameter(this, "EnableSSMMaintenanceWindows", {
      label: "Enable EC2 SSM Maintenance Windows",
      description:
        "Allow schedules to specify a maintenance window name. Instance Scheduler will ensure the instance is running during that maintenance window.",
      default: YesNoType.No,
    });

    const kmsKeyArns = new ParameterWithLabel(this, "KmsKeyArns", {
      label: "Kms Key Arns for EC2",
      description:
        "comma-separated list of kms arns to grant Instance Scheduler kms:CreateGrant permissions to provide the EC2 " +
        " service with Decrypt permissions for encrypted EBS volumes." +
        " This allows the scheduler to start EC2 instances with attached encrypted EBS volumes." +
        " provide just (*) to give limited access to all kms keys, leave blank to disable." +
        " For details on the exact policy created, refer to security section of the implementation guide" +
        " (https://aws.amazon.com/solutions/implementations/instance-scheduler-on-aws/)",
      type: "CommaDelimitedList",
      default: "",
    });

    const createRdsSnapshots = new YesNoParameter(this, "CreateRdsSnapshot", {
      label: "Create RDS instance snapshots on stop",
      description: "Create snapshots before stopping RDS instances (not clusters).",
      default: YesNoType.No,
    });

    const scheduledTagKey = new ParameterWithLabel(this, "AsgScheduledTagKey", {
      label: "ASG scheduled tag key",
      description: "Key for the tag Instance Scheduler will add to scheduled AutoScaling Groups",
      default: "scheduled",
    });

    const rulePrefix = new ParameterWithLabel(this, "AsgRulePrefix", {
      label: "ASG action name prefix",
      description:
        "The prefix Instance Scheduler will use when naming Scheduled Scaling actions for AutoScaling Groups. Actions with this prefix will be added and removed by Instance Scheduler as needed.",
      default: "is-",
    });

    addParameterGroup(this, {
      label: "Service-specific",
      parameters: [enableEc2SsmMaintenanceWindows, kmsKeyArns, createRdsSnapshots, scheduledTagKey, rulePrefix],
    });

    const usingAWSOrganizations = new YesNoParameter(this, "UsingAWSOrganizations", {
      label: "Use AWS Organizations",
      description: "Deploy resources to enable automatic spoke stack registration using AWS Organizations.",
      default: YesNoType.No,
    });

    const namespace = new ParameterWithLabel(this, "Namespace", {
      label: "Namespace",
      description: "Unique identifier per deployment. Cannot contain spaces.",
      default: "default",
    });

    const principals = new ParameterWithLabel(this, "Principals", {
      label: "Organization ID/remote account IDs",
      type: "CommaDelimitedList",
      description:
        "(Required) If using AWS Organizations, provide the Organization ID. Eg. o-xxxxyyy. " +
        "Else, provide a comma-separated list of spoke account ids to schedule. Eg.: 1111111111, 2222222222 or {param: ssm-param-name}",
      default: "",
    });

    const regions = new ParameterWithLabel(this, "Regions", {
      label: "Region(s)",
      type: "CommaDelimitedList",
      description:
        "Comma-separated List of regions in which resources should be scheduled. Leave blank for current region only.",
      default: "",
    });

    const scheduleLambdaAccount = new YesNoParameter(this, "ScheduleLambdaAccount", {
      label: "Enable hub account scheduling",
      description: "Enable scheduling in this account.",
      default: YesNoType.Yes,
    });

    addParameterGroup(this, {
      label: "Account structure",
      parameters: [usingAWSOrganizations, namespace, principals, regions, scheduleLambdaAccount],
    });

    const logRetentionValues: RetentionDays[] = [
      RetentionDays.ONE_DAY,
      RetentionDays.THREE_DAYS,
      RetentionDays.FIVE_DAYS,
      RetentionDays.ONE_WEEK,
      RetentionDays.TWO_WEEKS,
      RetentionDays.ONE_MONTH,
      RetentionDays.TWO_MONTHS,
      RetentionDays.THREE_MONTHS,
      RetentionDays.FOUR_MONTHS,
      RetentionDays.FIVE_MONTHS,
      RetentionDays.SIX_MONTHS,
      RetentionDays.ONE_YEAR,
      RetentionDays.THIRTEEN_MONTHS,
      RetentionDays.EIGHTEEN_MONTHS,
      RetentionDays.TWO_YEARS,
      RetentionDays.FIVE_YEARS,
      RetentionDays.TEN_YEARS,
    ];
    const logRetentionDays = new ParameterWithLabel(this, "LogRetentionDays", {
      label: "Log retention period (days)",
      description: "Retention period in days for logs.",
      type: "Number",
      allowedValues: logRetentionValues.map((value: number) => value.toString()),
      default: RetentionDays.ONE_MONTH,
    });

    const enableDebugLogging = new YesNoParameter(this, "Trace", {
      label: "Enable CloudWatch debug Logs",
      description: "Enable debug-level logging in CloudWatch Logs.",
      default: YesNoType.No,
    });

    const enableOpsMonitoring = new EnabledDisabledParameter(this, "OpsMonitoring", {
      label: "Operational Monitoring",
      description: "Deploy operational metrics and an Ops Monitoring Dashboard to Cloudwatch",
      default: EnabledDisabledType.Enabled,
    });

    addParameterGroup(this, {
      label: "Monitoring",
      parameters: [logRetentionDays, enableDebugLogging, enableOpsMonitoring],
    });

    const memorySizeValues = ["128", "384", "512", "640", "768", "896", "1024", "1152", "1280", "1408", "1536"];
    const memorySize = new ParameterWithLabel(this, "MemorySize", {
      label: "SchedulingRequestHandler Memory size (MB)",
      description:
        "Memory size of the Lambda function that schedules EC2 and RDS resources. Increase if you are experiencing high memory usage or timeouts.",
      type: "Number",
      allowedValues: memorySizeValues,
      default: 512,
    });

    const asgHandlerMemorySize = new ParameterWithLabel(this, "AsgMemorySize", {
      label: "AsgHandler Memory size (MB)",
      description:
        "Memory size of the Lambda function that schedules ASG resources. Increase if you are experiencing high memory usage or timeouts.",
      type: "Number",
      allowedValues: memorySizeValues,
      default: 512,
    });

    const orchestratorMemorySize = new ParameterWithLabel(this, "OrchestratorMemorySize", {
      label: "Orchestrator Memory size (MB)",
      description:
        "Memory size of the Lambda functions that coordinate multi-account, multi-region scheduling for the other " +
        "scheduling lambdas. Increase if you are experiencing high memory usage or timeouts.",
      type: "Number",
      allowedValues: memorySizeValues,
      default: 512,
    });

    const enableDdbDeletionProtection = new EnabledDisabledParameter(this, "ddbDeletionProtection", {
      label: "Protect DynamoDB Tables",
      description:
        "Enable deletion protection for DynamoDB tables used by the solution. This will cause the tables to be retained" +
        " when deleting this stack. To delete the tables when deleting this stack, first disable this parameter.",
      default: EnabledDisabledType.Enabled,
    });

    addParameterGroup(this, {
      label: "Other",
      parameters: [memorySize, asgHandlerMemorySize, orchestratorMemorySize, enableDdbDeletionProtection],
    });

    const sendAnonymizedUsageMetricsMapping = new CfnMapping(this, "Send");
    const anonymizedUsageKey1 = "AnonymousUsage";
    const anonymizedUsageKey2 = "Data";
    sendAnonymizedUsageMetricsMapping.setValue(anonymizedUsageKey1, anonymizedUsageKey2, YesNoType.Yes);
    const sendAnonymizedMetrics = yesNoCondition(
      this,
      "AnonymizedMetricsEnabled",
      sendAnonymizedUsageMetricsMapping.findInMap(anonymizedUsageKey1, anonymizedUsageKey2),
    );

    const factory = props.factory ?? new PythonFunctionFactory();

    const coreScheduler = new CoreScheduler(this, {
      solutionName: props.solutionName,
      solutionVersion: props.solutionVersion,
      solutionId: props.solutionId,
      memorySizeMB: memorySize.valueAsNumber,
      asgMemorySizeMB: asgHandlerMemorySize.valueAsNumber,
      orchestratorMemorySizeMB: orchestratorMemorySize.valueAsNumber,
      logRetentionDays: logRetentionDays.valueAsNumber,
      principals: principals.valueAsList,
      schedulingEnabled: enableScheduling.getCondition(),
      schedulingIntervalMinutes: schedulerIntervalMinutes.valueAsNumber,
      namespace: namespace.valueAsString,
      sendAnonymizedMetrics,
      enableDebugLogging: enableDebugLogging.getCondition(),
      tagKey: scheduleTagKey.valueAsString,
      defaultTimezone: defaultTimezone.valueAsString,
      enableEc2: enableEc2.getCondition(),
      enableRds: enableRds.getCondition(),
      enableRdsClusters: enableRdsClusters.getCondition(),
      enableNeptune: enableNeptune.getCondition(),
      enableDocdb: enableDocDb.getCondition(),
      enableRdsSnapshots: createRdsSnapshots.getCondition(),
      regions: regions.valueAsList,
      enableSchedulingHubAccount: scheduleLambdaAccount.getCondition(),
      enableEc2SsmMaintenanceWindows: enableEc2SsmMaintenanceWindows.getCondition(),
      startTags: startTags.valueAsString,
      stopTags: stopTags.valueAsString,
      enableAwsOrganizations: usingAWSOrganizations.getCondition(),
      enableOpsInsights: enableOpsMonitoring.getCondition(),
      kmsKeyArns: kmsKeyArns.valueAsList,
      factory,
      enableDdbDeletionProtection: enableDdbDeletionProtection.getCondition(),
      enableAsgs: enableAsgs.getCondition(),
      scheduledTagKey: scheduledTagKey.valueAsString,
      rulePrefix: rulePrefix.valueAsString,
    });

    new CfnOutput(this, "AccountId", {
      value: Aws.ACCOUNT_ID,
      description: "Hub Account ID - for use in corresponding spoke stack parameter",
    });

    new CfnOutput(this, "ConfigurationTable", {
      value: coreScheduler.configTable.tableArn,
      description: "DynamoDB Configuration table ARN",
    });

    new CfnOutput(this, "IssueSnsTopicArn", {
      value: coreScheduler.topic.topicArn,
      description: "Notification SNS Topic ARN",
    });

    new CfnOutput(this, "SchedulerRoleArn", {
      value: coreScheduler.hubSchedulerRole.roleArn,
      description: "Scheduler role ARN",
    });

    new CfnOutput(this, "ServiceInstanceScheduleServiceToken", {
      value: coreScheduler.cfnScheduleCustomResourceHandler.functionArn,
      description: "Custom resource provider ARN - use as ServiceToken property value for CloudFormation Schedules",
    });
  }
}
