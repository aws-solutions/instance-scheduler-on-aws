// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { Construct } from "constructs";
import { CfnQueryDefinition } from "aws-cdk-lib/aws-logs";
import { InstanceSchedulerDataLayer } from "../instance-scheduler-data-layer";
import { ISLogGroups } from "./log-groups";

export interface LogInsightsQueryProps {
  namespace: string;
  dataLayer: InstanceSchedulerDataLayer;
}

export class LogInsightsQueries extends Construct {
  constructor(scope: Construct, id: string, props: LogInsightsQueryProps) {
    super(scope, id);

    const query_root_folder = `InstanceScheduler-${props.namespace}/`;

    new CfnQueryDefinition(this, "SchedulingHistory", {
      name: query_root_folder + "SchedulingHistory",
      logGroupNames: [ISLogGroups.schedulingLogGroup(scope).logGroupName],
      queryString: `# Instance Scheduler Scheduling Decision Summary
# Remember to set the time range for this log query in the widget above
fields @timestamp, resource, decision, reason, action_taken, action_info
| filter log_type = 'scheduling_result'

# Uncomment and edit the following filters to restrict queries only to specific accounts/regions/instances/schedules/actions
#| filter resource like /arn-fragment/
#| filter instance_type = "instance_class"
#| filter xray_trace_id = "id"

| filter action_taken in ['Started', 'Stopped', 'Hibernated', 'Configured', 'Error', 'None']

| sort @timestamp desc`,
    });

    new CfnQueryDefinition(this, "ResourceRegistration", {
      name: query_root_folder + "RegistrationEvents",
      logGroupNames: [ISLogGroups.adminLogGroup(scope).logGroupName],
      queryString: `# Instance Scheduler Scheduling Decision Summary
# Remember to set the time range for this log query in the widget above
fields @timestamp, message
| filter context = "registration"

# Uncomment and edit the following filters to restrict queries only to specific accounts/regions/instances/schedules/actions
#| filter instance like /Instance_id/
#| filter region = "region_name"
#| filter account = "account_id"

| sort @timestamp desc`,
    });

    new CfnQueryDefinition(this, "Errors", {
      name: query_root_folder + "Errors",
      logGroupNames: [
        ISLogGroups.schedulingLogGroup(scope).logGroupName,
        ISLogGroups.adminLogGroup(scope).logGroupName,
      ],
      queryString: `# Instance Scheduler Scheduling Decision Summary
# Remember to set the time range for this log query in the widget above
fields @timestamp, message
| filter level in ['WARN', 'ERROR', 'CRITICAL']

| sort @timestamp desc`,
    });
  }
}
