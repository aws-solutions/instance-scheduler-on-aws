// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { execSync } from "child_process";
import {
  createPeriod,
  createSchedule,
  deleteConfigTableItemsWithNamePrefix,
  getConfigTableItem,
} from "./utils/cli-utils";
import { v4 } from "uuid";

const hubStack = process.env["HUB_STACK"];
const dynamoDbItemNamePrefix = `cli-test-${v4()}`;
const reusablePeriodName = `${dynamoDbItemNamePrefix}-reusable-period`;

beforeAll(async () => {
  await createPeriod({
    name: reusablePeriodName,
    description: "cli-test",
    begintime: "23:00",
    endtime: "23:59",
  });
});

afterAll(async () => {
  await deleteConfigTableItemsWithNamePrefix("period", dynamoDbItemNamePrefix);
  await deleteConfigTableItemsWithNamePrefix("schedule", dynamoDbItemNamePrefix);
});

test("should successfully print usage instructions", () => {
  const result = execSync("python -m instance_scheduler_cli");
  expect(result.toString()).toContain("usage: scheduler-cli");
});

describe("period", () => {
  // create-period
  test("should successfully create period with all values using the create-period cli command", async () => {
    const periodName = `${dynamoDbItemNamePrefix}-create-period-all-values`;

    execSync(
      `python -m instance_scheduler_cli create-period` +
        ` --stack ${hubStack}` +
        ` --name ${periodName}` +
        ` --begintime 00:00` +
        ` --endtime 12:00` +
        ` --description cli-test` +
        ` --monthdays 1` +
        ` --months "*"` +
        ` --weekdays mon-fri`,
    );
    expect(await getConfigTableItem("period", periodName)).toEqual({
      type: "period",
      name: periodName,
      description: "cli-test",
      begintime: "00:00",
      endtime: "12:00",
      weekdays: new Set(["mon-fri"]),
      monthdays: new Set(["1"]),
      months: new Set(["*"]),
    });
  }, 10_000);

  test("should successfully create period with min values using the create-period cli command", async () => {
    const periodName = `${dynamoDbItemNamePrefix}-create-period-min-values`;

    execSync(
      `python -m instance_scheduler_cli create-period` +
        ` --stack ${hubStack}` +
        ` --name ${periodName}` +
        ` --endtime 12:00`,
    );
    expect(await getConfigTableItem("period", periodName)).toEqual({
      type: "period",
      name: periodName,
      endtime: "12:00",
    });
  }, 10_000);

  test("should error from create-period cli command when period already exists", async () => {
    const periodName = `${dynamoDbItemNamePrefix}-create-period-already-exists`;
    await createPeriod({
      name: periodName,
      description: "cli-test",
      begintime: "00:00",
      endtime: "12:00",
    });

    expect(() =>
      execSync(
        `python -m instance_scheduler_cli create-period` +
          ` --stack ${hubStack}` +
          ` --name ${periodName}` +
          ` --description cli-test` +
          ` --begintime 00:00` +
          ` --endtime 12:00`,
      ),
    ).toThrow("Command failed:");
  }, 10_000);

  // delete-period
  test("should successfully delete period with delete-period cli command", async () => {
    const periodName = `${dynamoDbItemNamePrefix}-delete-period`;
    await createPeriod({
      name: periodName,
      description: "cli-test",
      begintime: "00:00",
      endtime: "12:00",
    });

    const response = execSync(
      `python -m instance_scheduler_cli delete-period --stack ${hubStack} --name ${periodName}`,
    );
    expect(JSON.parse(response.toString()).Period).toEqual(periodName);
    expect(async () => await getConfigTableItem("period", periodName)).rejects.toThrow("Did not find item");
  }, 10_000);

  test("should error from delete-period cli command when period does not exist", () => {
    const periodName = `${dynamoDbItemNamePrefix}-delete-period-does-not-exist`;

    expect(() =>
      execSync(`python -m instance_scheduler_cli delete-period --stack ${hubStack} --name ${periodName}`),
    ).toThrow("Command failed:");
  });

  // describe-periods
  test("should successfully describe all periods with describe-periods cli command", () => {
    const response = execSync(`python -m instance_scheduler_cli describe-periods --stack ${hubStack}`);
    expect(JSON.parse(response.toString()).Periods).toEqual(expect.any(Array));
  });

  test("should successfully describe single period with describe-periods cli command", async () => {
    const periodName = `${dynamoDbItemNamePrefix}-describe-single-period`;
    await createPeriod({
      name: periodName,
      description: "cli-test",
      begintime: "00:00",
      endtime: "12:00",
    });

    const response = execSync(
      `python -m instance_scheduler_cli describe-periods --stack ${hubStack} --name ${periodName}`,
    );
    expect(JSON.parse(response.toString()).Periods[0]).toEqual({
      Type: "period",
      Name: periodName,
      Description: "cli-test",
      Begintime: "00:00",
      Endtime: "12:00",
    });
  }, 10_000);

  test("should error from describe-period cli command when period does not exist", () => {
    const periodName = `${dynamoDbItemNamePrefix}-describe-periods-does-not-exist`;

    expect(() =>
      execSync(`python -m instance_scheduler_cli describe-periods --stack ${hubStack} --name ${periodName}`),
    ).toThrow("Command failed:");
  });

  // update-period
  test("should successfully update period with update-period cli command", async () => {
    const periodName = `${dynamoDbItemNamePrefix}-update-period`;
    await createPeriod({
      name: periodName,
      description: "cli-test",
      begintime: "00:00",
      endtime: "12:00",
    });

    const response = execSync(
      `python -m instance_scheduler_cli update-period --stack ${hubStack} --name ${periodName} --weekdays sat-sun`,
    );
    expect(JSON.parse(response.toString()).Period).toEqual({
      Type: "period",
      Name: periodName,
      Weekdays: ["sat-sun"],
    });
    expect(await getConfigTableItem("period", periodName)).toEqual({
      type: "period",
      name: periodName,
      weekdays: new Set(["sat-sun"]),
    });
  }, 10_000);

  test("should error from update-period cli command when period does not exist", () => {
    const periodName = `${dynamoDbItemNamePrefix}-update-period-does-not-exist`;

    expect(() =>
      execSync(
        `python -m instance_scheduler_cli update-period --stack ${hubStack} --name ${periodName} --weekdays sat-sun`,
      ),
    ).toThrow("Command failed:");
  });
});

