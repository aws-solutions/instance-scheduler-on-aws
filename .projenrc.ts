#!/usr/bin/env node
// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { readFileSync } from "node:fs";
import { Project, YamlFile } from "projen";
import { AwsCdkTypeScriptApp } from "projen/lib/awscdk";
import {
  Jest,
  JestOptions,
  JestReporter,
  NodePackageManager,
  Transform,
  TypescriptConfigOptions,
  UpdateSnapshot,
} from "projen/lib/javascript";
import { PythonProject } from "projen/lib/python";

function main() {
  new InstanceScheduler({ version: "3.1.1", cdkVersion: "2.232.2" }).synth();
}

interface InstanceSchedulerProps {
  readonly version: string;
  readonly cdkVersion: string;
}

class InstanceScheduler extends AwsCdkTypeScriptApp {
  private static readonly solutionId: string = "SO0030";
  private static readonly solutionName: string = "instance-scheduler-on-aws";

  private static readonly cdkContext: { [key: string]: any } = {
    solutionId: this.solutionId,
    solutionName: this.solutionName,
    appRegApplicationName: "AWS-Solutions",
    appRegSolutionName: this.solutionName,
    "instance-scheduler-on-aws-pipeline-source": "codecommit",
  };

  private static readonly tsconfig: TypescriptConfigOptions = {
    include: ["deployment/cdk-solution-helper/**/*.ts"],
    compilerOptions: {
      forceConsistentCasingInFileNames: true,
      lib: ["es2022", "dom"],
      noPropertyAccessFromIndexSignature: false,
      noUncheckedIndexedAccess: false,
      target: "ES2022",
      outDir: "build/cdk.ts.dist",
      rootDir: ".",
    },
  };

  private static readonly prTemplate: string[] = readFileSync("projenrc/PULL_REQUEST_TEMPLATE.md")
    .toString()
    .split("\n");

  private static readonly deps: string[] = [
    "@aws-sdk/client-auto-scaling",
    "@aws-sdk/client-cloudformation",
    "@aws-sdk/client-docdb",
    "@aws-sdk/client-dynamodb",
    "@aws-sdk/util-dynamodb",
    "@aws-sdk/client-ec2",
    "@aws-sdk/client-lambda",
    "@aws-sdk/client-neptune",
    "@aws-sdk/client-rds",
    "@aws-sdk/client-ssm",
    "cdk-nag",
    "source-map-support",
    "uuid",
  ];

  private static readonly devDeps: string[] = [
    "@types/uuid",
    "@typescript-eslint/eslint-plugin",
    "eslint",
    "eslint-config-prettier",
    "eslint-plugin-header",
    "eslint-plugin-import",
    "eslint-plugin-prettier",
    "jest-extended",
    "jest-junit",
    "ts-jest",
  ];

  private static readonly testReportDir: string = "deployment/test-reports";
  private static readonly coverageReportDir: string = "deployment/coverage-reports";

  private static readonly gitignore: string[] = [
    ".idea/",
    ".vscode/",
    ".venv/",
    "*.DS_Store",
    "deployment/open-source/",
    "deployment/global-s3-assets",
    "deployment/regional-s3-assets",
    "__pycache__/",
    "build/",
    "internal/scripts/redpencil",
    ".temp_redpencil",
    "bom.json",
    "internal/scripts/cfn-guard",
    "build",
    "git-info",
    ".env",
    this.testReportDir,
    this.coverageReportDir,
  ];

  private static readonly jestConfigFile: string = "jest.config.json";
  private static readonly testdir: string = "source/instance-scheduler/tests";

