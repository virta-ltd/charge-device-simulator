import asyncio
import logging
import typing

import aioconsole

from .abstract import DeviceAbstract
from .flows import Flows
from .frequent_flow_options import FrequentFlowOptions


class Simulator:
    __logger = logging.getLogger(__name__)

    @property
    def logger(self) -> logging:
        return self.__logger

    is_ended = False
    flow_charge_options: None
    frequent_flow_enabled = True
    frequent_flows: typing.Dict[Flows, FrequentFlowOptions] = {}

    def __init__(self, device: DeviceAbstract):
        self.device = device

    async def loop_flow_frequent(self):
        time = 0
        tasks: typing.Dict[str, asyncio.tasks.Task] = {}
        while not self.is_ended:
            await asyncio.sleep(1)
            time += 1

            f_flow: Flows
            for f_flow in self.frequent_flows:
                if f_flow.name in tasks and not tasks[f_flow.name].done():
                    continue
                f_options = self.frequent_flows[f_flow]
                f_options_delay_seconds = f_options.delay_seconds
                if f_options_delay_seconds <= 0:
                    f_options_delay_seconds = 60
                if (
                        f_options.run_last_time < 0 or
                        time - f_options.run_last_time >= f_options_delay_seconds
                ) and (
                        f_options.count < 0 or
                        f_options.run_counter < f_options.count
                ):
                    task_def = None
                    if f_flow == Flows.Heartbeat:
                        task_def = self.device.flow_heartbeat()
                    elif f_flow == Flows.Authorize:
                        task_def = self.device.flow_authorize(**self.flow_charge_options)
                    elif f_flow == Flows.Charge:
                        task_def = self.device.flow_charge(**self.flow_charge_options)
                    if task_def is not None:
                        self.logger.info(f"Frequent Flow, Started, Flow: {f_flow}, Time: {time}")
                        tasks[f_flow.name] = asyncio.create_task(task_def)
                    f_options.run_counter += 1
                    f_options.run_last_time = time

            if len(list(filter(
                    lambda x:
                    self.frequent_flows[x].count < 0 or
                    self.frequent_flows[x].run_counter < self.frequent_flows[x].count,
                    self.frequent_flows
            ))) <= 0:
                self.logger.info(f"No more frequent flow to run, wait for running tasks")
                await asyncio.gather(*(tasks.values()))
                self.logger.info(f"No more frequent flow to run, exiting loop")
                break
        pass

    def initialize(self):
        self.logger.info("Initialize")
        self.device.initialize()

    async def lifecycle_start(self, is_interactive=False):
        tasks = []
        if is_interactive:
            tasks.append(self.loop_interactive())
        if self.frequent_flow_enabled:
            tasks.append(self.loop_flow_frequent())
        await asyncio.gather(*tasks)

    def end(self):
        self.is_ended = True
        self.device.end()
        pass

    async def loop_interactive(self):
        while not self.is_ended:
            input1 = await aioconsole.ainput("""
What should I do? (enter the number + enter)
0: Exit
1: Flow charge
2: Flow frequent
3: Custom
""")
            if input1 == "0":
                return
            elif input1 == "3":
                await self.device.loop_interactive_custom()
        pass
