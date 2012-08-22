import renkiserver
import os, stat
import time
import subprocess
from multiprocessing import Process

from utils import get_uid, drop_privileges, recursive_mkdir

# Apache config service for renki

__version__ = '0.0.1'

def create_dirs(vhost):
    # This is executed as subprocess
    # logdir
    logdir = os.path.join(vhost.main.conf.apache_log_dir, vhost.name)
    if not os.path.isdir(logdir):
        try:
            os.mkdir(logdir)
            # 0=root, 4=admin
            os.chown(logdir, 0, 4)
            os.chmod(logdir, '0750')
        except Exception as e:
            vhost.main.log.error('Cannot create log dir')
            vhost.main.log.exception(e)
            return False

    # drop privileges
    drop_privileges(uid_name=vhost.user, gid_name=vhost.group)
    # vhosts dir
    # TODO: make this more generic
    # kapsi specific sites/ creation
    try:
        if not os.path.isdir(vhost.documentroot):
            recursive_mkdir(vhost.documentroot)
    except Exception as e:
        vhost.main.log.error('Cannot create document root!')
        vhost.main.log.exception(e)
        return False
    return True

    vhost_basedir = vhost.documentroot.rsplit('/')[:-1]
    vhost_basedir = os.path.join(*vhost_basedir)
    # create logs symlink
    link = os.path.join(vhost_basedir, 'log')
    if os.path.exist(link) and not os.path.islink(link):
        # move file to log.old
        subprocess.Popen(['mv', '-fT', link, '%s.old' % link])
    if not os.path.islink(link):
        try:
            os.symlink(vhost.logdir, link)
        except Exception as e:
            vhost.main.log.error('Cannot create symlink %s -> %s' % (vhost.logdir, link))
            vhost.main.log.exception(e)
            return False

    php_handlers = [os.path.join(vhost.documentroot, 'php5.fcgi')]

    if vhost.ssl:
        vhost_docroot = os.path.join(vhost_basedir, 'secure-www')
        if not os.path.isdir(vhost_docroot):
            os.mkdir(vhost_docroot)
        php_handlers.append(os.path.join(vhost_docroot, 'php5.fcgi'))

    # create php handler
    for php_handler in php_handlers:
        if not os.path.exist(php_handler):
            try:
                f = open(php_handler,'w')
                f.write('#!/usr/bin/php5-cgi\n')
                f.close()
                os.chmod(php_handler, '0700')
            except Exception as e:
                vhost.main.log.error('Cannot create php-handler php5.fcgi')
                vhost.main.log.exception(e)
                return False


