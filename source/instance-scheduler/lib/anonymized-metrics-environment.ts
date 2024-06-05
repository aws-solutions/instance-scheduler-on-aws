// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
export interface AnonymizedMetricsEnvironment {
  // environment variables for the metrics.py singleton service
  // omitting these variables will disable metrics reporting
  SEND_METRICS: string;
  METRICS_URL: string;
  SOLUTION_ID: string;
  SOLUTION_VERSION: string;
  SCHEDULING_INTERVAL_MINUTES: string;
  METRICS_UUID: string;
}
