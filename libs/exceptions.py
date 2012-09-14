# encoding: utf-8

class ConfigException(Exception):
    def __init__(self, message):
        self.msg = message
    
    def __str__(self):
        return self.msg

    def __unicode__(self):
        return unicode(self.__str__())


class ConfigTypeError(Exception):
    def __init__(self, name, value, type):
        self.name = name
        self.value = value
        self.type = type

    def __str__(self):
        return "Config setting %s value '%s' does not match type %s!" % (
                            self.name, self.value, self.type)

    def __unicode__(self):
        print unicode(self.__str__())


class ConfigValueError(Exception):
    def __init__(self, name, value, values):
        self.name = name
        self.value = value
        self.values = values

    def __str__(self):
        return "Config setting %s value '%s' does not match any allowed values %s!" % (
                                        self.name, self.value, self.values)

    def __unicode__(self):
        print unicode(self.__str__())


class ConfigError(Exception):
    def __init__(self, value, dependency=None):
        self.value = value
        self.dependency = dependency

    def __str__(self):
        if self.dependency:
            return "Config setting %s is mandatory if module %s is set!" % (
                                            self.value, self.dependency)
        return "Config setting %s is mandatory!" % self.value

    def __unicode__(self):
        print unicode(self.__str__())
