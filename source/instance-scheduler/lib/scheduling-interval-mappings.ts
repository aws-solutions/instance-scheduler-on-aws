// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { CfnMapping, CfnMappingProps } from "aws-cdk-lib";
import { Construct } from "constructs";

export const schedulerIntervalValues = ["1", "2", "5", "10", "15", "30", "60"];
export class SchedulingIntervalToCron extends CfnMapping {
  private readonly key = "IntervalMinutesToCron";
  constructor(scope: Construct, id: string, props: CfnMappingProps) {
    super(scope, id, props);
    this.setValue(this.key, "1", "cron(0/1 * * * ? *)");
    this.setValue(this.key, "2", "cron(0/2 * * * ? *)");
    this.setValue(this.key, "5", "cron(0/5 * * * ? *)");
    this.setValue(this.key, "10", "cron(0/10 * * * ? *)");
    this.setValue(this.key, "15", "cron(0/15 * * * ? *)");
    this.setValue(this.key, "30", "cron(0/30 * * * ? *)");
    this.setValue(this.key, "60", "cron(0 0/1 * * ? *)");
  }

  getMapping(schedulingInterval: string) {
    return this.findInMap(this.key, schedulingInterval);
  }
}

export class SchedulingIntervalToSeconds extends CfnMapping {
  private readonly key = "MinutesToSeconds";
  constructor(scope: Construct, id: string, props: CfnMappingProps) {
    super(scope, id, props);
    this.setValue(this.key, "1", "60");
    this.setValue(this.key, "2", "120");
    this.setValue(this.key, "5", "300");
    this.setValue(this.key, "10", "600");
    this.setValue(this.key, "15", "900");
    this.setValue(this.key, "30", "1800");
    this.setValue(this.key, "60", "3600");
  }

  getMapping(schedulingInterval: string) {
    return this.findInMap(this.key, schedulingInterval);
  }
}
