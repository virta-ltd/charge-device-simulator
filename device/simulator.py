import asyncio
import logging
import typing

import aioconsole

from .abstract import DeviceAbstract
from .flows import Flows
from .frequent_flow_options import FrequentFlowOptions
from device.error_reasons import ErrorReasons
from model.error_message import ErrorMessage


class Simulator:
    __logger = logging.getLogger(__name__)

    @property
    def logger(self) -> logging.Logger:
        return self.__logger

    is_ended = False
    flow_charge_options: None
    frequent_flow_enabled = True
    is_interactive = False
    frequent_flows: typing.Dict[Flows, FrequentFlowOptions] = {}
    on_error = []

    def __init__(self, device: DeviceAbstract):
        self.device = device
        self.name = ''

    async def loop_flow_frequent(self):
        time_loop = 0
        tasks: typing.Dict[str, asyncio.tasks.Task] = {}
        while not self.is_ended:
            await asyncio.sleep(1)
            time_loop += 1

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
                        time_loop - f_options.run_last_time >= f_options_delay_seconds
                ) and (
                        f_options.count < 0 or
                        f_options.run_counter < f_options.count
                ):
                    task_def = None
                    if f_flow == Flows.Heartbeat:
                        task_def = self.device.flow_heartbeat()
                    elif f_flow == Flows.Authorize:
                        task_def = self.device.flow_authorize(
                            **self.flow_charge_options)
                    elif f_flow == Flows.Charge:
                        task_def = self.device.flow_charge(
                            True,
                            **self.flow_charge_options
                        )
                    if task_def is not None:
                        self.logger.info(
                            f"Frequent Flow, Started, Flow: {f_flow}, Time: {time_loop}")
                        tasks[f_flow.name] = asyncio.create_task(self.task_start(task_def))
                    f_options.run_counter += 1
                    f_options.run_last_time = time_loop

            if len(list(filter(
                    lambda x:
                    self.frequent_flows[x].count < 0 or
                    self.frequent_flows[x].run_counter < self.frequent_flows[x].count,
                    self.frequent_flows
            ))) <= 0:
                self.logger.info(
                    f"No more frequent flow to run, wait for running tasks")
                await asyncio.gather(*(tasks.values()))
                self.logger.info(f"No more frequent flow to run, exiting loop")
                break
        pass

    async def task_start(self, task_def):
        try:
            await task_def
        except Exception as e:
            await self.device.handle_error(ErrorMessage(e).get(), ErrorReasons.UnknownException)

    async def initialize(self):
        self.device.on_error = self.on_error
        self.device.on_error.append(self.device_on_error)
        self.logger.info("Initialize")
        while not await self.device.initialize():
            await asyncio.sleep(10)
        pass

    async def re_initialize(self):
        self.logger.info("Re-Initialize")
        while not await self.device.re_initialize():
            await asyncio.sleep(10)
        pass

    async def device_on_error(self, desc, reason: ErrorReasons):
        if reason == ErrorReasons.UnknownException:
            await self.re_initialize()
        pass

    async def lifecycle_start(self):
        tasks = []
        if self.is_interactive:
            tasks.append(self.loop_interactive())
        if self.frequent_flow_enabled:
            tasks.append(self.loop_flow_frequent())
        await asyncio.gather(*tasks)

    async def end(self):
        self.is_ended = True
        await self.device.end()
        pass

    async def loop_interactive(self):
        while not self.is_ended:
            input1 = await aioconsole.ainput("""
What should I do? (enter the number + enter)
0: Exit
1: Flow charge
2: Flow heartbeat
3: Flow authorize
99: Single message
""")
            if input1 == "0":
                return
            elif input1 == "1":
                await self.device.flow_charge(True, **self.flow_charge_options)
            elif input1 == "2":
                await self.device.flow_heartbeat()
            elif input1 == "3":
                await self.device.flow_authorize(**self.flow_charge_options)
            elif input1 == "99":
                await self.device.loop_interactive_custom()
        pass
