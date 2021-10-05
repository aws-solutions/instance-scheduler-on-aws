from util.cross_account_roles import get_cross_account_role_arn
import os


def test_get_cross_account_role_arn():
    account_ids = ["account-1", "account-2"]
    role_arns = get_cross_account_role_arn(account_ids)
    print(role_arns)
    for arn in role_arns:
        assert arn.startswith(f"arn:{os.getenv('aws_partition')}:iam::")
        assert arn.endswith(f":role/{os.getenv('namespace')}"
                            f"-{os.getenv('execution_role_name')}"
                            f"-{os.getenv('AWS_REGION')}")
