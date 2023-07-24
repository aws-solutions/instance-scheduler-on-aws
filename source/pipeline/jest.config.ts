// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
module.exports = {
  roots: ["<rootDir>/e2e-tests"],
  testMatch: ["**/*.test.ts"],
  transform: {
    "^.+\\.tsx?$": "ts-jest",
  },
  reporters: [
    "default",
    [
      "jest-junit",
      {
        outputDirectory: "deployment/test-reports",
        outputName: "e2e-test-report.xml",
      },
    ],
  ],
  setupFilesAfterEnv: ["jest-extended/all"],
};
