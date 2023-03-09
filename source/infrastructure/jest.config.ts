module.exports = {
  roots: ["<rootDir>/tests", "<rootDir>/lib"],
  testMatch: ["**/*.test.ts"],
  transform: {
    "^.+\\.tsx?$": "ts-jest",
  },
  reporters: [
    "default",
    [
      "jest-junit",
      {
        outputDirectory: "../../deployment/test-reports",
        outputName: "cdk-test-report.xml",
      },
    ],
  ],
};
