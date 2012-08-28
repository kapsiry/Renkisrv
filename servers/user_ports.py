import renkiserver
import fileinput
import subprocess
from tempfile import mkstemp
import os
from shutil import move

# User ports service for renki

__version__ = '0.0.1'

class RenkiServer(renkiserver.RenkiServer):
    def __init__(self):
        renkiserver.RenkiServer.__init__(self, name='user_ports')
        self.tables = ['s_user_ports']
        self.config_file = '/etc/ports.conf'

    def reload_firewall(self):
        return True
        if subprocess.call(['/etc/init.d/firewall', 'userports']) != 0:
            self.log.error('/etc/init.d/firewall userports returns error')
        self.log.debug('Firewall successfully reloaded')

    def add_port(self, t_customers_id, port, username):
        if t_customers_id and port and username:
            f = open(self.config_file, 'a')
            f.write("%s %s %s\n" % (t_customers_id, port, username))
            return True
        self.log.error('BUG: invalid parameters given to add_port')
        return False

    def delete_port(self, port, customer):
        fh, abs_path = mkstemp()
        new = open(abs_path, 'w')
        old = open(self.config_file, 'r')
        for line in old:
            try:
                c, p, u = line.split()
                if str(p).strip() == str(port) and str(c) == str(customer).strip():
                    continue
            except:
                pass
            new.write(line)
        new.close()
        old.close()
        # dangerous part:
        move(self.config_file, "%s.old" % self.config_file)
        move(abs_path, self.config_file)
        os.remove("%s.old" % self.config_file)

    def insert(self, sqlobject, table):
        """Generate firewall rule"""
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
        try:
            self.add_port(sqlobject.t_customers_id, sqlobject.port, sqlobject.username)
        except Exception as e:
            self.log.error('Cannot add port %s' % sqlobject.port)
            self.log.exception(e)
            return False
        return True

    def update(self, old_sqlobject, new_sqlobject, table):
        """Update firewall rule"""
        if table != 's_user_ports':
            return True
        if new_sqlobject.server not in self.conf.hostnames:
            # not my bussines
            return True
        if old_sqlobject.port != new_sqlobject.port or \
        old_sqlobject.t_customers_id != new_sqlobject.t_customers_id or \
        old_sqlobject.username != new_sqlobject.username:
            try:
                self.delete_port(old_sqlobject.port, old_sqlobject.t_customers_id)
                self.add_port(new_sqlobject.t_customers_id, new_sqlobject.port, new_sqlobject.username)
            except Exception as e:
                self.log.error('Cannot update port %s' % new_sqlobject.port)
                self.log.exception(e)
                return False
            self.log.debug('Updated port %s' % new_sqlobject.port)
        return True

    def delete(self, sqlobject, table):
        """Delete firewall rule"""
        if table != 's_user_ports':
            return True
        if sqlobject.server not in self.conf.hostnames:
            # not my bussines
            return True
        try:
            self.delete_port(sqlobject.port, sqlobject.t_customers_id)
        except Exception as e:
            self.log.error('Cannot delete port %s' % sqlobject.port)
            self.log.exception(e)
            return False
        self.log.debug('Deleted port %s' % sqlobject.port)
        return True