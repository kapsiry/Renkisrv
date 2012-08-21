import renkiserver

# User ports service for renki

__version__ = '0.0.1'

class RenkiServer(renkiserver.RenkiServer):
    def __init__(self):
        renkiserver.RenkiServer.__init__(self)
        self.name = 'user_ports'
        self.tables = ['s_user_ports']

    def insert(self, sqlobject, table):
        """Generate firewall rule"""
        print('TABLE: %s' % table)
        if table != 's_user_ports':
            return True
        if sqlobject.server not in self.conf.hostnames:
            # not my bussines
            return True
        self.log.debug('Creating some firewall configs here...')
        if not sqlobject.unix_id:
            self.log.error('Cannot add port %s, unix_id unknown' % sqlobject.port)
            return True
        self.log.debug('User %s, port %s' % (sqlobject.unix_id, sqlobject.port))
        return True

    def update(self, old_sqlobject, new_sqlobject, table):
        """Update firewall rule"""
        if table != 's_user_ports':
            return True
        if sqlobject.server not in self.conf.hostnames:
            # not my bussines
            return True
        self.log.debug('Updating some firewall configs here...')
        return True

    def delete(self, sqlobject, table):
        """Delete firewall rule"""
        if table != 's_user_ports':
            return True
        if sqlobject.server not in self.conf.hostnames:
            # not my bussines
            return True
        self.log.debug('Deleting some firewall configs here...')
        return True