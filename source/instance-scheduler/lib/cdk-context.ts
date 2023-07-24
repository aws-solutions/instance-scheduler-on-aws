// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { App } from "aws-cdk-lib";

export function getSolutionContext(app: App) {
  return {
    solutionId: app.node.tryGetContext("solutionId"),
    solutionName: app.node.tryGetContext("solutionName"),
    appRegAppName: app.node.tryGetContext("appRegApplicationName"),
    appRegSolutionName: app.node.tryGetContext("appRegSolutionName"),
  };
}
