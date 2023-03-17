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
        outputDirectory: "../../deployment/test-reports",
        outputName: "e2e-test-report.xml",
      },
    ],
  ],
};
