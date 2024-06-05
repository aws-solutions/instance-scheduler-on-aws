# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import re
from typing import TYPE_CHECKING, Final, Iterator, Sequence

from instance_scheduler.boto_retry import get_client_with_standard_retry

if TYPE_CHECKING:
    from mypy_boto3_ssm import SSMClient
else:
    SSMClient = object


def replace_ssm_references_with_account_ids(
    raw_account_ids_list: Sequence[str],
) -> Iterator[str]:
    """
    for any account ids provided in the format {param:[param-name]}, fetch the corresponding
    SSM parameter list and append it to the list of account_ids

    :param raw_account_ids_list: a raw list of account_ids that may or may not contain ssm_param references
    :return: a new list of account_ids after ssm_param references have been fetched
    """
    REGEX_SSM_PARAM: Final = "{param:(.+?)}"

    for account_id in raw_account_ids_list:
        if re.match(REGEX_SSM_PARAM, account_id):
            param_names = re.findall(REGEX_SSM_PARAM, account_id)
            for ssm_account_id in fetch_account_ids_from_ssm_params(param_names):
                yield ssm_account_id
        else:
            yield account_id


def fetch_account_ids_from_ssm_params(param_names: list[str]) -> list[str]:
    if len(param_names) == 0:
        return []

    ssm_client: SSMClient = get_client_with_standard_retry("ssm")
    resp = ssm_client.get_parameters(Names=list(set(param_names)))  # remove duplicates

    account_ids = []
    for p in resp.get("Parameters", []):
        if p["Type"] == "StringList":
            account_ids += p["Value"].split(",")
        else:
            account_ids.append(p["Value"])
    return account_ids
