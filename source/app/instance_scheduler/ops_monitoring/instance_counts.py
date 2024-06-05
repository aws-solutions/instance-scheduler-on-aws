# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from collections import Counter
from typing import Iterable, Literal, Self

from instance_scheduler.service.abstract_instance import AbstractInstance

InstanceState = Literal["running", "stopped"]
ServiceName = str


class InstanceCounts(dict[str, Counter[InstanceState]]):
    """
    a count of instances in a given state aggregated by some key (schedule_name, instance_type)

    This can be accessed with indexing like any other dict, or safely using
    counts.get(aggregation_key, Counter()).get("stopped")
    which return the number of counted instances of the given type in the stopped state
    (returning 0 as the default fallback even if no instances of that type have been counted)
    """

    def count_instances_by_type(self, instances: Iterable[AbstractInstance]) -> Self:
        for instance in instances:
            self.increment(
                instance.instance_type,
                self.parse_as_running_or_stopped(instance.current_state),
            )
        return self

    def parse_as_running_or_stopped(
        self, instance_state: str
    ) -> Literal["running", "stopped"]:
        instance_state = instance_state.lower()
        match instance_state:
            case "available" | "starting" | "backing-up":  # rds running states
                return "running"
            case "running" | "starting":  # ec2 running states
                return "running"
            case _:
                return "stopped"

    def increment(self, aggregation_key: str, instance_state: str) -> Self:
        instance_state = self.parse_as_running_or_stopped(instance_state)
        if aggregation_key not in self:
            self[aggregation_key] = Counter()
        self[aggregation_key][instance_state] += 1
        return self

    def merged_with(self, other: "InstanceCounts") -> "InstanceCounts":
        return InstanceCounts(
            # create a new dict containing the union of all keys in the original 2 dicts
            # and summing together the counters of any keys that existed in both dicts
            {
                instance_type: self.get(instance_type, Counter())
                + other.get(instance_type, Counter())
                for instance_type in set(self).union(other)
            }
        )


class InstanceCountsAggregator(dict[Literal["by_type", "by_schedule"], InstanceCounts]):
    def by_type(self) -> InstanceCounts:
        if "by_type" not in self:
            self["by_type"] = InstanceCounts()
        return self["by_type"]

    def by_schedule(self) -> InstanceCounts:
        if "by_schedule" not in self:
            self["by_schedule"] = InstanceCounts()
        return self["by_schedule"]

    def merged_with(
        self, other: "InstanceCountsAggregator"
    ) -> "InstanceCountsAggregator":
        return InstanceCountsAggregator(
            # create a new dict containing the union of all keys in the original 2 dicts
            # and summing together the counters of any keys that existed in both dicts
            {
                counter: self.get(counter, InstanceCounts()).merged_with(
                    other.get(counter, InstanceCounts())
                )
                for counter in set(self).union(other)
            }
        )


class ServiceInstanceCounts(dict[ServiceName, InstanceCountsAggregator]):
    """
    sample data shape
    {
      "ec2": {
        "by_type": {
          "t2.micro": {
            stopped: 5
            running: 10
          }
        }
        "by_schedule": {
          "schedule-1": {
            stopped: 12,
            running: 0
          }
       }
      },
      "rds": {
        "by_type": {
          "m2.medium": {
            stopped: 1
            running: 1
          }
        }
        "by_schedule": {
          "schedule-1": {
            stopped: 2,
            running: 0
          }
       }
      }
    }
    """

    def merged_with(self, other: "ServiceInstanceCounts") -> "ServiceInstanceCounts":
        return ServiceInstanceCounts(
            # create a new dict containing the union of all keys in the original 2 dicts
            # and summing together the counters of any keys that existed in both dicts
            {
                service: self.get(service, InstanceCountsAggregator()).merged_with(
                    other.get(service, InstanceCountsAggregator())
                )
                for service in set(self).union(other)
            }
        )
