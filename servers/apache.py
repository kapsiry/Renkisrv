import renkiserver

# Apache config service for renki

__version__ = '0.0.1'

class RenkiServer(renkiserver.RenkiServer):
    def __init__(self):
        renkiserver.RenkiServer.__init__(self)
        self.name = 'apache'
        self.tables = ['s_vhosts']

    def insert(self, sqlobject, table):
        """Process apache configs to server"""
        print('TABLE: %s' % table)
        if table == 's_vhosts':
            self.log.debug('Creating some apache configs here...')
            self.log.debug('Vhost name: %s' % sqlobject.name)
            self.log.debug('%s' % vars(sqlobject))
        return True

    def update(self, old_sqlobject, new_sqlobject, table):
        """Process apache configs to server"""
        if table == 's_vhosts':
            self.log.debug('Updating some apache configs here...')
            self.log.debug('Vhost name: %s' % new_sqlobject.name)
            self.log.debug('%s' % vars(new_sqlobject))
        return True

    def delete(self, sqlobject, table):
        """Process apache configs to server"""
        if table == 's_vhosts':
            self.log.debug('Deleting some apache configs here...')
            self.log.debug('Vhost name: %s' % sqlobject.name)
        return True