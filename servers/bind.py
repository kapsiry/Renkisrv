from libs import renkiserver
from libs.services import S_services, T_domains, T_dns_records
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
import dns.zone
import dns.rcode
from dns.tsig import PeerBadKey
from dns.exception import DNSException, FormError

from sqlalchemy.orm.exc import NoResultFound

# Bind config service for renki
# TODO:
# ns-server settings from database
#

__version__ = '0.0.2'

class AlreadyExists(Exception):
    pass

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
        self.tables = ['t_domains', 't_dns_records']
        self.keyring = None

    def get_domain(self, t_domains_id):
        """Get t_domains object"""
        try:
            return self.srv.session.query(T_domains).filter(
                T_domains.t_domains_id == t_domains_id).one()
        except:
            self.srv.session.rollback()
            return None

    def create_keyring(self):
        """Initialize keyring if not exists"""
        if not self.keyring:
            self.keyring = dns.tsigkeyring.from_text({
                str(self.conf.bind_secret_name) : str(self.conf.bind_secret)
            })
        return True

    def check_record(self, key, ttype, value, domain):
        """Check if record already exist in domain
        AXFR used because resolver can also resolve addresses 
        from remote servers"""
        try:
            xfr = dns.query.xfr('127.0.0.1', domain ,keyring=self.keyring,
                      keyalgorithm=str(self.conf.bind_secret_algorithm).lower())
            zone = dns.zone.from_xfr(xfr)
            rdataset = zone.find_rdataset(key, rdtype=ttype)
            for rdata in rdataset:
                if ttype in ['NS','CNAME']:
                    address = rdata.target
                elif ttype == 'MX':
                    address = rdata.exchange
                else:
                    address = rdata.address
                if str(address).rstrip('.') == str(value):
                    return True
        except DNSException or FormError:
            self.log.info('Cannot make axfr query to domain %s' % domain)
        except KeyError:
            # record not found
            pass
        except AttributeError as e:
            self.log.error('BUG: Got attribute error on check_record')
            self.log.exception(e)
        return False

    def update_dns_value(self, sqlobject, delete=False):
        """Update dns value
        if delete is true, delete value instead of adding"""
        self.create_keyring()
        domain = self.get_domain(sqlobject.t_domains_id)
        if not domain:
            if delete:
                # domain already deleted
                return True
            self.log.error('Cannot get domain for t_domains_id %s' % sqlobject.t_domains_id)
            return False
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
            if not self.check_record(sqlobject.key, sqlobject.type, sqlobject.value, domain.name):
                update.add(str(sqlobject.key), int(sqlobject.ttl),
                                                str(sqlobject.type), value)
            else:
                self.log.debug('Record %s %d IN %s %s already exists' % (
                                    str(sqlobject.key), int(sqlobject.ttl),
                                    str(sqlobject.type), value))
                return True
        try:
            response = dns.query.tcp(update, '127.0.0.1')
        except PeerBadKey or PeerBadSignature:
            self.log.error('Cannot update dns entry, secret invalid')
            return False
        if response.rcode() != 0:
            self.log.error('DNS update failed, got error %s on domain %s' % (
                            dns.rcode.to_text(response.rcode()), domain.name))
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
        """Parse silly per char inet array to per ip python array
        {'1','0','.','1','0','.','1','0','.','1','0'} -> ['10.10.10.10']
        TODO: report bug to sqlalchemy"""
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
        except IOError as e:
            self.log.error('Cannot write DNS changes to config file %s' % \
                           self.conf.bind_zones_conf)
            return False
        except Exception as e:
            self.log.exception(e)
            return False
        return True

    def sanitize_email(self, address):
        return address.replace('@','.')

    def create_serial(self):
        """Create simple serial"""
        return datetime.strftime(datetime.now(), '%Y%m%d00')

    def get_zones(self):
        """Get zones config file and return parsed config"""
        old = open(self.conf.bind_zones_conf, 'r')
        conf = ParseISCString(old.read())
        old.close()
        return conf

    def get_dns_servers(self, sqlobject):
        """Get NS servers for domain given in sqlobject"""
        return self.srv.session.query(T_dns_records).filter(
        T_dns_records.t_domains_id == sqlobject.t_domains_id,
        T_dns_records.type == 'NS').all()

    def zone_file(self, name):
        """Return zonefile name"""
        return os.path.join(self.conf.bind_zones_dir, "%s.db" % name)

    def add_zone(self, sqlobject, create_zone=True, overwrite=False):
        """Create zone configs
        Create also simple zone if create_zone is True
        if overwrite is True, supress already exists errors and overwrite"""
        if not sqlobject.dns:
            # do not create dns configs for domains which don't have dns
            return True
        zone = 'zone "%s"' % sqlobject.name
        conf = self.get_zones()
        if zone in conf and not overwrite:
            self.log.error('Cannot add new zone %s, already exists' % sqlobject.name)
            raise AlreadyExists()
        if create_zone:
            # Get DNS-servers
            dns_servers = self.get_dns_servers(sqlobject)
            my_hostname = 'localhost'
            # Resolve my real hostname
            # TODO: Fix this to get hostname from t_services table
            for dns_server in dns_servers:
                if dns_server.value in self.conf.hostnames:
                    my_hostname = dns_server.value
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
                    f.write(' IN NS %s\n' % dns_server.value)
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

    def reload(self, zone=None, config=False):
        """Use rndc to reload config
        if zone is given run rndc reload zone
        if config is given, run rndc reconfig
        else run rndc reload
        """
        if config:
            retval = subprocess.Popen(['rndc', 'reconfig'],
                                stderr=subprocess.PIPE, stdout=subprocess.PIPE)
        elif zone:
            if type(zone) != type(str()):
                self.log.error('BUG: Invalid zone %s given' % zone)
                return False
            retval = subprocess.Popen(['rndc', 'reload', zone],
                                stderr=subprocess.PIPE, stdout=subprocess.PIPE)
        else:
            retval = subprocess.Popen(['rndc','reload'], stderr=subprocess.PIPE,
                                                        stdout=subprocess.PIPE)
        retval.wait()
        if retval.returncode != 0:
            self.log.error('rndc failed with retval code %d' % retval.returncode)
            self.log.error('rndc output: %s' % retval.stderr.read())
            return False
        stdout = retval.stdout.read()
        if len(stdout) > 0:
            self.log.debug('rndc: %s' % stdout)
        return True

    def delete_zone(self, sqlobject):
        """Remove zone from zones config file"""
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
                try:
                    retval = self.add_zone(sqlobject)
                except AlreadyExists:
                    return True
                if retval:
                    return self.reload(config=True)
            else:
                try:
                    retval = self.add_zone(sqlobject, create_zone=False)
                except AlreadyExists:
                    return True
                if retval:
                    return self.reload(config=True)
            return retval
        elif table == 't_dns_records':
            return self.update_dns_value(sqlobject)
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
                # only dns change is important
                self.delete_zone(str(old_sqlobject.name))
        elif table == 't_dns_records':
            self.update_dns_value(old_sqlobject, delete=True)
            return self.update_dns_value(new_sqlobject)
        return True

    def delete(self, sqlobject, table):
        """Process dns configs to server"""
        if table == 't_domains':
            self.log.debug('Deleting some dns configs here...')
            self.log.debug('Domain name: %s' % sqlobject.name)
            retval = self.delete_zone(sqlobject)
            if retval:
                self.reload()
        elif table == 't_dns_records':
            return self.update_dns_value(sqlobject, delete=True)
        return True