# encoding: utf-8
# Licensed under MIT license
# Kapsi Internet-käyttäjät ry

# This file contains default settings for renkisrv server.

import logging
import imp
from libs.exceptions import ConfigException, ConfigError, ConfigTypeError, ConfigValueError

class Option:
    def __init__(self, name, module=None, mandatory=False, variable=None, values=[], default=None, type=None):
        self.name = name
        self.module = module
        self.variable = variable
        self.values = values
        self.default = default
        self.mandatory = mandatory
        self.type = None
        if type:
            if type in ['int', 'str', 'bool', 'list']:
                self.type = type
            else:
                raise ConfigException('BUG: value_type must be int, str or bool')

    def check_value(self, value):
        if self.type:
            try:
                if self.type == 'int':
                    value = int(value)
                elif self.type == 'str':
                    value = str(value)
                elif self.type == 'bool':
                    value = bool(value)
                elif self.type == 'list':
                    if type(value) == type([]) or type(value) == type(()):
                        value = list(value)
                    else:
                        raise ConfigTypeError(self.name, value, self.type)
                else:
                    raise ConfigException('BUG: Unknown type %s' % self.type)
            except TypeError:
                raise ConfigTypeError(self.name, value, self.type)
        if len(self.values) > 0:
            if self.type != 'list':
                if value not in self.values:
                    raise ConfigValueError(self.name, value, self.values)
            else:
                for v in value:
                    if v not in self.values:
                        raise ConfigValueError(self.name, v, self.values)
        return value

    def get(self, conf_obj):
        if self.module:
            if self.module not in conf_obj.servers:
                return
        if self.variable:
            try:
                if not conf_obj.variables_dict[self.variable].get(conf_obj):
                    return
            except KeyError:
                raise ConfigException('Invalid dependency variable %s given' % self.variable)
        try:
            return self.check_value(getattr(conf_obj.values,self.name))
        except AttributeError:
            if not self.mandatory:
                return self.default
            elif self.module:
                raise ConfigError(self.name, dependency=self.module)
            else:
                raise ConfigError(self.name)


class Config():
    def __init__(self, variables, config_file):
        self.variables = variables
        self.variables_dict = {}
        for value in self.variables:
            self.variables_dict[value.name] = value
        try:
            self.values = imp.load_source('config', config_file)
        except IOError:
            raise ConfigException('File %s does not exists')
        self.tables = ['t_change_log']
        self.services = {}
        self.log = logging.getLogger('renkisrv')
        self._check_config()

    def _check_config(self):
        for option in self.variables:
            try:
                getattr(self,option.name)
            except AttributeError:
                self._check_variable(option)

    def _check_variable(self, option):
        if not option:
            return
        setattr(self,option.name, option.get(self))

    def add_tables(self,tables):
        for table in tables:
            if table not in self.tables:
                self.tables.append(table)

    def add_setting(self,option):
        if option:
            if option.name in self.variables_dict:
                # already added
                return
            self.variables_dict[option.name] = option
            self.variables.append(option)
            self._check_config()
