import logging
import threading
from time import sleep

class RenkiServer(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.tables = []
        self.queue = []
        self.name = 'dummy'
        self.stop = False
        self.log = logging.getLogger('RenkiServer')

    def kill(self):
        self.stop = True

    def add(self, sqlobject):
        self.queue.insert(0,sqlobject)

    def insert(self, sqlobject, table):
        """Do something on insert to table <table>
        sqlobject contains inserted row object
        table contains name of name
        """
        return True

    def update(self,old_sqlobject, new_sqlobject,table):
        """Do something on update to table <table>
        old_sqlobject contains row before update
        new_sqlobject contains row after update
        """
        return True

    def delete(self,sqlobject,table):
        """Do something on delete to table <table>
        sqlobject contains row before delete
        """
        return True

    def run(self):
        self.log.info('%s service started' % self.name)
        while not self.stop:
            try:
                sqlobject = self.queue.pop()
            except IndexError:
                sleep(1)
                continue
            try:
                if sqlobject.Change_log.table in self.tables:
                    for label in sqlobject._labels:
                        if label is not 'Change_log':
                            if not label.endswith('_history'):
                                print("NEWOBJECT : %s" % label)
                                mynewobject = vars(sqlobject)[label]
                            elif label.endswith('_history'):
                                myoldobject = vars(sqlobject)[label]
                    if sqlobject.Change_log.event_type == 'INSERT':
                        if not self.insert(mynewobject, sqlobject.Change_log.table):
                            self.log.error('Error processing object %s on insert function' % vars(myobject))
                    elif sqlobject.Change_log.event_type == 'UPDATE':
                        if not self.update(myoldobject, mynewobject, sqlobject.Change_log.table):
                            self.log.error('Error processing object %s on update function' % vars(myobject))
                    elif sqlobject.Change_log.event_type == 'DELETE':
                        if not self.delete(myoldobject, sqlobject.Change_log.table):
                            self.log.error('Error processing object %s on delete function' % vars(myobject))
            except Exception as e:
                self.log.exception(e)
                self.log.error('Error processing object %s' % vars(sqlobject))
        self.log.error('Service %s stopped' % self.name)