class RenkiServer(renkiserver.RenkiServer):
    """Vhost generator
    TODO:
    - locked accounts
    """

    def __init__(self):
        renkiserver.RenkiServer.__init__(self)
        self.name = 'apache'
        self.tables = ['s_vhosts']

    class Vhost(object):
        def __init__(self, main, sqlobject = None):
            self.main = main
            self.address = ''
            self.port = 80
            self.ssl = False
            self.aliases = []
            self.user = 'nobody'
            self.group = 'users'
            self.documentroot = ''
            self.sslkey = None
            self.sslcrt = None
            self.cacrt = None
            self.logdir = None
            self.uid = None
            self.conf = os.path.join(self.main.conf.apache_vhosts_dir,"%s.conf" % self.name)
            self.default_crt = ''
            if sqlobject:
                self.from_sqlobject(sqlobject)

        def from_sqlobject(self,sqlobject):
            self.address = '*'
            self.name = sqlobject.name
            self.user = sqlobject.username
            self.group = 'users'
            self.documentroot = '/var/www/userhomes/%s/sites/%s/www/' % (
                                self.user, self.name)
            self.logdir = '/var/log/apache2/vhosts/%s' % self.name
            self.aliases = sqlobject.aliases
            self.uid = sqlobject.unix_id

        def copy(self, source, dest):
            if not os.path.isfile(source):
                self.main.log.error('File %s does not found, cannot copy' % source)
                return False
            if os.path.isfile(dest):
                if os.path.getmtime(dest) > os.path.getmtime(source):
                    # Destination is newer than source, no need for copying
                    return True
            source = open(source, 'rb')
            dest = open(dest, 'wb')
            while line in source.read(2048):
                dest.write(line)
            dest.close()
            source.close()
            return True

        def copy_ssl(self):
            ssl_dir = '/var/www/userhome/%s/sites/%s/.ssl/' % (self.username, self.name)
            ssl_dest = '/etc/apache2/ssl/users/'

            if not os.path.isdir(ssl_dest):
                try:
                    os.mkdir(ssl_dest)
                    os.chmod(ssl_dest, "0711")
                except IOError as e:
                    self.main.log.exception(e)
                    return False
            ssl_dest = os.path.join(ssl_dest, self.name)
            if not os.path.isdir(ssl_dir):
                # Remove old crt if exist
                if os.path.isdir(ssl_dest):
                    for filename in ['server.key', 'server.crt', 'ca.crt', '']:
                        filename = os.path.join(ssl_dest, filename)
                        try:
                            os.remove(filename)
                        except:
                            pass
                return False
            # .ssl dir exist, copy certificate to safe location to prevent failures as
            # if user deletes certificate and apache can't read it, apache won't reboot 
            user_crt = os.path.join(ssl_dir,'server.crt'))
            user_key = os.path.isfile(os.path.join(ssl_dir,'server.key'))
            ca_crt = os.path.isfile(os.path.join(ssl_dir,'ca.crt'))
            if os.path.isfile(user_crt) and os.path.isfile(user_key):
                # test certificate validity
                # TODO: better implementation needed
                valid = subprocess.check_call(['openssl', 'x509', 
                                '-in','"%s"' % user_crt, '-text','-noout'])
                if valid != 0:
                    self.main.log.error('Certificate file %s contains errors' % user_crt)
                    return False
                valid = subprocess.check_call(['openssl', 'rsa', -'in', '"%s"' % user_key,
                                              '-passin', 'file:/dev/urandom'])
                if valid != 0:
                    self.main.log.error('Certificate file %s contains errors' % user_key)
                    return False
                if not os.path.isdir(os.path.join(ssl_dest, self.name)):
                    try:
                        os.mkdir(ssl_dest)
                        os.chmod(ssl_dest, '0711')
                    except IOError as e:
                        self.main.log.exception(e)
                        return False
                if not os.path.isfile(os.path.join(ssl_dest, 'server.key')):
                    self.copy(user_key, os.path.join(ssl_dest, 'server.key'))
                    os.chmod(os.path.join(ssl_dest, 'server.key'),'0400')
                    os.chown(os.path.join(ssl_dest, 'server.key'), 0, 0)
                    self.sslkey = os.path.join(ssl_dest, 'server.key')
                if not os.path.isfile(os.path.join(ssl_dest, 'server.crt')):
                    self.copy(user_crt, os.path.join(ssl_dest, 'server.crt'))
                    os.chmod(os.path.join(ssl_dest, 'server.crt'),'0444')
                    os.chown(os.path.join(ssl_dest, 'server.crt'), 0, 0)
                    self.sslcrt = os.path.join(ssl_dest, 'server.crt')
                # copy cacert if exist:
                if os.path.isfile(ca_crt):
                    valid = subprocess.check_call(['openssl', 'x509', '-in', 
                                        '"%s"'% ca_crt, '-text', '-noout'])
                    if valid == 0:
                         self.copy(ca_crt, os.path.join(ssl_dest, 'ca.crt'))
                         os.chmod(os.path.join(ssl_dest, 'ca.crt'),'0444')
                         os.chown(os.path.join(ssl_dest, 'ca.crt'), 0, 0)
                return True
            return False

        def default_ssl(self):
            if not self.conf.apache_default_crt or not self.conf.apache_default_key:
                return False
            self.sslcrt = self.conf.apache_default_crt
            self.sslkey = self.conf.apache_default_key
            if self.conf.apache_default_cacert:
                self.cacrt = self.conf.apache_default_cacert
            return True

        def test_ssl(self):
            if not self.conf.apache_ssl or not self.conf.apache_ssl_domain:
                return False

            if '.%s' % self.main.conf.apache_ssl_domain.lower() in self.name:
                return self.default_ssl()
            if self.name.lower() == self.main.conf.apache_ssl_domain.lower():
                return self.default_ssl()
            # check .ssl/
            if self.copy_ssl():
                return True
            return False

        def write(self):
            self.test_ssl()
            # create dirs
            b = Process(target=create_dirs, args(self))
            b.start()
            b.join()
            try:
                f = open(os.path.join(self.main.conf.apache_vhosts_dir,"%s.conf" % self.name),'w+')
            except IOError:
                self.main.log.error('Cannot write to file %s! Please check config' % 
                    os.path.join(self.main.conf.apache_vhosts_dir,"%s.conf" % self.name))
            f.write(self.as_text())
            f.write(self.as_text(True))

        def remove(self):
            try:
                if os.path.exist(self.conf):
                    self.remove(self.conf)
            except IOError as e:
                self.main.log.error('Cannot remove file %s, %s' % (self.conf, e))

        def as_text(self, ssl=False):
            if ssl and not self.ssl:
                return ''
            if ssl:
                port = 443
            else:
                port = self.port
            a = []
            for alias in self.aliases:
                if alias:
                    a.append(alias)
            self.aliases = a
            retval = "<VirtualHost %s:%s>\n" % (self.address, port)
            retval += "  DocumentRoot %s\n" % self.documentroot
            retval += "  ServerName %s\n" % self.name
            if len(self.aliases) > 0:
                retval += " ServerAlias %s\n" % ' '.join(self.aliases)
            retval += "  ErrorLog %s\n" % os.path.join(self.main.conf.apache_log_dir, self.name, 'error.log')
            retval += "  CustomLog %s combined\n" % os.path.join(self.main.conf.apache_log_dir, self.name, 'access.log')
            retval += "  SuexecUserGroup %s %s\n" % (self.user, self.group)
            if ssl:
                retval += "SSL-"
                pass
            retval += "</VirtualHost>\n"
            return retval

    def get_vhost(self, vhost):
        """Get vhost object from file
        USELESS!!!!"""
        vhost = self.Vhost(self)
        try:
            f = open(os.path.join(self.conf.apache_conf_dir, self.vhosts_file), 'r')
        except IOError:
            self.log.error('File %s does not exist! Please check config' % os.path.join(
                      self.conf.apache_conf_dir, self.vhosts_file))
            return None
        for line in f.readlines():
	        line = line.strip()
	        if '<virtualhost ' in line.lower():
	            vhost = self.Vhost(self)
	            line = line[13:-1].strip()
	            address, port = line.split(':')
	            vhost.address = address
	            if '>' in port:
	                port = port[:-1]
	            vhost.port = port
	        elif 'servername' in line.lower():
	            vhost.name = line[11:].strip()
	        elif 'serveralias' in line.lower():
	            vhost.aliases = line[11:].strip().split()
	        elif 'sslengine on' in line.lower():
	            vhost.ssl = True
	        elif 'documentroot' in line.lower():
	            line = line[13:].strip()
	            vhost.documentroot = line
	        elif 'suexecusergroup' in line.lower():
	            line = line[15:].strip()
	            user,group = line.split()
	            vhost.user=user
	            vhost.group = group
	        elif '</virtualhost>' in line.lower():
	            if vhost.name == vhost:
	                f.close()
	                return vhost
	        f.close()

    def insert(self, sqlobject, table):
        """Process apache configs to server"""
        print('TABLE: %s' % table)
        if table == 's_vhosts':
            self.log.debug('Creating some apache configs here...')
            self.log.debug('Vhost name: %s' % sqlobject.name)
            self.log.debug('%s' % vars(sqlobject))
            vhost = self.Vhost(self, sqlobject)
            self.log.debug(vhost.as_text())
            vhost.write()
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