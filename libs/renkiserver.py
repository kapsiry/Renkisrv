import logging
import threading
from time import sleep
from datetime import datetime, timedelta

class Retry(object):
    def __init__(self, object):
        self.object = object
        self.timestamp = datetime.now()

class RenkiServer(threading.Thread):
    def __init__(self, name=None):
        threading.Thread.__init__(self)
        self.tables = []
        self._queue = []
        self._retry = []
        self.name = 'Renkiserver'
        if name:
            self.name = name
        self.conf = None
        self.srv = None
        self._stop = False
        self.config_options = []
        self.log = logging.getLogger(self.name)

    def _kill(self):
        """Called when Renkisrv exits"""
        self._stop = True

    def _add(self, sqlobject):
        self._queue.insert(0,sqlobject)

    def insert(self, sqlobject, table):
        """Do something on insert to table <table>
        sqlobject contains inserted row object
        table contains name of name
        Return True on successful run
        """
        return True

    def update(self,old_sqlobject, new_sqlobject,table):
        """Do something on update to table <table>
        old_sqlobject contains row before update
        new_sqlobject contains row after update
        Return True on successful run
        """
        return True

    def delete(self,sqlobject,table):
        """Do something on delete to table <table>
        sqlobject contains row before delete
        Return True on successful run
        """
        return True

    def run(self):
        self.log.info('%s service started' % self.name)
        while not self._stop:
            retry = True
            try:
                sqlobject = self._queue.pop()
            except IndexError:
                try:
                    # Trust objects are in time order
                    retryobject = self._retry.pop()
                    if retryobject.timestamp < (datetime.now() - timedelta(seconds=30)):
                        sqlobject = retryobject.object
                        retry = False
                    else:
                       self._retry.insert(0,retryobject)
                       continue
                except IndexError:
                    sleep(1)
                    continue
            try:
                if sqlobject.Change_log.table in self.tables:
                    for label in sqlobject._labels:
                        if label is not 'Change_log':
                            if not label.endswith('_history'):
                                mynewobject = vars(sqlobject)[label]
                            elif label.endswith('_history'):
                                myoldobject = vars(sqlobject)[label]
                    if sqlobject.Change_log.event_type == 'INSERT':
                        if not self.insert(mynewobject, sqlobject.Change_log.table):
                            if retry:
                                self._retry.insert(0,Retry(sqlobject))
                                self.log.info('Failed to process object %s, added to retry queue' % vars(mynewobject))
                            else:
                                self.log.critical('Permanently failed prosessing object %s' % vars(mynewobject))
                    elif sqlobject.Change_log.event_type == 'UPDATE':
                        if not self.update(myoldobject, mynewobject, sqlobject.Change_log.table):
                            if retry:
                                self._retry.insert(0,Retry(sqlobject))
                                self.log.info('Failed to process object %s, added to retry queue' % vars(mynewobject))
                            else:
                                self.log.critical('Permanently failed prosessing object %s' % vars(mynewobject))
                    elif sqlobject.Change_log.event_type == 'DELETE':
                        if not self.delete(myoldobject, sqlobject.Change_log.table):
                            if retry:
                                self._retry.insert(0,Retry(sqlobject))
                                self.log.info('Failed to process object %s, added to retry queue' % vars(myoldobject))
                            else:
                                self.log.critical('Permanently failed prosessing object %s' % vars(myoldobject))
            except Exception as e:
                self.log.exception(e)
                self.log.error('Error processing object %s' % vars(sqlobject))
        self.log.error('Service %s stopped' % self.name)