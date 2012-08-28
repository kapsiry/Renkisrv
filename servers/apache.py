from libs import renkiserver
import os, stat
import time
import subprocess
from multiprocessing import Process

from libs.conf import Option
from libs.utils import get_uid, drop_privileges, recursive_mkdir, copy

# Apache config service for renki

__version__ = '0.0.1'

def create_dirs(vhost):
    # This is executed as subprocess
    # logdir
    logdir = vhost.log_dir()
    if not os.path.isdir(logdir):
        try:
            os.mkdir(logdir)
            # 0=root, 4=admin
            os.chown(logdir, 0, 4)
            os.chmod(logdir, 0750)
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
        if not os.path.isdir(vhost.documentroot()):
            recursive_mkdir(vhost.documentroot())
    except Exception as e:
        vhost.main.log.error('Cannot create document root!')
        vhost.main.log.exception(e)
        return False

    vhost_basedir = vhost.documentroot().rsplit('/')[:-1]
    vhost_basedir[0] = '/%s' % vhost_basedir[0]
    vhost_basedir = os.path.join(*vhost_basedir)
    # create logs symlink
    link = os.path.join(vhost_basedir, 'log')
    if os.path.exists(link) and not os.path.islink(link):
        # move file to log.old
        subprocess.Popen(['mv', '-fT', link, '%s.old' % link])
    if not os.path.islink(link):
        try:
            os.symlink(vhost.log_dir(), link)
        except Exception as e:
            vhost.main.log.error('Cannot create symlink %s -> %s' % (vhost.log_dir(), link))
            vhost.main.log.exception(e)
            return False

    php_handlers = [os.path.join(vhost.documentroot(), 'php5.fcgi')]

    if vhost.ssl:
        vhost_docroot = vhost.documentroot(ssl=True)
        if not os.path.isdir(vhost_docroot):
            os.mkdir(vhost_docroot)
        php_handlers.append(os.path.join(vhost_docroot, 'php5.fcgi'))

    # create php handler
    for php_handler in php_handlers:
        if not os.path.exists(php_handler):
            try:
                f = open(php_handler,'w')
                f.write('#!/usr/bin/php5-cgi\n')
                f.close()
                os.chmod(php_handler, 0700)
            except Exception as e:
                vhost.main.log.error('Cannot create php-handler php5.fcgi')
                vhost.main.log.exception(e)
                return False
    return True