describe("schedule", () => {
  // create-schedule
  test("should successfully create schedule with all values using the create-schedule cli command", async () => {
    const scheduleName = `${dynamoDbItemNamePrefix}-create-schedule-all-values`;

    execSync(
      `python -m instance_scheduler_cli create-schedule` +
        ` --stack ${hubStack}` +
        ` --name ${scheduleName}` +
        ` --periods ${reusablePeriodName}` +
        ` --description test` +
        ` --timezone UTC` +
        ` --override-status running` +
        ` --do-not-stop-new-instances` +
        ` --ssm-maintenance-window test` +
        ` --retain-running` +
        ` --enforced` +
        ` --hibernate`,
    );
    expect(await getConfigTableItem("schedule", scheduleName)).toEqual({
      description: "test",
      enforced: true,
      hibernate: true,
      name: scheduleName,
      override_status: "running",
      periods: new Set([reusablePeriodName]),
      retain_running: true,
      ssm_maintenance_window: new Set(["test"]),
      stop_new_instances: false,
      timezone: "UTC",
      type: "schedule",
    });
  }, 10_000);

  test("should successfully create schedule with min values using the create-schedule cli command", async () => {
    const scheduleName = `${dynamoDbItemNamePrefix}-create-schedule-min-values`;

    execSync(
      `python -m instance_scheduler_cli create-schedule` +
        ` --stack ${hubStack}` +
        ` --name ${scheduleName}` +
        ` --periods ${reusablePeriodName}`,
    );
    expect(await getConfigTableItem("schedule", scheduleName)).toEqual({
      type: "schedule",
      enforced: false,
      hibernate: false,
      name: scheduleName,
      periods: new Set([reusablePeriodName]),
      retain_running: false,
      stop_new_instances: true,
    });
  }, 10_000);

  test("should error from create-schedule cli command when schedule already exists", async () => {
    const scheduleName = `${dynamoDbItemNamePrefix}-create-schedule-already-exists`;
    await createSchedule({
      name: scheduleName,
      description: "cli-test",
      periods: new Set([reusablePeriodName]),
    });

    expect(() =>
      execSync(
        `python -m instance_scheduler_cli create-schedule` +
          ` --stack ${hubStack}` +
          ` --name ${scheduleName}` +
          ` --periods ${reusablePeriodName}`,
      ),
    ).toThrow("Command failed:");
  }, 10_000);

  // delete-schedule
  test("should successfully delete schedule with delete-schedule cli command", async () => {
    const scheduleName = `${dynamoDbItemNamePrefix}-delete-schedule`;
    await createSchedule({
      name: scheduleName,
      description: "cli-test",
      periods: new Set([reusablePeriodName]),
    });

    const response = execSync(
      `python -m instance_scheduler_cli delete-schedule --stack ${hubStack} --name ${scheduleName}`,
    );
    expect(JSON.parse(response.toString()).Schedule).toEqual(scheduleName);
    expect(async () => await getConfigTableItem("schedule", scheduleName)).rejects.toThrow("Did not find item");
  }, 10_000);

  test("should error from delete-schedule cli command when schedule does not exist", () => {
    const scheduleName = `${dynamoDbItemNamePrefix}-delete-schedule-does-not-exist`;

    expect(() =>
      execSync(`python -m instance_scheduler_cli delete-schedule --stack ${hubStack} --name ${scheduleName}`),
    ).toThrow("Command failed:");
  });

  // describe-schedule
  test("should successfully describe all schedules with describe-schedules cli command", () => {
    const response = execSync(`python -m instance_scheduler_cli describe-schedules --stack ${hubStack}`);
    expect(JSON.parse(response.toString()).Schedules).toEqual(expect.any(Array));
  });

  test("should successfully describe single schedule with describe-schedules cli command", async () => {
    const scheduleName = `${dynamoDbItemNamePrefix}-describe-single-schedule`;
    await createSchedule({
      name: scheduleName,
      description: "cli-test",
      periods: new Set([reusablePeriodName]),
    });

    const response = execSync(
      `python -m instance_scheduler_cli describe-schedules --stack ${hubStack} --name ${scheduleName}`,
    );
    expect(JSON.parse(response.toString()).Schedules[0]).toEqual({
      Type: "schedule",
      Name: scheduleName,
      Description: "cli-test",
      Periods: [reusablePeriodName],
    });
  }, 10_000);

  test("should error from describe-schedule cli command when schedule does not exist", () => {
    const scheduleName = `${dynamoDbItemNamePrefix}-describe-schedules-does-not-exist`;

    expect(() =>
      execSync(`python -m instance_scheduler_cli describe-schedules --stack ${hubStack} --name ${scheduleName}`),
    ).toThrow("Command failed:");
  });

  // update-schedule
  test("should successfully update schedule with update-schedule cli command", async () => {
    const scheduleName = `${dynamoDbItemNamePrefix}-update-schedule`;
    await createSchedule({
      name: scheduleName,
      description: "cli-test",
      periods: new Set([reusablePeriodName]),
    });

    const response = execSync(
      `python -m instance_scheduler_cli update-schedule` +
        ` --stack ${hubStack}` +
        ` --name ${scheduleName}` +
        ` --periods ${reusablePeriodName}` +
        ` --description updated-description`,
    );
    expect(JSON.parse(response.toString()).Schedule).toEqual({
      Description: "updated-description",
      Enforced: false,
      Hibernate: false,
      Name: scheduleName,
      Type: "schedule",
      Periods: [reusablePeriodName],
      RetainRunning: false,
      StopNewInstances: true,
    });
    expect(await getConfigTableItem("schedule", scheduleName)).toEqual({
      description: "updated-description",
      enforced: false,
      hibernate: false,
      name: scheduleName,
      type: "schedule",
      periods: new Set([reusablePeriodName]),
      retain_running: false,
      stop_new_instances: true,
    });
  }, 10_000);

  test("should error from update-schedule cli command when schedule does not exist", () => {
    const scheduleName = `${dynamoDbItemNamePrefix}-update-schedule-does-not-exist`;

    expect(() =>
      execSync(
        `python -m instance_scheduler_cli update-schedule` +
          ` --stack ${hubStack}` +
          ` --name ${scheduleName}` +
          ` --periods ${reusablePeriodName}` +
          ` --description updated-description`,
      ),
    ).toThrow("Command failed:");
  });

  // describe-schedule-usage
  test("should successfully describe schedule usage with describe-schedule-usage cli command", async () => {
    const scheduleName = `${dynamoDbItemNamePrefix}-describe-schedule-usage`;
    await createSchedule({
      name: scheduleName,
      description: "cli-test",
      periods: new Set([reusablePeriodName]),
      timezone: "UTC",
    });

    // Response contains current date in two different formats (yyyy-mm-dd, mm/dd/yy)
    // Need to calculate those for the current date to form the expected response object
    const date = new Date();
    const day = String(date.getUTCDate()).padStart(2, "0");
    const month = String(date.getUTCMonth() + 1).padStart(2, "0"); // month is 0 indexed
    const year = date.getUTCFullYear().toString();

    const yyyymmdd = `${year}-${month}-${day}`;
    const mmddyy = `${month}/${day}/${year.slice(-2)}`;

    const response = execSync(
      `python -m instance_scheduler_cli describe-schedule-usage --stack ${hubStack} --name ${scheduleName}`,
    );
    expect(JSON.parse(response.toString())).toEqual({
      Schedule: scheduleName,
      Usage: {
        [yyyymmdd]: {
          RunningPeriods: {
            [reusablePeriodName.charAt(0).toUpperCase() + reusablePeriodName.slice(1)]: {
              // cli handler converts periodNames to PascalCase
              Begin: `${mmddyy} 23:00:00`,
              End: `${mmddyy} 23:59:00`,
              BillingHours: 1,
              BillingSeconds: 3540,
            },
          },
          BillingSeconds: 3540,
          BillingHours: 1,
        },
      },
    });
  });

  test("should error from describe-schedule-usage cli command when schedule does not exist", () => {
    const scheduleName = `${dynamoDbItemNamePrefix}-describe-schedule-usage-does-not-exist`;

    expect(() =>
      execSync(`python -m instance_scheduler_cli describe-schedule-usage --stack ${hubStack} --name ${scheduleName}`),
    ).toThrow("Command failed:");
  }, 10_000);
});
