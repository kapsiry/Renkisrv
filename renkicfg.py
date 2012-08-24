# encoding: utf-8
# Licensed under MIT license
# Kapsi Internet-käyttäjät ry

# This file contains default settings for renkisrv server.

from config import *
import logging
from pprint import pprint


# Format 'variable name' : 'Default value'
# If default value is mandatory(), setting is mandatory and if setting not found on config
# ConfigError is raised

class mandatory():
    pass

default_variables = {
    'services_username': mandatory,
    'services_password' : mandatory,
    'services_port': None,
    'services_server' : mandatory,
    'services_database' : mandatory,
    'servers': None,
    'debug': False,
    'database_debug': False,
    'log_file' : None,
    'apache_ssl': False,
    'apache_ssl_domain': None,
    'apache_log_dir': '/var/log/apache2/%(vhost)s',
    'apache_default_ssl_key': None,
    'apache_default_ssl_crt': None,
    'apache_default_ssl_cacrt': None,
    'apache_vhosts_dir': '/etc/apache2/',
    'apache_documentroot': '/var/www/',
    'hostnames' : mandatory
    }

class ConfigError(Exception):
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return "Config setting %s is mandatory!" % self.value

    def __unicode__(self):
        print unicode(self.__str__())

class Config():
    def __init__(self):
        self.variables = default_variables
        self.tables = ['t_change_log']
        self.services = {}
        self.log = logging.getLogger('renkisrv')
        self._check_config()

    def _check_config(self):
        for var in self.variables:
            try:
                getattr(self,var)
            except AttributeError:
                self._check_variable(var)

    def _check_variable(self, name):
        if not name:
            return
        try:
            self.log.debug('setting value %s = %s' % (name, globals()[name]))
            setattr(self,name,globals()[name])
            return
        except KeyError:
            if self.variables[name] == mandatory:
                raise ConfigError(name)
            else:
                setattr(self,name,self.variables[name])

    def add_tables(self,tables):
        for table in tables:
            if table not in self.tables:
                self.tables.append(table)

    def add_setting(self,name,default=mandatory):
        if name:
            if name in self.variables:
                raise RuntimeError('Config %s already set!' % name)
            self.variables[name] = default
            self._check_config()
