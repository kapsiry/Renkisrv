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
    def __init__(self, module=None, variable=None):
        self.module = module
        self.variable = variable

#TODO: rewrite options to objects
# with: 
# mandatory t/f
# module string
# values: None
# default string/bool

default_variables = [
    ('servers', None),
    ('services_username', mandatory()),
    ('services_password', mandatory()),
    ('services_port', None),
    ('services_server', mandatory()),
    ('services_database', mandatory()),
    ('debug', False),
    ('database_debug', False),
    ('log_file', None),
    ('apache_ssl', False),
    ('apache_ssl_domain', mandatory(variable='apache_ssl')),
    ('apache_log_dir', '/var/log/apache2/%(vhost)s'),
    ('apache_default_ssl_key', mandatory(variable='apache_ssl')),
    ('apache_default_ssl_crt', mandatory(variable='apache_ssl')),
    ('apache_default_ssl_cacrt', None),
    ('apache_vhosts_dir', '/etc/apache2/'),
    ('apache_documentroot', '/var/www/'),
    ('bind_secret', mandatory(module='bind')),
    ('bind_secret_name', mandatory(module='bind')),
    ('bind_zones_conf', '/etc/bind/zones.conf'),
    ('bind_zones_dir', mandatory(module='bind')),
    ('bind_master', True),
    ('bind_secret_algorithm', 'hmac-md5'),
    ('hostnames', mandatory())
    ]

class ConfigError(Exception):
    def __init__(self, value, dependency=None):
        self.value = value
        self.dependency = dependency

    def __str__(self):
        if self.dependency:
            return "Config setting %s is mandatory if %s is set!" % (self.value,
                                                                self.dependency)
        return "Config setting %s is mandatory!" % self.value

    def __unicode__(self):
        print unicode(self.__str__())

class Config():
    def __init__(self):
        self.variables = default_variables
        self.variables_dict = dict({key: value for key,value in self.variables})
        self.tables = ['t_change_log']
        self.services = {}
        self.log = logging.getLogger('renkisrv')
        self._check_config()

    def _check_config(self):
        for key, value in self.variables:
            try:
                getattr(self,key)
            except AttributeError:
                self._check_variable(key)

    def _check_variable(self, name):
        if not name:
            return
        try:
            setattr(self,name,globals()[name])
            return
        except KeyError:
            if type(self.variables_dict[name]) == type(mandatory()):
                if self.servers:
                    if not self.variables_dict[name].module and not self.variables_dict[name].variable:
                        raise ConfigError(name)
                    if self.variables_dict[name].module not in self.servers:
                        if self.variables_dict[name].variable:
                            try:
                                if not getattr(self,self.variables_dict[name].variable):
                                    return
                            except:
                                raise RuntimeError('BUG: Config variable %s must be defined before %s' % (
                                        self.variables_dict[name].variable, name))
                            raise ConfigError(name, self.variables_dict[name].variable)
                        else:
                            return
                raise ConfigError(name)
            else:
                setattr(self,name,self.variables_dict[name])

    def add_tables(self,tables):
        for table in tables:
            if table not in self.tables:
                self.tables.append(table)

    def add_setting(self,name,default=mandatory()):
        if name:
            if name in self.variables_dict:
                raise RuntimeError('Config %s already set!' % name)
            self.variables_dict[name] = default
            self._check_config()
