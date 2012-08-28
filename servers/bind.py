from libs import renkiserver
from libs.services import S_services, T_domains
from libs.conf import Option

import os
import subprocess
from iscpy import ParseISCString, MakeISC
from tempfile import mkstemp
from shutil import move
from datetime import datetime

import dns.query
import dns.tsigkeyring
import dns.update
from dns.tsig import PeerBadKey

from sqlalchemy.orm.exc import NoResultFound

# Bind config service for renki
# TODO:
# dns update
# ns-server settings from database
#
__version__ = '0.0.2'

class RenkiServer(renkiserver.RenkiServer):
    def __init__(self):
        renkiserver.RenkiServer.__init__(self, name='dns')
        self.name = 'dns'
        self.config_options = [
            Option('bind_secret', mandatory=True, module='bind', type='str'),
            Option('bind_secret_name', mandatory=True, module='bind', type='str'),
            Option('bind_zones_conf', default='/etc/bind/zones.conf', module='bind', type='str'),
            Option('bind_zones_dir', mandatory=True, module='bind', type='str'),
            Option('bind_master', default=True, module='bind', type='bool'),
            Option('bind_secret_algorithm', default='hmac-md5',
                values=['hmac-md5', 'hmac-sha1', 'hmac-sha224', 'hmac-sha256',
                'hmac-sha384', 'hmac-sha512'], type='str', module='bind', mandatory=True)]
        self.tables = ['t_domains', 't_dns_entries']
        self.keyring = None

    def get_domain(self, t_domains_id):
        try:
            return self.srv.session.query(T_domains).filter(
                T_domains.t_domains_id == t_domains_id).one()
        except:
            self.srv.session.rollback()
            return None

    def create_keyring(self):
        if not self.keyring:
            self.keyring = dns.tsigkeyring.from_text({
                str(self.conf.bind_secret_name) : str(self.conf.bind_secret)
            })
        return True

    def update_dns_value(self, sqlobject, delete=False):
        """Update dns value"""
        self.create_keyring()
        domain = self.get_domain(sqlobject.t_domains_id)
        if not domain:
            self.log.error('Cannot get domain for t_domains_id %s' % sqlobject.t_domains_id)
            return
        if self.parse_inetlist(domain.masters):
            # this server is not master
            return True
        if not self.conf.bind_master:
            # this server is not master
            return True
        value = str(sqlobject.value).split('/')[0]
        update = dns.update.Update(str(domain.name), keyring=self.keyring,
                    keyalgorithm=str(self.conf.bind_secret_algorithm).lower())
        if delete:
            update.delete(str(sqlobject.key), str(sqlobject.type), value)
        else:
            update.add(str(sqlobject.key), int(sqlobject.ttl),
                                                str(sqlobject.type), value)
        try:
            response = dns.query.tcp(update, '127.0.0.1')
        except PeerBadKey or PeerBadSignature:
            self.log.error('Cannot update dns entry, secret invalid')
            return False
        if response.rcode() != 0:
            self.log.error('DNS update failed, got error')
            self.log.error(response)
            return False
        if delete:
            self.log.info('Successfully deleted dns-record %s %d IN %s %s' % (
                                    str(sqlobject.key), int(sqlobject.ttl),
                                    str(sqlobject.type), value))
        else:
            self.log.info('Successfully added dns-record %s %d IN %s %s' % (
                                    str(sqlobject.key), int(sqlobject.ttl),
                                    str(sqlobject.type), value))
        return True

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

    def write_zones(self, zone):
        if not zone:
            self.log.error('BUG: empty zone given to write_zones')
            return
        try:
            zone = MakeISC(zone)
            move(self.conf.bind_zones_conf, "%s.old" % self.conf.bind_zones_conf)
            new = open(self.conf.bind_zones_conf, 'w')
            new.write(zone)
            new.close()
            os.remove("%s.old" % self.conf.bind_zones_conf)
        except Exception as e:
            self.log.error('Cannot write DNS changes to config file %s' % self.conf.bind_zones_conf)
            self.log.exception(e)
            return False
        return True

    def sanitize_email(self, address):
        return address.replace('@','.')

    def create_serial(self):
        return datetime.strftime(datetime.now(), '%Y%m%d00')

    def get_zones(self):
        old = open(self.conf.bind_zones_conf, 'r')
        conf = ParseISCString(old.read())
        old.close()
        return conf

    def get_dns_servers(self):
        return self.srv.session.query(S_services).filter(
        S_services.service_type=='DNS', S_services.active == True).all()

    def zone_file(self, name):
        return os.path.join(self.conf.bind_zones_dir, "%s.conf" % name)

    def add_zone(self, sqlobject, create_zone=True, overwrite=False):
        if not sqlobject.dns:
            # do not create dns configs for domains which dont have dns
            return True
        zone = 'zone "%s"' % sqlobject.name
        conf = self.get_zones()
        if zone in conf and not overwrite:
            self.log.error('Cannot add new zone %s, already exists' % sqlobject.name)
            return True
        if create_zone:
            # Get DNS-servers
            dns_servers = self.get_dns_servers()
            my_hostname = 'localhost'
            for dns_server in dns_servers:
                if dns_server.address in self.conf.hostnames:
                    my_hostname = dns_server.address
            try:
                f = open(self.zone_file(sqlobject.name), 'w')
                f.write(';This is automatically generated file, do not modify this\n')
                f.write('$ORIGIN .\n')
                f.write('$TTL %s\n' % sqlobject.ttl)
                f.write('%s IN SOA %s. %s. (\n' % (sqlobject.name, my_hostname, self.sanitize_email(sqlobject.admin_address)))
                f.write('%s\n' % self.create_serial())
                f.write('%s\n' % sqlobject.refresh_time)
                f.write('%s\n' % sqlobject.retry_time)
                f.write('%s\n' % sqlobject.expire_time)
                f.write('%s\n' % sqlobject.minimum_cache_time)
                f.write(');\n')
                for dns_server in dns_servers:
                    f.write(' IN NS %s.\n' % dns_server.address)
                f.close()
            except IOError as e:
			    self.log.error('Cannot write to zone file %s' % self.zone_file(sqlobject.name))
			    self.log.exception(e)
			    return False
        if not self.conf.bind_master:
		    conf[zone] = {'type' : 'slave',
		             'allow-transfer' :  {'key "%s"' % self.conf.bind_secret_name : True},
		             'masters' : {'ns-master': True},
		             'file': '"%s"' % self.zone_file(sqlobject.name)}
        else:
            conf[zone] = {'allow-transfer' : {'ns-slaves': True,
                     'key "%s"' % self.conf.bind_secret_name: True },
                     'type' : 'master',
                     'allow-update': { 'key "%s"' % self.conf.bind_secret_name: True },
                     'file': '"%s"' % self.zone_file(sqlobject.name)}
        allow_transfer = self.parse_inetlist(sqlobject.allow_transfer)
        if allow_transfer:
            # add allow transfer addresses
            for ip in allow_transfer:
                conf[zone]['allow-transfer'][str(ip)] = True
        # if masters set, overwrite defaults
        masters = self.parse_inetlist(sqlobject.masters)
        if masters:
            if len(masters) > 0:
                conf[zone]['masters'] = {}
                conf[zone]['type'] = 'slave'
                for ip in masters:
                    conf[zone]['masters'][str(ip)] = True
                    conf[zone]['allow-transfer'][str(ip)] = True
        return self.write_zones(conf)

    def reload(self, zone=None):
        """Reload subprocess with rndc"""
        if zone:
            if type(zone) != type(str()):
                self.log.error('Invalid zone %s given' % zone)
                return False
            retval = subprocess.Popen(['rndc', 'reload', zone], stderr=subprocess.PIPE, stdout=subprocess.PIPE)
        else:
            retval = subprocess.Popen(['rndc','reload'], stderr=subprocess.PIPE, stdout=subprocess.PIPE)
        retval.wait()
        if retval.returncode != 0:
            self.log.error('rndc failed with retval code %d' % retval.returncode)
            self.log.error('rndc output: %s' % retval.stderr.read())
            return False
        self.log.debug('rndc: %s' % retval.stdout.read())
        return True

    def delete_zone(self, sqlobject):
        conf = self.get_zones()
        zone = 'zone "%s"' % sqlobject.name
        if zone in conf:
            del conf[zone]
        else:
            self.log.error('Cannot delete zone %s, does not exists in config file' % sqlobject.name)
        return self.write_zones(conf)

    def insert(self, sqlobject, table):
        """Process dns configs to server"""
        if table == 't_domains':
            self.log.debug('Inserting new domain %s' % sqlobject.name)
            self.log.debug('%s' % vars(sqlobject))
            if self.conf.bind_master:
                # create zonefiles only if this bind is master
                retval = self.add_zone(sqlobject)
            else:
                retval = self.add_zone(sqlobject, create_zone=False)
                if retval:
                    return self.reload()
                return retval
        elif table == 't_dns_entries':
            self.update_dns_value(sqlobject)
        return True

    def update(self, old_sqlobject, new_sqlobject, table):
        """Process dns configs to server"""
        if table == 't_domains':
            update = False
            for obj in ['allow_transfer', 'masters', 'dns']:
                # TODO: do this better
                if vars(old_sqlobject)[obj] != vars(new_sqlobject)[obj]:
                    update = True
                    retval = self.add_zone(new_sqlobject, create_zone=False, overwrite=True)
                    if retval == True:
                        self.reload()
                        break
                    else:
                        return False
            if not new_sqlobject.dns and old_sqlobject.dns:
                update = True
                self.delete_zone(str(old_sqlobject.name))
            if update:
                self.log.debug('Updated!')
            else:
                self.log.debug('Not updated!')
                self.log.debug('OLD: %s' % vars(old_sqlobject))
                self.log.debug('NEW: %s' % vars(new_sqlobject))
        elif table == 't_dns_entries':
            self.update_dns_value(old_sqlobject, delete=True)
            self.update_dns_value(new_sqlobject)
        return True

    def delete(self, sqlobject, table):
        """Process dns configs to server"""
        if table == 't_domains':
            self.log.debug('Deleting some dns configs here...')
            self.log.debug('Domain name: %s' % sqlobject.name)
            retval = self.delete_zone(sqlobject)
            if retval:
                self.reload()
        elif table == 't_dns_entries':
            self.update_dns_value(sqlobject, delete=True)
        return True