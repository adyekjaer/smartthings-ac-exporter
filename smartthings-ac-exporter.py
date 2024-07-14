#!/usr/bin/env python
""" Smartthings AC exporter """

import sys
import argparse
import time
import prometheus_client
from prometheus_client.core import GaugeMetricFamily, CounterMetricFamily, REGISTRY
import aiohttp
import asyncio
import pysmartthings
import inflection
import json


class STACCollector:
    """ Class for collecting and exporting Smartthings AC metrics """

    def __init__(self, args):
        """Construct the object and parse the arguments."""
        self.args = self._parse_args(args)

        self.token = self.args.token

        self.metric_list = self.get_device_metrics()

        self.mappings = {
            'air_conditioner_mode': {'cool': 0, 'dry': 1, 'wind': 2, 'auto': 3, 'heat': 4},
            'ac_optional_mode': {'off': 0, 'sleep': 1, 'quiet': 2, 'smart': 3, 'speed': 4},
            'fan_mode': {'auto': 0, 'low': 1, 'medium': 2, 'high': 3, 'turbo': 4},
            'fan_oscillation_mode':  {'fixed': 0, 'all': 1, 'vertical': 2, 'horizontal': 3},
            'dust_filter_status': {'normal': 0, 'wash': 1},
            'auto_cleaning_mode': {'off': 0, 'on': 1},
            'switch': {'off': 0, 'on': 1},
            'status': {'ready': 0, 'notready': 1},
            'spi_mode': {'off': 0, 'on': 1},
        }

    @staticmethod
    def _parse_args(args):
        parser = argparse.ArgumentParser()
        parser.add_argument(
            '-l',
            '--listen',
            dest='listen',
            default='0.0.0.0:9555',
            help='Listen host:port, i.e. 0.0.0.0:9417'
        )
        parser.add_argument(
            '-t',
            '--token',
            required=True,
            dest='token',
            help='Personal Access Token'
        )
        arguments = parser.parse_args(args)
        return arguments

    def get_device_metrics(self):

        with open('./device_metrics.json', 'r') as fp:
            device_metrics = json.load(fp)

        return device_metrics['whitelist']

    def is_mapped(self, name, value):

        if name in self.mappings:
            n_value = self.mappings[name].get(value, None)
            if n_value is None:
                print(f'{name}/{value} not mapped - returning 0')
                return 0
            else:
                return n_value
        else:
            return value

    async def get_metrics(self):

        metrics = {}

        async with aiohttp.ClientSession() as session:
            api = pysmartthings.SmartThings(session, self.token)

            devices = await api.devices()

            # Care about one A/C device for now
            for device in devices:
                if device.name != 'Samsung Room A/C':
                    continue

                print('Refreshing data')
                await device.status.refresh()

                for name, value in device.status.values.items():
                    # Convert name to snake case
                    name = inflection.underscore(name)

                    if name not in self.metric_list:
                        continue

                    if isinstance(value, dict):
                        for sub_name, sub_value in value.items():
                            sub_name = inflection.underscore(sub_name)
                            if sub_name not in self.metric_list:
                                continue
                            metrics[sub_name] = self.is_mapped(sub_name, sub_value)
                    else:
                        metrics[name] = self.is_mapped(name, value)

                # One device then break
                break

            return metrics

    def collect(self):
        """ Create dynamic list of metrics based on api response and whitelist """

        prefix = 'smartthings_ac_'
        metrics = asyncio.run(self.get_metrics())

        for name, info in self.metric_list.items():
            metric_name = f'{prefix}{name}'

            if info['type'] == 'counter':
                counter = CounterMetricFamily(metric_name, info['description'])
                counter.add_metric(labels=['foo'], value=metrics[name])
                yield counter

            elif info['type'] in ['gauge', 'enum']:
                gauge = GaugeMetricFamily(metric_name, info['description'])
                gauge.add_metric(labels=['bar'], value=metrics[name])
                yield gauge

            elif info['type'] in ['sub_metric']:
                continue

            else:
                print(f'Unknown type at {name}')
                continue


def run():
    """ Run the main loop """

    collector = STACCollector(sys.argv[1:])
    args = collector.args

    REGISTRY.register(collector)

    (ip_addr, port) = args.listen.split(':')
    print(f'Starting listener on {ip_addr}:{port}')
    prometheus_client.start_http_server(port=int(port),
                                        addr=ip_addr)
    print('Starting main loop')
    while True:
        time.sleep(15)


if __name__ == '__main__':
    try:
        run()
    except KeyboardInterrupt:
        print('Caught keyboard interrupt - exiting')
    except Exception as main_err:
        print(f'Caught unknown exception ({main_err})')
        raise
