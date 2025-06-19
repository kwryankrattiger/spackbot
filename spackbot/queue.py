# Copyright 2013-2021 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

import os

from rq import get_current_job, Queue

import spackbot.helpers as helpers

TASK_QUEUE_SHORT = os.environ.get("TASK_QUEUE_SHORT", "tasks")
TASK_QUEUE_LONG = os.environ.get("TASK_QUEUE_LONG", "tasks_long")
QUERY_TIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"

# If we don't provide a timeout, the default in RQ is 180 seconds
WORKER_JOB_TIMEOUT = int(os.environ.get("WORKER_JOB_TIMEOUT", "21600"))


def _init_redis_connection():
    """Initialization function for redis service"""
    from redis import Redis

    REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
    return Redis(host=REDIS_HOST, port=REDIS_PORT)

# Global redis connection
redis = helpers.Singleton(_init_redis_connection)

def get_queue(name):
    """Get the queue with a given name"""
    return Queue(name=name, connection=redis.instance())