  private static readonly jestOptions: JestOptions = {
    junitReporting: false, // we will override
    updateSnapshot: UpdateSnapshot.NEVER,
    configFilePath: this.jestConfigFile,
    jestConfig: {
      reporters: [
        new JestReporter("jest-junit", {
          outputDirectory: this.testReportDir,
          outputName: "cdk-test-report.xml",
        }),
      ],
      roots: [`<rootDir>/${this.testdir}`],
      transform: { "^.+\\.tsx?$": new Transform("ts-jest") },
      setupFilesAfterEnv: ["jest-extended/all"],
    },
  };

  constructor(props: InstanceSchedulerProps) {
    const authorName = "Amazon Web Services";
    const license = "Apache-2.0";

    super({
      appEntrypoint: "instance-scheduler.ts",
      cdkVersion: props.cdkVersion,
      cdkVersionPinning: true,
      context: InstanceScheduler.cdkContext,
      cdkout: "build/cdk.out",
      srcdir: "source",
      testdir: InstanceScheduler.testdir,
      eslint: false,
      tsconfig: InstanceScheduler.tsconfig,
      typescriptVersion: "~5.2.x", //@typescript-eslint/typescript-estree doesn't support 5.3.x yet
      disableTsconfigDev: true,
      projenrcTs: true,
      defaultReleaseBranch: "main",
      npmignoreEnabled: false,
      pullRequestTemplateContents: InstanceScheduler.prTemplate,
      gitignore: InstanceScheduler.gitignore,
      jestOptions: InstanceScheduler.jestOptions,
      githubOptions: { mergify: false, workflows: false },
      name: InstanceScheduler.solutionName,
      description: `Instance Scheduler on AWS (${InstanceScheduler.solutionId})`,
      deps: InstanceScheduler.deps,
      devDeps: InstanceScheduler.devDeps,
      packageManager: NodePackageManager.NPM,
      authorName,
      authorUrl: "https://aws.amazon.com/solutions",
      authorOrganization: true,
      minNodeVersion: "18.0.0",
      license,
    });

    // manage project versioning manually
    this.overrideVersion(props.version);
    // cdk deps should lock to the same version as cdk itself, so they must be specified separately
    this.addDeps(...this.getCdkDeps(props.cdkVersion));
    this.addTestTasks();
    this.addTypescriptFiles("global.d.ts");
    // adding to project props doesn't seem to work as expected
    this.addJestMatch("**/*.test.ts");
    // use default snapshot resolution
    this.removeCustomSnapshotResolver();

    this.addScripts({
      "update-deps": "chmod +x ./update-all-dependencies.sh && exec ./update-all-dependencies.sh",
      "deploy:hub":
        "source .env && npx cdk deploy instance-scheduler-on-aws --require-approval=never --parameters RetainDataAndLogs=$RETAIN_DATA_AND_LOGS --parameters Trace=$ENABLE_DEBUG_LOGGING",
      "destroy:hub": "source .env && npx cdk destroy instance-scheduler-on-aws -f",
      "deploy:spoke":
        "source .env && npx cdk deploy instance-scheduler-on-aws-remote --require-approval=never --parameters InstanceSchedulerAccount=$HUB_ACCOUNT",
      "destroy:spoke": "source .env && npx cdk destroy instance-scheduler-on-aws-remote -f",
    });

    new YamlFile(this, "solution-manifest.yaml", {
      obj: {
        id: InstanceScheduler.solutionId,
        name: InstanceScheduler.solutionName,
        version: `v${props.version}`,
        cloudformation_templates: [
          { template: "instance-scheduler-on-aws.template", main_template: true },
          { template: "instance-scheduler-on-aws-remote.template" },
        ],
        build_environment: { build_image: "aws/codebuild/standard:7.0" },
      },
    });

    const homepage = "https://aws.amazon.com/solutions/implementations/instance-scheduler-on-aws/";

    const commonPythonDevDeps = [
      "black@^24.3.0",
      "flake8@^6.1.0",
      "isort@^5.12.0",
      "mypy@^1.7.1",
      "pytest@^7.4.3",
      "pytest-cov@^4.1.0",
      "tox@^4.11.4",
      "urllib3@^2"
    ];

    const commonPythonProjectOptions: CommonPythonProjectOptions = {
      authorName,
      version: props.version,
      parent: this,
      license,
      homepage,
      devDeps: commonPythonDevDeps,
    };

    new InstanceSchedulerLambdaFunction(commonPythonProjectOptions);
    new InstanceSchedulerCli(commonPythonProjectOptions);
  }

