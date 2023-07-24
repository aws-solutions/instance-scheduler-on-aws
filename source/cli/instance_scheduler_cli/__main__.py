# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import sys

from instance_scheduler_cli.scheduler_cli import build_parser


def main() -> int:
    parser = build_parser()
    if len(sys.argv) == 1:
        parser.print_help()
        return 0
    else:
        p = parser.parse_args(sys.argv[1:])
        return int(p.func(p, p.command))


sys.exit(main())
