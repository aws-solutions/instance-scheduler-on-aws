# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import traceback
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from os import environ
from typing import TYPE_CHECKING, Any, Literal, TypedDict, TypeGuard, cast, get_args

from instance_scheduler.model.store.ddb_config_item_store import DdbConfigItemStore
from instance_scheduler.util import safe_json
from instance_scheduler.util.app_env_utils import AppEnvError, env_to_bool
from instance_scheduler.util.logger import Logger
from instance_scheduler.util.validation import ValidationException, validate_string

if TYPE_CHECKING:
    from aws_lambda_powertools.utilities.typing import LambdaContext
else:
    LambdaContext = object


SpokeRegistrationOperation = Literal["Register", "Deregister"]

SpokeRequest = TypedDict(
    "SpokeRequest",
    {
        "account": str,
        "operation": SpokeRegistrationOperation,
    },
    total=False,
)


@dataclass(frozen=True)
class SpokeRegistrationEnvironment:
    user_agent_extra: str
    log_group: str
    topic_arn: str
    enable_debug_logging: bool
    config_table_name: str

    @staticmethod
    def from_env() -> "SpokeRegistrationEnvironment":
        try:
            return SpokeRegistrationEnvironment(
                user_agent_extra=environ["USER_AGENT_EXTRA"],
                log_group=environ["LOG_GROUP"],
                topic_arn=environ["ISSUES_TOPIC_ARN"],
                enable_debug_logging=env_to_bool(environ["ENABLE_DEBUG_LOGS"]),
                config_table_name=environ["CONFIG_TABLE"],
            )
        except KeyError as err:
            raise AppEnvError(
                f"Missing required application environment variable: {err.args[0]}"
            ) from err


def validate_spoke_request(untyped_dict: Mapping[str, Any]) -> TypeGuard[SpokeRequest]:
    validate_string(untyped_dict, "account", required=True)
    validate_string(untyped_dict, "operation", required=True)

    operation = untyped_dict["operation"]
    valid_operations = get_args(SpokeRegistrationOperation)
    if operation not in valid_operations:
        raise ValidationException(
            f"{operation} is not a valid operation, valid operations are {valid_operations}"
        )

    return True


class SpokeRegistrationException(Exception):
    pass


class InvalidRequestException(Exception):
    pass


def handle_spoke_registration_event(
    event: Mapping[str, Any],
    _: LambdaContext,
) -> str:
    env = SpokeRegistrationEnvironment.from_env()

    dt = datetime.now(timezone.utc)
    log_stream = "SpokeRegistration-{:0>4d}{:0>2d}{:0>2d}".format(
        dt.year, dt.month, dt.day
    )
    with Logger(
        log_group=env.log_group,
        log_stream=log_stream,
        topic_arn=env.topic_arn,
        debug=env.enable_debug_logging,
    ) as logger:
        logger.debug(
            "spoke registration handler received event: {}", safe_json(event, indent=3)
        )

        try:
            validate_spoke_request(event)
            event = cast(SpokeRequest, event)
            handler = SpokeRegistrationHandler(event, env=env, logger=logger)

            return handler.handle_request()
        except Exception as e:
            # log error to SNS, then let the lambda execution fail
            logger.error(
                "Error handling spoke registration request {}: ({})\n{}",
                safe_json(event),
                e,
                traceback.format_exc(),
            )
            raise e


class SpokeRegistrationHandler:
    """
    Handles event from cloudwatch rule time
    """

    def __init__(
        self,
        event: SpokeRequest,
        env: SpokeRegistrationEnvironment,
        logger: Logger,
    ) -> None:
        self._logger = logger
        self._event = event
        self._ddb_config_item_store = DdbConfigItemStore(env.config_table_name)

    def handle_request(self) -> str:
        """
        Handles the CloudWatch Rule timer events
        :return:
        """
        event = self._event
        account_id = event["account"]

        match event["operation"]:
            case "Register":
                try:
                    self._ddb_config_item_store.register_spoke_accounts({account_id})
                    self._logger.info("Registered spoke account {}", account_id)
                    return f"Registered spoke account {account_id}"
                except Exception as e:
                    raise SpokeRegistrationException(
                        f"Error registering spoke account {account_id}: {e}"
                    )
            case "Deregister":
                try:
                    self._ddb_config_item_store.deregister_spoke_accounts({account_id})
                    self._logger.info("Deregistered spoke account {}", account_id)
                    return f"Deregistered spoke account {account_id}"
                except Exception as e:
                    raise SpokeRegistrationException(
                        f"Error deregistering spoke account {account_id}: {e}"
                    )
            case _:
                raise InvalidRequestException(
                    f"Spoke Registration handler received an unknown request: {self._event}"
                )
