#!/usr/bin/env node
// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { readFileSync } from "node:fs";
import { awscdk } from "projen";
import { JestReporter, NodePackageManager, Transform, UpdateSnapshot } from "projen/lib/javascript";

const cdkVersion = "2.87.0";
const solutionId = "SO0030";
const solutionName = "instance-scheduler-on-aws";

const project = new awscdk.AwsCdkTypeScriptApp({
  projenrcTs: true,
  minNodeVersion: "18.0.0",
  name: "instance-scheduler-on-aws",
  description: `Instance Scheduler on AWS (${solutionId})`,
  authorName: "Amazon Web Services",
  authorUrl: "https://aws.amazon.com/solutions",
  authorOrganization: true,
  defaultReleaseBranch: "main",
  packageManager: NodePackageManager.NPM,
  majorVersion: 1,
  srcdir: "source",
  testdir: "source/instance-scheduler/tests",
  cdkVersion,
  cdkout: "build/cdk.out",
  appEntrypoint: "instance-scheduler.ts",
  jestOptions: {
    configFilePath: "jest.config.json",
    updateSnapshot: UpdateSnapshot.NEVER,
    junitReporting: false, // we will override
    jestConfig: {
      roots: ["<rootDir>/source/instance-scheduler/tests"],
      transform: { "^.+\\.tsx?$": new Transform("ts-jest") },
      reporters: [
        new JestReporter("jest-junit", {
          outputDirectory: "deployment/test-reports",
          outputName: "cdk-test-report.xml",
        }),
      ],
    },
  },
  context: {
    solutionId,
    solutionName,
    appRegApplicationName: "AWS-Solutions",
    appRegSolutionName: solutionName,
    "instance-scheduler-on-aws-pipeline-source": "codecommit",
  },
  deps: [
    `@aws-cdk/aws-lambda-python-alpha@^${cdkVersion}-alpha.0`,
    `@aws-cdk/aws-servicecatalogappregistry-alpha@^${cdkVersion}-alpha.0`,
    "@aws-sdk/client-dynamodb",
    "@aws-sdk/client-ec2",
    "@aws-sdk/client-rds",
    "@aws-sdk/client-ssm",
    "@aws-solutions-constructs/aws-lambda-dynamodb",
    "cdk-nag",
    "constructs",
    "source-map-support",
  ],
  devDeps: [
    "@types/jest",
    "@types/node",
    "@typescript-eslint/eslint-plugin",
    "eslint",
    "eslint-config-prettier",
    "eslint-plugin-header",
    "eslint-plugin-import",
    "eslint-plugin-prettier",
    "jest-extended",
    "jest-junit",
    "ts-jest",
  ],
  githubOptions: {
    workflows: false,
  },
  pullRequestTemplateContents: readFileSync("projenrc/PULL_REQUEST_TEMPLATE.md").toString().split("\n"),
  eslint: false,
  autoMerge: false,
  npmignoreEnabled: false,
  license: "Apache-2.0",
  disableTsconfigDev: true,
  tsconfig: {
    compilerOptions: {
      rootDir: ".",
      noUnusedLocals: true,
      forceConsistentCasingInFileNames: true,
      lib: ["es2022", "dom"],
      noEmitOnError: true,
      noPropertyAccessFromIndexSignature: false, // TODO: enable
      noUncheckedIndexedAccess: false, // TODO: enable
      target: "ES2022",
      allowJs: false,
      outDir: "build/cdk.ts.dist",
    },
    include: ["source/pipeline/**/*.ts", "deployment/cdk-solution-helper/**/*.ts"],
    exclude: ["node_modules"],
  },
  gitignore: [
    "__pycache__/",
    "*.py[cod]",
    "*$py.class",
    "*node_modules*",
    "*.so",
    "*.pyc",
    ".Python",
    "env/",
    "build/",
    "develop-eggs/",
    "dist/",
    "downloads/",
    "eggs/",
    ".eggs/",
    "lib64/",
    "parts/",
    "sdist/",
    "var/",
    "*.egg-info/",
    ".installed.cfg",
    "*.egg",
    ".idea/",
    "*.manifest",
    "*.spec",
    "pip-log.txt",
    "pip-delete-this-directory.txt",
    "htmlcov/",
    ".tox/",
    ".coverage",
    ".coverage.*",
    ".cache",
    "nosetests.xml",
    "coverage.xml",
    "*,cover",
    ".hypothesis/",
    "deployment/coverage-reports/",
    "deployment/test-reports/",
    "coverage/",
    "*.mo",
    "*.pot",
    "*.log",
    "local_settings.py",
    "instance/",
    ".webassets-cache",
    ".scrapy",
    "docs/_build/",
    "target/",
    ".ipynb_checkpoints",
    ".python-version",
    "celerybeat-schedule",
    ".env",
    ".venv/",
    "venv/",
    "ENV/",
    ".spyderproject",
    ".ropeproject",
    "*cdk.out*",
    "*.js",
    "!.eslintrc.js",
    "*regional-s3-assets*",
    "*staging*",
    "*global-s3-assets*",
    ".DS_Store",
    ".pytest_cache",
    ".mypy_cache",
    "*.zip",
    "deployment/open-source",
    "deployment/dist",
    "source/deploy",
    "source/code/sample_events",
    ".vscode",
    "__pycache__",
    "**/cdk-test-report.xml",
  ],
});