  private overrideVersion(version: string): void {
    const packageFile = this.tryFindObjectFile("package.json");
    if (!packageFile) {
      throw new Error("Error overriding package version");
    }
    packageFile.addOverride("version", version);
  }

  private getCdkDeps(cdkVersion: string): string[] {
    return [
      `@aws-cdk/aws-lambda-python-alpha@${cdkVersion}-alpha.0`,
      `@aws-cdk/aws-servicecatalogappregistry-alpha@${cdkVersion}-alpha.0`,
      `@aws-cdk/aws-neptune-alpha@${cdkVersion}-alpha.0`,
    ];
  }

  private addTestTasks(): void {
    this.addE2ETestTask();

    const prettierTask = this.addTask("test:prettier", { exec: "npx prettier --check ./**/*.ts" });
    const eslintTask = this.addTask("test:eslint", { exec: "npx eslint --max-warnings=0 ." });

    const updateSnapshotsTask = this.addTask("test:update-snapshots", {
      exec: "jest --updateSnapshot --passWithNoTests --coverageProvider=v8 --ci",
    });

    const updateTask = this.tasks.tryFind("test:update");
    if (!updateTask) {
      throw new Error("Error adding subtasks to update task");
    }
    updateTask.reset();
    updateTask.spawn(prettierTask);
    updateTask.spawn(eslintTask);
    updateTask.spawn(updateSnapshotsTask);

    const baseJestCommand = "jest --coverageProvider=v8 --ci";
    const cdkTestTask = this.addTask("test:cdk-tests", { exec: baseJestCommand });

    const cdkTask = this.addTask("test:cdk");

    cdkTask.spawn(prettierTask);
    cdkTask.spawn(eslintTask);
    cdkTask.spawn(cdkTestTask);

    const baseToxCommand = "python -m tox --parallel --exit-and-dump-after 1200";
    const appDir = "source/app";
    const cliDir = "source/cli";
    const appTestTask = this.addTask("test:app", {
      cwd: appDir,
      env: { TOX_PARALLEL_NO_SPINNER: "true" },
      exec: baseToxCommand,
    });
    const cliTestTask = this.addTask("test:cli", {
      cwd: cliDir,
      env: { TOX_PARALLEL_NO_SPINNER: "true" },
      exec: baseToxCommand,
    });

    const testTask = this.tasks.tryFind("test");
    if (!testTask) {
      throw new Error("Error adding subtasks to test task");
    }
    testTask.reset();
    testTask.spawn(cdkTask);
    testTask.spawn(appTestTask);
    testTask.spawn(cliTestTask);

    const testCiTask = this.addTask("test:ci");

    const jestCoverageOptions = `--coverage --coverageDirectory ${InstanceScheduler.coverageReportDir}/cdk-coverage`;
    const cdkTestCiTask = this.addTask("test:cdk-tests:ci", { exec: `${baseJestCommand} ${jestCoverageOptions}` });

    const cdkCiTask = this.addTask("test:cdk:ci");

    cdkCiTask.spawn(prettierTask);
    cdkCiTask.spawn(eslintTask);
    cdkCiTask.spawn(cdkTestCiTask);

    const ciToxOptions = "--skip-missing-interpreters false";
    const appPytestOptions = `--junitxml=../../${InstanceScheduler.testReportDir}/lambda-test-report.xml --cov --cov-report "xml:../../${InstanceScheduler.coverageReportDir}/lambda-coverage.xml"`;
    const appReportFixupCommand = `sed -i -e "s|<source>.*</source>|<source>source/app/instance_scheduler</source>|g" ../../${InstanceScheduler.coverageReportDir}/lambda-coverage.xml`;
    const appTestCiTask = this.addTask("test:app:ci", {
      cwd: appDir,
      env: { TOX_PARALLEL_NO_SPINNER: "true" },
      exec: `${baseToxCommand} ${ciToxOptions} -- ${appPytestOptions} && ${appReportFixupCommand}`,
    });
    const cliPytestOptions = `--junitxml=../../${InstanceScheduler.testReportDir}/cli-test-report.xml --cov --cov-report "xml:../../${InstanceScheduler.coverageReportDir}/cli-coverage.xml"`;
    const cliReportFixupCommand = `sed -i -e "s|<source>.*</source>|<source>source/cli/instance_scheduler_cli</source>|g" ../../${InstanceScheduler.coverageReportDir}/cli-coverage.xml`;
    const cliTestCiTask = this.addTask("test:cli:ci", {
      cwd: cliDir,
      env: { TOX_PARALLEL_NO_SPINNER: "true" },
      exec: `${baseToxCommand} ${ciToxOptions} -- ${cliPytestOptions} && ${cliReportFixupCommand}`,
    });

    testCiTask.spawn(cdkCiTask);
    testCiTask.spawn(appTestCiTask);
    testCiTask.spawn(cliTestCiTask);
  }

