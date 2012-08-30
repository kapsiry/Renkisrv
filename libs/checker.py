# encoding: utf-8

import logging
import threading

from sqlalchemy.orm import class_mapper

from libs.services import Change_log

"""This file is part of Renkisrv-project."""

class Checker(threading.Thread):
    def __init__(self, main):
        threading.Thread.__init__(self)
        self.log = logging.getLogger('Checker')
        self.workers = main.workers
        self.srv = main.srv
        self.conf = main.conf
        self.success = False
        self._stop = False

    def run(self):
        """Put all (missed) rows to workers"""
        for table in self.conf.tables:
            if table in ['t_change_log']:
                continue
            self.log.debug('Checking changes on table %s' % table)
            if self._stop:
                return
            pk = vars(self.srv.tables[table])[class_mapper(self.srv.tables[table]).primary_key[0].name]
            results = self.srv.session.query(self.srv.tables[table],Change_log).join(
                    Change_log, Change_log.data_id == pk).filter(
                    Change_log.table == table).filter(
                    Change_log.event_type == 'INSERT').all()
            for result in results:
                if self._stop:
                    return
                for worker in self.workers:
                    if table in worker.tables:
                        worker._add_check(result)
        self.log.info('Checked all values. Checker exits!')
        self.success = True

    def _kill(self):
        self._stop = True