project.addTask("e2e-tests", { exec: "jest --config source/pipeline/jest.config.ts", receiveArgs: true });

const prettierTask = project.addTask("test:prettier", { exec: "npx prettier --check ./**/*.ts" });
const eslintTask = project.addTask("test:eslint", { exec: "npx eslint --max-warnings=0 ." });
const cdkTestTask = project.addTask("test:cdk", {
  exec: "jest --coverageProvider=v8 --ci",
});
const appTestTask = project.addTask("test:app", {
  cwd: "source/app",
  exec: "python -m tox --parallel --exit-and-dump-after 1200",
});
const cliTestTask = project.addTask("test:cli", {
  cwd: "source/cli",
  exec: "python -m tox --parallel --exit-and-dump-after 1200",
});

const testTask = project.tasks.tryFind("test");
testTask?.reset();
testTask?.spawn(prettierTask);
testTask?.spawn(eslintTask);
testTask?.spawn(cdkTestTask);
testTask?.spawn(appTestTask);
testTask?.spawn(cliTestTask);

const testCiTask = project.addTask("test:ci");

const cdkTestCiTask = project.addTask("test:cdk:ci", {
  exec: "jest --coverageProvider=v8 --ci --coverage --coverageDirectory deployment/coverage-reports/cdk-coverage",
});
const appTestCiTask = project.addTask("test:app:ci", {
  cwd: "source/app",
  env: { TOX_PARALLEL_NO_SPINNER: "true" },
  exec: 'python -m tox --parallel --exit-and-dump-after 1200 --skip-missing-interpreters false -- --junitxml=../../deployment/test-reports/lambda-test-report.xml --cov --cov-report "xml:../../deployment/coverage-reports/lambda-coverage.xml" && sed -i -e "s|<source>.*</source>|<source>source/app/instance_scheduler</source>|g" ../../deployment/coverage-reports/lambda-coverage.xml',
});
const cliTestCiTask = project.addTask("test:cli:ci", {
  cwd: "source/cli",
  env: { TOX_PARALLEL_NO_SPINNER: "true" },
  exec: 'python -m tox --parallel --exit-and-dump-after 1200 --skip-missing-interpreters false -- --junitxml=../../deployment/test-reports/cli-test-report.xml --cov --cov-report "xml:../../deployment/coverage-reports/cli-coverage.xml" && sed -i -e "s|<source>.*</source>|<source>source/cli/instance_scheduler_cli</source>|g" ../../deployment/coverage-reports/cli-coverage.xml',
});

testCiTask.spawn(prettierTask);
testCiTask.spawn(eslintTask);
testCiTask.spawn(cdkTestCiTask);
testCiTask.spawn(appTestCiTask);
testCiTask.spawn(cliTestCiTask);

project.tryFindObjectFile("tsconfig.json")?.addOverride("files", ["global.d.ts"]);

// adding to project props doesn't seem to work as expected
project.jest?.addTestMatch("**/*.test.ts");

// use default snapshot resolution
project.tryFindObjectFile("jest.config.json")?.addOverride("snapshotResolver", undefined);

project.tryFindObjectFile("package.json")?.addOverride("version", "1.5.1");

project.synth();
