# -*- coding: utf-8 -*-
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import subprocess
import time
import os

from celery import Celery
from celery import states as celery_states

from xTool.config_templates.default_celery import DEFAULT_CELERY_CONFIG
from xTool.exceptions import XToolException
from xTool.executors.base_executor import BaseExecutor
from xTool import configuration
from xTool.utils.log.logging_mixin import LoggingMixin
from xTool.utils.module_loading import import_string

PARALLELISM = configuration.get('core', 'PARALLELISM')

'''
To start the celery worker, run the command:
airflow worker
'''

# 导入celery默认配置
if configuration.has_option('celery', 'celery_config_options'):
    celery_configuration = import_string(
        configuration.get('celery', 'celery_config_options')
    )
else:
    celery_configuration = DEFAULT_CELERY_CONFIG

app = Celery(
    configuration.get('celery', 'CELERY_APP_NAME'),
    config_source=celery_configuration)


@app.task
def execute_command(command):
    """执行shell命令 ."""
    log = LoggingMixin().log
    log.info("Executing command in Celery: %s", command)
    env = os.environ.copy()
    try:
        subprocess.check_call(command, shell=True, stderr=subprocess.STDOUT,
                              close_fds=True, env=env)
    except subprocess.CalledProcessError as e:
        log.exception('execute_command encountered a CalledProcessError')
        log.error(e.output)

        raise AirflowException('Celery command failed')


class CeleryExecutor(BaseExecutor):
    """
    CeleryExecutor is recommended for production use of Airflow. It allows
    distributing the execution of task instances to multiple worker nodes.

    Celery is a simple, flexible and reliable distributed system to process
    vast amounts of messages, while providing operations with the tools
    required to maintain such a system.
    """

    def start(self):
        self.tasks = {}
        self.last_state = {}

    def execute_async(self, key, command,
                      queue=DEFAULT_CELERY_CONFIG['task_default_queue']):
        self.log.info("[celery] queuing {key} through celery, "
                      "queue={queue}".format(**locals()))
        # 向celery发送任务
        self.tasks[key] = execute_command.apply_async(
            args=[command], queue=queue)
        # 记录当前任务的状态
        self.last_state[key] = celery_states.PENDING

    def sync(self):
        self.log.debug("Inquiring about %s celery task(s)", len(self.tasks))
        for key, async in list(self.tasks.items()):
            try:
                # 获得异步任务的执行状态
                state = async.state
                if self.last_state[key] != state:
                    if state == celery_states.SUCCESS:
                        self.success(key)
                        del self.tasks[key]
                        del self.last_state[key]
                    elif state == celery_states.FAILURE:
                        self.fail(key)
                        del self.tasks[key]
                        del self.last_state[key]
                    elif state == celery_states.REVOKED:
                        self.fail(key)
                        del self.tasks[key]
                        del self.last_state[key]
                    else:
                        self.log.info("Unexpected state: %s", async.state)
                    self.last_state[key] = async.state
            except Exception as e:
                self.log.error(
                    "Error syncing the celery executor, ignoring it:")
                self.log.exception(e)

    def end(self, synchronous=False):
        if synchronous:
            # 等待所有的任务完成
            while any([
                    async.state not in celery_states.READY_STATES
                    for async in self.tasks.values()]):
                time.sleep(5)
        self.sync()