class Vhost(object):
    def __init__(self, main, sqlobject = None):
        self.main = main
        self.address = ''
        self.port = 80
        self.name = None
        self.ssl = False
        self.aliases = []
        self.redirects = []
        self.user = 'nobody'
        self.group = 'users'
        self.sslkey = None
        self.sslcrt = None
        self.cacrt = None
        self.uid = None
        self.default_crt = ''
        if sqlobject:
            self.from_sqlobject(sqlobject)

    def conf(self):
        if self.name:
            return os.path.join(self.main.conf.apache_vhosts_dir,"%s.conf" % self.name)
        else:
            return None

    def documentroot(self, ssl=False):
        return self.format_path('apache_documentroot', ssl=ssl)

    def log_dir(self, ssl=False):
        return self.format_path('apache_log_dir', ssl=ssl)

    def format_path(self, conf, ssl):
        if conf not in self.main.conf.__dict__:
            raise RuntimeError('BUG: unexist conf variable %s' % conf)
        if ssl:
            ssl = 'secure-www'
        else:
            ssl = 'www'
        if not self.name or not self.user:
            raise RuntimeError('Vhost object not fully configured')
        return self.main.conf.__dict__[conf] % {'user': self.user,
                'type': ssl, 'vhost': self.name}

    def from_sqlobject(self,sqlobject):
        self.address = '*'
        self.name = sqlobject.name
        self.user = sqlobject.username
        self.group = 'users'
        self.aliases = sqlobject.aliases
        self.redirects = sqlobject.redirects
        self.uid = sqlobject.unix_id


    def copy_ssl(self):
        """Copy ssl-cert from user dir to safe location"""
        ssl_dir = '/var/www/userhome/%s/sites/%s/.ssl/' % (self.username, self.name)
        ssl_dest = '/etc/apache2/ssl/users/'

        if not os.path.isdir(ssl_dest):
            try:
                os.mkdir(ssl_dest)
                os.chmod(ssl_dest, 0711)
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
        user_crt = os.path.join(ssl_dir,'server.crt')
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
                    os.chmod(ssl_dest, 0711)
                except IOError as e:
                    self.main.log.exception(e)
                    return False
            if not os.path.isfile(os.path.join(ssl_dest, 'server.key')):
                copy(user_key, os.path.join(ssl_dest, 'server.key'))
                os.chmod(os.path.join(ssl_dest, 'server.key'),0400)
                os.chown(os.path.join(ssl_dest, 'server.key'), 0, 0)
                self.sslkey = os.path.join(ssl_dest, 'server.key')
            if not os.path.isfile(os.path.join(ssl_dest, 'server.crt')):
                copy(user_crt, os.path.join(ssl_dest, 'server.crt'))
                os.chmod(os.path.join(ssl_dest, 'server.crt'),0444)
                os.chown(os.path.join(ssl_dest, 'server.crt'), 0, 0)
                self.sslcrt = os.path.join(ssl_dest, 'server.crt')
            # copy cacert if exist:
            if os.path.isfile(ca_crt):
                valid = subprocess.check_call(['openssl', 'x509', '-in',
                                    '"%s"'% ca_crt, '-text', '-noout'])
                if valid == 0:
                     copy(ca_crt, os.path.join(ssl_dest, 'ca.crt'))
                     os.chmod(os.path.join(ssl_dest, 'ca.crt'), 0444)
                     os.chown(os.path.join(ssl_dest, 'ca.crt'), 0, 0)
            return True
        return False

    def default_ssl(self):
        """Set default ssl to vhost"""
        if not self.main.conf.apache_default_crt or not self.main.conf.apache_default_key:
            return False
        self.sslcrt = self.main.conf.apache_default_crt
        self.sslkey = self.main.conf.apache_default_key
        if self.main.conf.apache_default_cacert:
            self.cacrt = self.main.conf.apache_default_cacert
        return True

    def test_ssl(self):
        """Test vhost ssl"""
        if not self.main.conf.apache_ssl or not self.main.conf.apache_ssl_domain:
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
        """Write vhost to file"""
        self.test_ssl()
        # create dirs
        b = Process(target=create_dirs, args=(self,))
        b.start()
        b.join()
        try:
            f = open(os.path.join(self.main.conf.apache_vhosts_dir,"%s.conf" % self.name),'w+')
        except IOError:
            self.main.log.error('Cannot write to file %s! Please check config' %
                os.path.join(self.main.conf.apache_vhosts_dir,"%s.conf" % self.name))
        f.write(self.as_text())

    def delete(self):
        """Delete vhost"""
        try:
            if os.path.exists(self.conf()):
                os.remove(self.conf())
        except IOError as e:
            self.main.log.error('Cannot remove file %s, %s' % (self.conf(), e))

    def as_text(self):
        """Output vhost as Apache2 config"""
        a = []
        for alias in self.aliases:
            if alias:
                a.append(alias)
        self.aliases = a
        a = []
        for redirect in self.redirects:
            if redirect:
                a.append(redirect)
        self.redirects = a
        ssl = False
        retval = ''
        while True:
            if ssl and not self.ssl:
                break
            port = self.port
            if ssl:
                port = 443
            retval += "<VirtualHost %s:%s>\n" % (self.address, port)
            retval += "  DocumentRoot %s\n" % self.documentroot(ssl)
            retval += "  ServerName %s\n" % self.name
            if len(self.aliases) > 0:
                retval += " ServerAlias %s\n" % ' '.join(self.aliases)
            retval += "  ErrorLog %s\n" % os.path.join(self.log_dir(), 'error.log')
            retval += "  CustomLog %s combined\n" % os.path.join(self.log_dir(), 'access.log')
            retval += "  SuexecUserGroup %s %s\n" % (self.user, self.group)
            if ssl:
                retval += "  SSLEngine On\n"
                if self.cacrt:
                    retval += "  SSLCACertificateFile %s\n" % self.cacrt
                retval += "  SSLCertificateFile %s\n" % self.sslcrt
                retval += "  SSLCertificateKeyFile %s\n" % self.sslkey
            retval += "</VirtualHost>\n"
            # redirects also
            for redirect in self.redirects:
                retval += "<VirtualHost %s:%s>\n" % (self.address, port)
                retval += "  ServerName %s\n" % redirect
                if not ssl:
                    retval +=  "  Redirect permanent / http://%s/\n" % (self.name)
                else:
                    retval +=  "  Redirect permanent / https://%s/\n" % (self.name)
                retval += "</VirtualHost>\n"
            if ssl:
                #loop most two round
                break
            ssl = True
        return retval

