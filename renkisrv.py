#!/usr/bin/env python
# -*- encoding: utf-8 -*-

__version__ = 'v0.1'

from services import *
import sys
from os import path
import select
from libs.conf import Option, Config
import logging
from sqlalchemy.orm import class_mapper
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from psycopg2 import OperationalError, DatabaseError

from time import sleep

formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
x = logging.getLogger()
h = logging.StreamHandler()
h.setFormatter(formatter)
x.addHandler(h)
x.setLevel(logging.DEBUG)


config_variables = [
    Option('servers', default=None, type='list'),
    Option('services_username', mandatory=True, type='str'),
    Option('services_password', mandatory=True, type='str'),
    Option('services_port', default=None, type='int'),
    Option('services_server', mandatory=True, type='str'),
    Option('services_database', mandatory=True, type='str'),
    Option('debug', default=False, type='bool'),
    Option('database_debug', default=False, type='bool'),
    Option('log_file', default=None),
    Option('hostnames', mandatory=True)
]

class RenkiSrv(object):
    def __init__(self, conf):
        self.log = logging.getLogger('renkisrv')
        self.conf = Config(config_variables, config_file)
        h = logging.FileHandler(filename="renkiserv.log")
        if self.conf.debug:
            self.log.setLevel(logging.DEBUG)
            h.setLevel(logging.DEBUG)
        else:
            self.conf.setLevel(logging.WARNING)
            h.setLevel(logging.WARNING)
        self.log.debug("Initializing RenkiSrv")
        self.workers = []
        self.workqueue = []
        self.populate_workers()
        try:
            self.srv = Services(self.conf)
        except RuntimeError as e:
            log.exception(e)
            log.error("Cannot login to server, please check config")
            sys.exit(1)
        for worker in self.workers:
            worker.srv = self.srv
        self.conn = None
        self.cursor = None
        self.connect()
        self.log.debug("Initialized RenkiSrv")
        latest = self.srv.session.query(Change_log).order_by(Change_log.created.desc()).first()
        try:
            self.latest_transaction = latest.transaction_id
        except:
            self.latest_transaction = 0
        # do not leave open transaction
        self.srv.session.commit()

    def connect(self):
        """Create self.conn"""
        if not self.conn:
            self.conn = self.srv.db.connect().connection
            self.conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            self.cursor = self.conn.cursor()

    def reconnect(self):
        """Reconnect to database"""
        self.log.debug("Reconnecting to database")
        if not self.srv:
            self.srv = Services(self.conf)
        first = True
        try:
            self.conn.close()
        except:
            pass
        self.conn = None
        while 1:
            try:
                self.srv.session.rollback()
                self.connect()
                self.cursor.execute('SELECT 1')
                self.cursor.execute('LISTEN sqlobjectupdate')
                self.log.info('Connected to database')
                break
            except OperationalError as e:
                #log.exception(e)
                pass
            except DatabaseError as e:
                log.exception(e)
            except Exception as e:
                log.exception(e)
            if first:
                # don't print text once in five seconds
                self.log.error('Database not available')
                first = False
            sleep(5)
        #TODO needs to check works missed on break
        self.feed_workers()
        self.log.error('Reconnected to database')

    def populate_workers(self):
        """Populate workers list with service workers"""
        for server in self.conf.servers:
            try:
                module = __import__('servers.%s' % server)
                worker = vars(module)[server].RenkiServer()
                worker.conf = self.conf
                for option in worker.config_options:
                    option.module = server
                    self.conf.add_setting(option)
                self.workers.append(worker)
                self.conf.add_tables(worker.tables)
            except ImportError as e:
                if e.args[0] == 'No module named %s' % server:
                    self.log.error('Cannot import nonexistent server %s' % server)
                    self.log.error('Check config')
                else:
                    self.log.exception(e)
                sys.exit(1)

    def feed_workers(self):
        """Get changes and add them to workers"""
        try:
            #sleep(2)
            changes = self.get_changes()
        except Exception as e:
            self.log.error('BUG: Cannot get changes')
            self.log.exception(e)
            return
        if changes:
            self.workqueue.append(change)
            for worker in self.workers:
                worker.add(change)

    def mainloop(self):
        """Run this loop until ctrl + c"""
        self.log.info("Starting mainloop")
        self.log.info('Starting services')
        for worker in self.workers:
            worker.start()
        self.cursor.execute('LISTEN sqlobjectupdate;')
        self.log.info('Waiting for notifications on channel "sqlobjectupdate"')
        while True:
            try:
                # close open transactions if any()
                self.srv.session.commit()
                if select.select([self.conn],[],[],30) == ([],[],[]):
                    self.log.debug('Timeout')
                    try:
                        self.cursor.execute('SELECT 1')
                    except DatabaseError as e:
                        self.reconnect()
                else:
                    self.conn.poll()
                    while self.conn.notifies:
                        notify = self.conn.notifies.pop()
                        self.log.info('Got notify: pid: %s' % notify.pid)
                        self.feed_workers()
            except OperationalError as e:
                # postgresql disconnected.
                self.log.error('Postgresql connection lost, trying to reconnect')
                self.log.exception(e)
                self.reconnect()
            except ValueError as e:
                self.srv.session.rollback()
                self.log.exception(e)
                sleep(5)
            restart = []

            for worker in range(0,len(self.workers)):
                    if self.workers[worker].isAlive() is not True:
                        self.log.info('Service %s is dead, restarting' % self.workers[worker].name)
                        restart.append(worker)

            if len(restart) == 0:
                self.workqueue = []

            for num in restart:
                oldworker = self.workers[num]
                worker = oldworker.__class__()
                worker.conf = self.conf
                worker.start()
                self.workers[num] = worker
                for work in self.workqueue:
                    self.workers[num].add(work)
                self.log.info('Service %s restarted and pending %s works send to it' % (self.workers[num].name, len(self.workqueue)))

    def get_changes(self):
        """Get all database changes made after latest check"""
        retval = []
        # get changes from change_log view
        changes = self.srv.session.query(Change_log).filter(Change_log.transaction_id > self.latest_transaction).order_by(Change_log.t_change_log_id).all()

        ## do here some duplicate check
        # delete updates and inserts if also delete to same row
        undups = []
        data_id_index = {}
        for change in changes:
            if change.data_id not in data_id_index:
                data_id_index[change.data_id] = []
            data_id_index[change.data_id].append(change)
        for change in changes:
            if change.event_type == 'DELETE':
                undups.append(change)
            elif change.event_type in ['INSERT', 'UPDATE']:
                keep = True
                for c in data_id_index[change.data_id]:
                    if c.event_type == 'DELETE' and c.table == change.table:
                        keep = False
                if keep:
                    undups.append(change)
        for change in changes:
            # loop over all changes, ignore unknown tables
            if change.table in self.srv.tables:
                self.log.debug('Action %s in table %s' % (change.event_type, change.table))
                results = []
                self.log.debug("Transaction_id: %s" % str(change.transaction_id))
                """results = self.srv.session.execute("SELECT *,xmin,xmax FROM %s WHERE xmin = :transaction" % change.table,
                    {'transaction' : str(change.transaction_id)},
                    mapper=self.srv.tables[change.table]).fetchall()"""
                try:
                    table = self.srv.tables[change.table]
                    #self.log.debug('CLASS MAPPER: %s' % class_mapper(self.srv.tables[change.table]).primary_key[0].name)
                    history_table = self.srv.tables['%s_history' % change.table]
                    history_table_pk = vars(history_table)[class_mapper(self.srv.tables[change.table]).primary_key[0].name]
                except KeyError as e:
                    self.log.error('History table %s_history not found for table %s!' % (change.table,change.table))
                    self.log.exception(e)
                    continue
                try:
                    if change.event_type == 'INSERT':
                        # On insert get only newobject
                        results = self.srv.session.query(self.srv.tables[change.table],Change_log).join(Change_log,
                            Change_log.data_id == class_mapper(table).primary_key[0]).filter(
                            class_mapper(table).primary_key[0] == change.data_id
                            ).filter(Change_log.transaction_id == change.transaction_id).filter(
                            Change_log.table == change.table).filter(
                            Change_log.event_type == 'INSERT').filter(
                            Change_log.t_change_log_id == change.t_change_log_id).all()
                    elif change.event_type == 'UPDATE':
                        # on update get newobject from table and old object from history
                        results = self.srv.session.query(table,Change_log,history_table).join(Change_log,
                            Change_log.data_id == class_mapper(table).primary_key[0]).join(
                            history_table, class_mapper(table).primary_key[0] == history_table_pk).filter(
                            history_table_pk == change.data_id).filter(
                            Change_log.transaction_id == change.transaction_id ).filter(
                            history_table.old_xmax == change.transaction_id).filter(
                            Change_log.table == change.table).filter(
                            Change_log.t_change_log_id == change.t_change_log_id).all()
                    elif change.event_type == 'DELETE':
                        # on delete get oldobject from history
                        results = self.srv.session.query(history_table, Change_log).join(Change_log,
                            Change_log.data_id == history_table_pk).filter(
                            Change_log.transaction_id == change.transaction_id).filter(
                            history_table.old_xmax == change.transaction_id).filter(
                            Change_log.table == change.table).filter(
                            Change_log.event_type == 'DELETE').filter(
                            Change_log.t_change_log_id == change.t_change_log_id).all()
                    for result in results:
                        self.workqueue.append(change)
                        for worker in self.workers:
                            worker.add(result)
                    self.latest_transaction = change.transaction_id
                    # close open transactions if any
                    self.srv.session.commit()
                except IntegrityError or OperationalError or ProgrammingError as e:
                    self.log.error('Error while getting changed data')
                    self.log.exception(e)
            else:
                self.log.debug('No plugins for table %s' % change.table)

    def killall(self):
        """Kill all workers"""
        for worker in self.workers:
            try:
                self.log.info('Stopping service %s' % worker.name)
                worker.kill()
            except Exception as e:
                self.log.exception(e)

if __name__ == '__main__':
    log = logging.getLogger("renkisrv")
    log.info("Welcome to Renkisrv version %s" % __version__)
    config_file = path.join(path.dirname(path.abspath(__file__)),'config.py')
    try:
        renkisrv = RenkiSrv(config_file)
    except Exception as error:
        cla, exc, trbk = sys.exc_info()
        log.error('%s: %s' % (cla.__name__, error))
        log.exception(error)
        log.critical('Renkisrv stopped')
        sys.exit(1)
    try:
        renkisrv.mainloop()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        log.exception(e)
    except:
        log.critical('Got unknown exception')
    renkisrv.killall()
    log.critical('Renkisrv stopped')
