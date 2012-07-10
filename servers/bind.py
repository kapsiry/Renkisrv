import renkiserver

# Bind config service for renki

__version__ = '0.0.1'

class RenkiServer(renkiserver.RenkiServer):
    def __init__(self):
        renkiserver.RenkiServer.__init__(self)
        self.name = 'dns'
        self.tables = ['t_domains']
        
    def parse_inetlist(self, inetlist):
        if not inetlist:
            return None
        addresses = []
        address = ""
        for i in inetlist:
            if i in '1234567890.':
                address += i
            elif i in ',}':
                addresses.append(address)
                address = ''
        return addresses

    def insert(self, sqlobject, table):
        """Process dns configs to server"""
        if table == 't_domains':
            self.log.debug('Doing some dns configs here...')
            self.log.debug('Domain name: %s' % sqlobject.name)
            sqlobject.masters = self.parse_inetlist(sqlobject.masters)
            self.log.debug('%s' % vars(sqlobject))
        return True
        
    def update(self, old_sqlobject, new_sqlobject, table):
        """Process dns configs to server"""
        if table == 't_domains':
            self.log.debug('Updating some dns configs here...')
            self.log.debug('New Domain name: %s' % new_sqlobject.name)
            new_sqlobject.masters = self.parse_inetlist(new_sqlobject.masters)
            self.log.debug('%s' % vars(new_sqlobject))
        return True

    def delete(self, sqlobject, table):
        """Process dns configs to server"""
        if table == 't_domains':
            self.log.debug('Deleting some dns configs here...')
            self.log.debug('Domain name: %s' % sqlobject.name)
        return True