class RenkiServer(renkiserver.RenkiServer):
    """Vhost generator
    TODO:
    - locked accounts
    - users ssl-support will not work at all
     - maybe needs daemon to crawl through .ssl/ dirs
    """

    def __init__(self):
        renkiserver.RenkiServer.__init__(self, name='apache')
        self.tables = ['s_vhosts']
        self.conf_options = [
            Option('apache_ssl', default=False, module='apache'),
            Option('apache_ssl_domain', mandatory=True, variable='apache_ssl', type='str', module='apache'),
            Option('apache_log_dir', default='/var/log/apache2/%(vhost)s', type='str', module='apache'),
            Option('apache_default_ssl_key', mandatory=True, variable='apache_ssl', type='str', module='apache'),
            Option('apache_default_ssl_crt', mandatory=True, variable='apache_ssl', type='str', module='apache'),
            Option('apache_default_ssl_cacrt', default=None, type='str', module='apache'),
            Option('apache_vhosts_dir', default='/etc/apache2/', type='str', module='apache'),
            Option('apache_documentroot', default='/var/www/', type='str', module='apache')]

    def reload_apache(self):
        """We need maybe better way to handle situations when multiple changes has made once"""
        if subprocess.call(['/usr/sbin/apache2ctl', 'configtest']) == 0:
            retval = subprocess.call(['/usr/sbin/apache2ctl', 'graceful'])
            if retval != 0:
                self.log.error('/usr/sbin/apache2ctl graceful returned %s' % retval)
                return False
            return True
        self.log.error('apache2ctl configtest failed!')
        return False

    def insert(self, sqlobject, table):
        """Process apache configs to server"""
        if table == 's_vhosts':
            self.log.debug('Creating some apache configs here...')
            self.log.debug('Vhost name: %s' % sqlobject.name)
            self.log.debug('%s' % vars(sqlobject))
            vhost = Vhost(self, sqlobject)
            self.log.debug(vhost.as_text())
            vhost.write()
            self.reload_apache()
        return True

    def update(self, old_sqlobject, new_sqlobject, table):
        """Process apache configs to server"""
        if table == 's_vhosts':
            self.log.debug('Updating some apache configs here...')
            self.log.debug('Vhost name: %s' % new_sqlobject.name)
            self.log.debug('%s' % vars(new_sqlobject))
            vhost = Vhost(self, sqlobject)
            vhost.write()
            self.reload_apache()
        return True

    def delete(self, sqlobject, table):
        """Process apache configs to server"""
        if table == 's_vhosts':
            self.log.debug('Deleting some apache configs here...')
            self.log.debug('Vhost name: %s' % sqlobject.name)
            vhost = Vhost(self, sqlobject)
            vhost.delete()
            self.reload_apache()
        return True
