from unittest import mock
import os


def mock_boto_env_vars():
    mock.patch.dict(os.environ, {'AWS_DEFAULT_REGION': 'us-east-1'}).start()
    mock.patch.dict(os.environ, {'AWS_ACCESS_KEY_ID': 'testing'}).start()
    mock.patch.dict(os.environ, {'AWS_SECRET_ACCESS_KEY': 'testing'}).start()
    mock.patch.dict(os.environ, {'AWS_SECURITY_TOKEN': 'testing'}).start()
    mock.patch.dict(os.environ, {'AWS_SESSION_TOKEN': 'testing'}).start()
    mock.patch.dict(os.environ, {'SOLUTION_ID': 'SOTestID'}).start()
    mock.patch.dict(os.environ, {'AWS_ACCOUNT': '123456789012'}).start()
