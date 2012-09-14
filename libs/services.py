from sqlalchemy import Table, Column, Integer, create_engine, MetaData, select
from sqlalchemy.orm import mapper, sessionmaker, synonym, relationship
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.engine.url import URL
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm.exc import NoResultFound, MultipleResultsFound
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql.base import ARRAY, INET
import logging

Base = declarative_base()

class DatabaseError(Exception):
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return "%s" % self.value

class DoesNotExist(Exception):
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return "%s" % self.value

class Services():
    def __init__(self,conf,verbose=False):
        self.db = None
        self.conf = conf
        self.tables = {}
        if verbose or conf.database_debug:
            self.verbose = True
            logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
        else:
            self.verbose = False
            logging.getLogger('sqlalchemy.engine').setLevel(logging.ERROR)
        self.log = logging.getLogger('services')
        self.log.info('Connecting to database')
        self.connect()
        self.log.info('Connected to database')
        self.session = None
        self.log.info('Getting database schema')
        self.getSession()
        self.log.info('Got database schema')
        if not self.session:
            raise RuntimeError('Invalid login')

    def connect(self):
        connstring = URL('postgresql', username=self.conf.services_username,
                         password=self.conf.services_password,
                         database=self.conf.services_database,
                         host=self.conf.services_server)
        if self.conf.services_port:
            connstring = URL('postgresql', username=self.conf.services_username,
                             password=self.conf.services_password,
                             database=self.conf.services_database,
                             host=self.conf.services_server,
                             port=self.conf.services_port)
        self.db = create_engine(connstring,encoding='utf-8', echo=self.verbose,
                                pool_recycle=120)

    def getSession(self, map_tables=True):
        """Function to get session"""
        if not map_tables:
            Session = sessionmaker(bind=self.db)
            self.session = Session()
            return
        try:
            metadata = MetaData(self.db)
            change_log = Table('change_log', metadata,
                Column("t_change_log_id", Integer, primary_key=True),
                autoload=True)
            mapper(Change_log, change_log)
            if 's_vhosts' in self.conf.tables:
                s_vhosts = Table('s_vhosts', metadata,
                    Column("t_vhosts_id", Integer, primary_key=True),
                    autoload=True)
                mapper(S_vhosts, s_vhosts)
                self.tables['s_vhosts'] = S_vhosts
                s_vhosts_history = Table('s_vhosts_history', metadata,
                    Column("s_vhosts_history_id", Integer, primary_key=True),
                    autoload=True)
                mapper(S_vhosts_history, s_vhosts_history)
                self.tables['s_vhosts_history'] = S_vhosts_history
            if 't_domains' in self.conf.tables:
                t_domains = Table('t_domains', metadata,
                    #Column("t_domains_id", Integer, primary_key=True),
                    autoload=True)
                mapper(T_domains, t_domains)
                self.tables['t_domains'] = T_domains
                t_domains_history = Table('t_domains_history', metadata,
                autoload=True)
                mapper(T_domains_history, t_domains_history)
                self.tables['t_domains_history'] = T_domains_history
            if 's_user_ports' in self.conf.tables:
                s_user_ports = Table('s_user_ports', metadata,
                    Column("t_user_ports_id", Integer, primary_key=True),
                    autoload=True)
                mapper(S_user_ports, s_user_ports)
                self.tables['s_user_ports'] = S_user_ports
                s_user_ports_history = Table('s_user_ports_history', metadata,
                autoload=True)
                mapper(S_user_ports_history, s_user_ports_history)
                self.tables['s_user_ports_history'] = S_user_ports_history
            if 't_dns_records':
                t_dns_records = Table('t_dns_records', metadata,
                    Column("t_dns_records_id", Integer, primary_key=True),
                    autoload=True)
                mapper(T_dns_records, t_dns_records)
                self.tables['t_dns_records'] = T_dns_records
                t_dns_records_history = Table('t_dns_records_history', metadata,
                    Column("t_dns_records_history_id", Integer, primary_key=True),
                    autoload=True)
                mapper(T_dns_records_history, t_dns_records_history)
                self.tables['t_dns_records_history'] = T_dns_records_history
            s_services = Table('s_services', metadata,
                    Column("t_services_id", Integer, primary_key=True),
                    autoload=True)
            mapper(S_services, s_services)
            Session = sessionmaker(bind=self.db)
            self.session = Session()
        except OperationalError as e:
            raise RuntimeError(e)

    def reconnect(self):
        self.session.rollback()

class T_domains(object):
    pass

class T_domains_history(object):
    pass

class Change_log(object):
        pass

class S_vhosts(object):
    pass

class S_vhosts_history(object):
    pass

class S_user_ports_history(object):
    pass

class S_user_ports(object):
    pass

class S_services(object):
    pass

class T_dns_records_history(object):
    pass

class T_dns_records(object):
    pass