  private addE2ETestTask(): void {
    const e2eConfigFile = "source/pipeline/jest.config.json";
    new Jest(this, {
      junitReporting: false, // we will override
      updateSnapshot: UpdateSnapshot.NEVER,
      configFilePath: e2eConfigFile,
      jestConfig: {
        reporters: [
          new JestReporter("jest-junit", {
            outputDirectory: InstanceScheduler.testReportDir,
            outputName: "e2e-test-report.xml",
          }),
        ],
        roots: [`<rootDir>/e2e-tests`],
        setupFilesAfterEnv: ["jest-extended/all"],
        transform: { "^.+\\.tsx?$": new Transform("ts-jest") },
        globalSetup: "./setup.ts",
      },
    });

    this.addTask("e2e-tests", { exec: `node --experimental-vm-modules node_modules/.bin/jest --config ${e2eConfigFile}`, receiveArgs: true });
  }

  private addTypescriptFiles(...files: string[]): void {
    const tsconfig = this.tryFindObjectFile("tsconfig.json");
    if (!tsconfig) {
      throw new Error("Error overriding tsconfig");
    }
    tsconfig.addOverride("files", files);
  }

  private addJestMatch(pattern: string): void {
    if (!this.jest) {
      throw new Error("Error overriding jest matcher");
    }
    this.jest.addTestMatch(pattern);
  }

  private removeCustomSnapshotResolver(): void {
    const jestConfig = this.tryFindObjectFile(InstanceScheduler.jestConfigFile);
    if (!jestConfig) {
      throw new Error("Error overriding jest config");
    }
    jestConfig.addOverride("snapshotResolver", undefined);
  }
}

interface CommonPythonProjectOptions {
  readonly authorName: string;
  readonly license: string;
  readonly version: string;
  readonly parent: Project;
  readonly homepage: string;
  readonly devDeps: string[];
}

