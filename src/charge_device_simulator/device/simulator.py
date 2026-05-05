import asyncio
import logging
import typing

from . import utility
from .error_reasons import ErrorReasons
from ..model.error_message import ErrorMessage
from .abstract import DeviceAbstract
from .flows import Flows
from .frequent_flow_options import FrequentFlowOptions


class Simulator:
    __logger = logging.getLogger(__name__)

    @property
    def logger(self) -> logging.Logger:
        return self.__logger

    is_ended = False
    flow_charge_options: dict = {}
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
                            self.flow_charge_options)
                    elif f_flow == Flows.Charge:
                        task_def = self.device.flow_charge(
                            True,
                            self.flow_charge_options
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
        # Interactive sessions should drop back to the menu on a rejected
        # response instead of sys.exit'ing the process. Toggled here (rather
        # than in initialize) so callers can flip is_interactive after
        # initialize() completes; common pattern in play_ground.py.
        if self.is_interactive:
            self.device.error_exit = False
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
        await utility.run_menu("What should I do?", [
            utility.MenuEntry("Exit", is_back=True, shortcut="0"),
            utility.MenuEntry("Flow charge", self._interactive_flow_charge, shortcut="1"),
            utility.MenuEntry("Flow heartbeat", self.device.flow_heartbeat, shortcut="2"),
            utility.MenuEntry("Flow authorize", self._interactive_flow_authorize, shortcut="3"),
            utility.MenuEntry("Flow charge with RFID swipe",
                              self._interactive_flow_rfid_swipe, shortcut="4"),
            utility.MenuEntry("Single message", self.device.loop_interactive_custom, shortcut="s"),
        ])

    async def _interactive_flow_charge(self) -> None:
        await self.device.flow_charge(True, self.flow_charge_options)

    async def _interactive_flow_authorize(self) -> None:
        await self.device.flow_authorize(self.flow_charge_options)

    async def _interactive_flow_rfid_swipe(self) -> None:
        swiped_id_tag: str = await utility.prompt_text("Swipe RFID — enter idTag:")
        swipe_options: typing.Dict[str, typing.Any] = dict(self.flow_charge_options)
        swipe_options["idTag"] = swiped_id_tag
        await self.device.flow_charge(True, swipe_options)
