#!/usr/bin/env python
# -*- encoding: utf-8 -*-

__version__ = '0.0.1'

from services import *
import sys
import select
from renkicfg import *
import logging
#from sqlalchemy import select as alchemyselect
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

class RenkiSrv(object):
    def __init__(self, conf):
        self.log = logging.getLogger('renkisrv')
        self.conf = conf
        self.log.debug("Initializing RenkiSrv")
        self.workers = []
        self.workqueue = []
        self.populate_workers()
        try:
            self.srv = Services(conf)
        except RuntimeError as e:
            log.exception(e)
            log.error("Cannot login to server, please check config")
            sys.exit(1)
        self.conn = None
        self.cursor = None
        self.connect()
        self.log.debug("Initialized RenkiSrv")
        latest = self.srv.session.query(Change_log).order_by(Change_log.created.desc()).first()
        print(dir(latest))
        print(vars(Change_log.table))
        self.latest_transaction = latest.transaction_id
        
    def connect(self):
        if not self.conn:
            self.conn = self.srv.db.connect().connection
            self.conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            self.cursor = self.conn.cursor()
            
    def reconnect(self):
        self.log.debug("Reconnecting to database")
        if not self.srv:
            self.srv = Services(self.conf)
        first = True
        while 1:
            try:
                self.connect()
                self.cursor.execute('SELECT 1')
                self.cursor.execute('LISTEN sqlobjectupdate')
                self.log.info('Connected to database')
                break
            except OperationalError or DatabaseError as e:
                if first:
                    # don't print text once in five seconds
                    self.log.error('Database not available')
                    first = False
                self.conn = None
                log.exception(e)
                sleep(5)  
            
    def populate_workers(self):
        # dynamically import servers set on config
        for server in self.conf.servers:
            try:
                module = __import__('servers.%s' % server)
                worker = vars(module)[server].RenkiServer()
                self.workers.append(worker)
                self.conf.add_tables(worker.tables)
            except ImportError:
                self.log.error('Cannot import nonexistent server %s' % server)
                self.log.error('Check our config' % server)
                sys.exit(1)
        """if 'bind' in self.conf.servers:
            import bind
            worker = bind.RenkiService()
            print(vars(worker))
            self.workers.append(worker)
            self.conf.add_tables(worker.tables)"""

    def feed_workers(self):
        """Get changes and add them to workers"""
        changes = self.get_changes()
        if changes:
            self.workqueue.append(change)
            for worker in self.workers:
                worker.add(change)
        
    def mainloop(self):
        self.log.info("Starting mainloop")
        self.log.info('Starting services')
        for worker in self.workers:
            worker.start()
        self.cursor.execute('LISTEN sqlobjectupdate;')
        self.log.info('Waiting for notifications on channel "sqlobjectupdate"')
        while True:
            try:
                if select.select([self.conn],[],[],30) == ([],[],[]):
                    self.log.debug('Timeout')
                    try:
                        self.cursor.execute('SELECT 1')
                    except DatabaseError as e:
                        self.reconnect()
                           
                        
                else:
                    self.conn.poll()
                    print("%s" % self.conn.notifies)
                    while self.conn.notifies:
                        notify = self.conn.notifies.pop()
                        self.log.info('Got notify: pid: %s, channel: %s, payload: %s' % (notify.pid, notify.channel, notify.payload))
                        self.feed_workers()
            except OperationalError as e:
                log.exception(e)
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
        
        ## here some duplicate check 
        # also delete updates and inserts if also delete to same row
        for change in changes:
            # loop over all changes, ignore unknown tables
            if change.table in self.srv.tables:
                self.log.debug('Action %s in table %s' % (change.event_type, change.table))
                results = []
                print("Transaction_id: %s" % str(change.transaction_id))
                """results = self.srv.session.execute("SELECT *,xmin,xmax FROM %s WHERE xmin = :transaction" % change.table, 
                    {'transaction' : str(change.transaction_id)},
                    mapper=self.srv.tables[change.table]).fetchall()"""
                try:
                    table = self.srv.tables[change.table]
                    print('CLASS MAPPER: %s' % class_mapper(self.srv.tables[change.table]).primary_key[0].name)
                    history_table = self.srv.tables['%s_history' % change.table]
                    history_table_pk = vars(history_table)[class_mapper(self.srv.tables[change.table]).primary_key[0].name]
                    print('HISTORY: %s' % history_table_pk)
                except KeyError:
                    self.log.error('History table %s_history not found for table %s!' % (change.table,change.table))
                    continue
                try:
                    if change.event_type == 'INSERT':
                        # On insert get only newobject
                        results = self.srv.session.query(self.srv.tables[change.table],Change_log).join(Change_log,
                            Change_log.data_id == class_mapper(table).primary_key[0]).filter(
                            class_mapper(table).primary_key[0] == change.data_id
                            ).filter(Change_log.transaction_id == change.transaction_id).filter(
                            Change_log.table == change.table).filter(
                            Change_log.event_type == 'INSERT').all()
                    elif change.event_type == 'UPDATE':
                        # on update get newobject from table and old object from history
                        results = self.srv.session.query(table,Change_log,history_table).join(Change_log,
                        Change_log.data_id == class_mapper(table).primary_key[0]).join(
                        history_table, class_mapper(table).primary_key[0] == history_table_pk).filter(
                        history_table_pk == change.data_id).filter(
                        Change_log.transaction_id == change.transaction_id ).filter(
                        history_table.old_xmax == change.transaction_id).all()
                    elif change.event_type == 'DELETE':
                        # on delete get oldobject from history
                        results = self.srv.session.query(history_table, Change_log).join(Change_log,
                        Change_log.data_id == history_table_pk).filter(
                        Change_log.transaction_id == change.transaction_id).filter(
                        history_table.old_xmax == change.transaction_id).all()
                    print("RESULTS: %s" % results)
                    for result in results:
                        self.workqueue.append(change)
                        print("WORK: %s" % vars(result))
                        for worker in self.workers:
                            worker.add(result)
                    self.latest_transaction = change.transaction_id
                except IntegrityError or OperationalError or ProgrammingError as e:
                    self.log.error('Error while getting changed data')
                    self.log.exception(e)
                            
    
    def killall(self):
        for worker in self.workers:
            try:
                self.log.info('Stopping service %s' % worker.name)
                worker.kill()
            except Exception as e:
                self.log.exception(e)

if __name__ == '__main__':
    log = logging.getLogger("renkisrv")
    log.info("Welcome to %s version %s" % (__name__, __version__))
    try:
        config = Config()
    except ConfigError as error:
        log.error('Config error: %s' % error)
        sys.exit(1)
    if config.debug:
        x.setLevel(logging.DEBUG)
    else:
        x.setLevel(logging.WARNING)
    h = logging.FileHandler(filename="renkiserv.log")
    try:
        if config.debug:
            h.setLevel(logging.DEBUG)
        else:
            h.setLevel(logging.WARNING)
    except:
        h.setLevel(logging.WARNING)
    renkisrv = RenkiSrv(config)
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