class InstanceSchedulerLambdaFunction extends PythonProject {
  constructor(options: CommonPythonProjectOptions) {
    super({
      authorEmail: "",
      moduleName: "instance_scheduler",
      name: "instance_scheduler",
      outdir: "./source/app",
      poetry: true,
      description: "Instance Scheduler on AWS",
      deps: ["python@^3.12"],
      pytest: false,
      ...options,
    });

    const boto3StubsExtras = [
      "autoscaling",
      "cloudwatch",
      "dynamodb",
      "ec2",
      "ecs",
      "lambda",
      "events",
      "logs",
      "rds",
      "resourcegroupstaggingapi",
      "sns",
      "ssm",
      "sts",
      "sqs",
      "events",
    ];

    const motoExtras = ["autoscaling", "dynamodb", "ec2", "logs", "rds", "resourcegroupstaggingapi", "ssm", "events"];

    const boto3Version = "^1.40.4";
    const jmespathVersion = "1.0.1";
    const pythonDateutilVersion = "2.8.2";
    [
      `boto3@${boto3Version}`,
      `boto3-stubs-lite@{version = "${boto3Version}", extras = ${JSON.stringify(boto3StubsExtras)}}`,
      `botocore@${boto3Version}`,
      `botocore-stubs@${boto3Version}`,
      "freezegun@^1.3.1",
      `jmespath@${jmespathVersion}`,
      "pytest-mock@^3.12.0",
      "pytest-runner@^6.0.1",
      "pytest-xdist@^3.5.0",
      `python-dateutil@${pythonDateutilVersion}`,
      `moto@{version = "^5.1.4", extras = ${JSON.stringify(motoExtras)}}`, //locked to 5.0.27 until 5.1.4 releases
      "types-freezegun@^1.1.10",
      `types-jmespath@${jmespathVersion}`,
      `types-python-dateutil@${pythonDateutilVersion}`,
      "types-requests@^2",
      "tzdata@^2023.3",
    ].forEach((spec: string) => this.addDevDependency(spec));

    ["aws-lambda-powertools@^3.4.1", "packaging@^24.0", "pydantic", "urllib3@^2",].forEach((spec: string) => this.addDependency(spec));

    const pyproject = this.tryFindObjectFile("pyproject.toml");
    if (!pyproject) {
      throw new Error("Could not override pyproject.toml");
    }
    pyproject.addOverride("tool.poetry.authors", [options.authorName]);

    const installTask = this.tasks.tryFind("install");
    if (!installTask) {
      throw new Error("Could not override install task");
    }
    installTask.reset();
    installTask.exec("poetry lock && poetry install");
  }
}

class InstanceSchedulerCli extends PythonProject {
  constructor(options: CommonPythonProjectOptions) {
    const boto3Version = "^1.34.1";
    const jmespathVersion = "1.0.1";
    super({
      authorEmail: "",
      moduleName: "instance_scheduler_cli",
      name: "instance_scheduler_cli",
      outdir: "./source/cli",
      poetry: true,
      description: "Instance Scheduler on AWS CLI",
      deps: ["python@^3.11.0", `boto3@${boto3Version}`, `jmespath@^${jmespathVersion}`],
      pytest: false,
      ...options,
    });

    const boto3StubsExtras = ["cloudformation", "lambda"];

    const motoExtras = ["cloudformation", "lambda"];

    [
      `boto3-stubs-lite@{version = "${boto3Version}", extras = ${JSON.stringify(boto3StubsExtras)}}`,
      "jsonschema@~4.17.3", // held back, 4.18.0 is a breaking change
      `moto@{version = "^5.1.4", extras = ${JSON.stringify(motoExtras)}}`,
      `types-jmespath@^${jmespathVersion}`,
      "types-PyYAML@^6.0.12.12",
      "types-requests@2.31.0.6", // held back, need to support urllib3@^1
    ].forEach((spec: string) => this.addDevDependency(spec));

    const pyproject = this.tryFindObjectFile("pyproject.toml");
    if (!pyproject) {
      throw new Error("Could not override pyproject.toml");
    }
    pyproject.addOverride("tool.poetry.authors", [options.authorName]);
    pyproject.addOverride("tool.poetry.scripts.scheduler-cli", "instance_scheduler_cli:__main__");

    const installTask = this.tasks.tryFind("install");
    if (!installTask) {
      throw new Error("Could not override install task");
    }
    installTask.reset();
    installTask.exec("poetry lock && poetry install");
  }
}

main();
