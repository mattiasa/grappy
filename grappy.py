#!/usr/bin/python

# Copyright (c) 2004 Mattias Amnefelt <mattiasa@stacken.kth.se>
# All rights reserved.
# 
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
# 
# 1. Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
# 
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.
# 
# 3. The name of the Author may not be used to endorse or promote
#    products derived from this software without specific prior written
#    permission.
# 
# THIS SOFTWARE IS PROVIDED BY THE INSTITUTE AND CONTRIBUTORS ``AS IS'' AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE INSTITUTE OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS
# OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
# HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY
# OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF
# SUCH DAMAGE.
#

# This software is based on greylist-python which has been placed in the
# public domain by it's author Vsevolod Sipakov <versus@megalink.ru>

# Configuration variables

# The amount of time from the first time a triplet is seen until it is
# allowed trough
GREYLIST_DELAY = 60                  # seconds

# Greylist on network instead of exact address
LIGHTGREY = True

# The message sent when greylisting
GREYLIST_MESSAGE = "Temporary failure"

# Just populate the database, always approve message
LEARNING_MODE = False

# Allow messages when sql errors occurs
PASS_ON_ERROR = True

# Database configuration
DBHOST='dbhost.example.com'
DATABASE='greylist'
DBUSER='greylist'
DBPASS='secret'

# Set to True for debug
debug = False

import sys, time, os
import syslog, traceback
import SocketServer
import socket
import re
import thread


# If you want to use the mysql interface, uncomment the following line
# import MySQLdb as grappydb

# If you want to use the postgresql interface, uncomment the following line
import pgdb as grappydb
postgresql=True;

progname="grappy"

def daemonize (pidfilename,stdin='/dev/null', stdout='/dev/null', stderr='/dev/null'):
    '''This forks the current process into a daemon.
    The stdin, stdout, and stderr arguments are file names that
    will be opened and be used to replace the standard file descriptors
    in sys.stdin, sys.stdout, and sys.stderr.
    These arguments are optional and default to /dev/null.
    Note that stderr is opened unbuffered, so
    if it shares a file with stdout then interleaved output
    may not appear in the order that you expect.

    References:
    UNIX Programming FAQ
    1.7 How do I get my program to act like a daemon?
    http://www.erlenstar.demon.co.uk/unix/faq_2.html#SEC16
    Advanced Programming in the Unix Environment
    W. Richard Stevens, 1992, Addison-Wesley, ISBN 0-201-56317-7.
    
    History:
      2001/07/10 by Jürgen Hermann
      2002/08/28 by Noah Spurrier
    '''
    # Do first fork.
    try: 
        pid = os.fork() 
        if pid > 0:
            sys.exit(0) # Exit first parent.
    except OSError, e: 
        sys.stderr.write ("fork #1 failed: (%d) %s\n" % (e.errno, e.strerror)    )
        sys.exit(1)
        
    # Decouple from parent environment.
    os.chdir("/") 
    os.umask(0) 
    os.setsid() 
    
    # Do second fork.
    try: 
        pid = os.fork() 
        if pid > 0:
            sys.exit(0) # Exit second parent.
    except OSError, e: 
        sys.stderr.write ("fork #2 failed: (%d) %s\n" % (e.errno, e.strerror)    )
        sys.exit(1)
        
    # Now I am a daemon!

    mypid = os.getpid()

    pidfile = file(pidfilename, "w+")
    pidfile.write("%s\n" % mypid)
    pidfile.flush()
    pidfile.close()
    
    # Redirect standard file descriptors.
    si = file(stdin, 'r')
    so = file(stdout, 'a+')
    se = file(stderr, 'a+', 0)
    os.dup2(si.fileno(), sys.stdin.fileno())
    os.dup2(so.fileno(), sys.stdout.fileno())
    os.dup2(se.fileno(), sys.stderr.fileno())

def syslog_traceback():
    lines = traceback.format_exception (sys.exc_type, sys.exc_value,
       sys.exc_traceback)
    for i in lines:
        printlog(i)

def printlog(msg):
    if debug:
        print msg
    else:
        syslog.syslog(msg)

def printdebug(msg):
    if debug:
        print msg


class SQLHandler:
    queue = []
    lock = thread.allocate_lock()

    # Return an connection to the pool
    def return_connection(self, o):
        self.lock.acquire()
        self.queue.append(o)
        
        self.lock.release()

    # Get a connection from the pool, create a new if neccesary
    def get_connection(self):
        self.lock.acquire()
        try:
            ret = self.queue.pop(0)
        except IndexError:
            ret = self.new_connection()
            
        self.lock.release()
        return ret


    def select(self,k):
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute(k)
        t = cursor.fetchone()

        cursor.close()
        self.return_connection(conn)

        return t
        
    def execute(self,k):
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute(k)
        conn.commit()

        cursor.close()
        self.return_connection(conn)

    def new_connection(self):
        printdebug('Allocating new connection')
        if postgresql:
            conn = grappy.connect(user=DBUSER,host=DBHOST,database=DATABASE,password=DBPASS)
        else:
            conn = grappy.connect(user=DBUSER,host=DBHOST,db=DATABASE,passwd=DBPASS)
        return conn

    def escape(self,k):
        return re.sub(r'([/|&{}#^~\\\']+)', '', k)
    

class GreylistRequestHandler (SocketServer.StreamRequestHandler):
    def handle(self):
        self.info = policy_info()
        while(1):
            l = self.rfile.readline()
            if l:
                l = l.rstrip()
            else:
                printlog("disconnect")
                break

            if l:
                self.info.add_pair(l)
            else:
                # empty input line - we have to make a decision
                ip,sender,recipient = self.info.triplet()
                action = ""
                try:
                    if self.info.check_whitelist():
                        printlog("whitelisted: sender=%s recipient=%s ip=%s" % (sender,recipient,ip))
                        action = "dunno"
                    else:
                        action = self.info.get_policy()

                except:
                    printlog("MySQL database error")
                    if not action:
                        if PASS_ON_ERROR:
                            syslog_traceback()
                            action = "dunno"
                        else:
                            syslog_traceback()
                            action = "defer_if_permit Local error"

                printdebug('Action:'+action)

                if LEARNING_MODE:
                    self.wfile.write("action=dunno\n\n")
                else:
                    self.wfile.write("action=%s\n\n" % (action))

                sys.stdout.flush()
                self.info.cleanup()

class policy_info:
    lock = thread.allocate_lock()

    def __init__(self):
        self.words = {}
        self.sql = SQLHandler()

    def cleanup(self):
        self.words = {}

    def lightaddress(self, address):
        return re.sub("\.[^.]*$", '.0', address)

    def triplet(self):
        address = ""
        sender = ""
        recipient = ""
        try:
            address = self.words['client_address']
            if LIGHTGREY:
                address = self.lightaddress(address)

        except KeyError:
            pass
        try:
            sender = self.words['sender']
        except KeyError:
            sender = 'void@void'
            pass
        try:
            recipient = self.words['recipient']
        except KeyError:
            pass

        if sender == '':
            sender = 'void@void'

                        
        return address,sender,recipient

    def add_pair(self,k):
        try:
            # fixed: possible multiple '='s handled by maxsplit argument
            a,b = k.split('=',1)
            b = self.sql.escape(b)
            self.words[a[:512]] = b[:512]
        except ValueError:
            printdebug("junk at input: " + k[:100])

    def check_whitelist(self):
        """returns if the entry is whitelisted"""
        ip,sender,recipient = self.triplet()

        lightip = re.sub("\.[^.]*$", '', ip)
        senderdomain = re.sub("^.*@", '@', sender)
        recipientdomain = re.sub("^.*@", '@', recipient)


        k = "select count(*) from whitelist where \
            ip='%s' or ip='%s' or \
            sender='%s' or sender='%s' or \
            recipient='%s' or recipient='%s' \
            limit 1" % (ip,lightip,sender,senderdomain,recipient,recipientdomain)

        t = self.sql.select(k)

        if t[0] > 0:
            return True
        else:
            return False
        
    def search_entry(self):
        """returns first as unixtime"""
        ip,sender,recipient = self.triplet()
        k = "select first from greylist where ip='%s' \
              and sender='%s' and recipient='%s'" % (ip,sender,recipient)
        t = self.sql.select(k)
        if t: return t[0]
        return None

    def update_entry(self):
        ip,sender,recipient = self.triplet()
        k = "update greylist set last=%i,n=n+1 where ip='%s' \
              and sender='%s' and recipient='%s'" % (time.time(),ip,sender,recipient)
        self.sql.execute(k)

    def create_entry(self):
        self.lock.acquire()
        try:
            ip,sender,recipient = self.triplet()

            k = "select first from greylist where ip='%s' \
                and sender='%s' and recipient='%s'" % (ip,sender,recipient)
            t = self.sql.select(k)
            if t:
                self.lock.release()
                return
            
            k = "insert into greylist (ip,sender,recipient,first,last,n) \
                values('%s','%s','%s',%i,%i,%i)" % (ip,sender,recipient,
                time.time(), time.time(),1)
            self.sql.execute(k)
        except:
            self.lock.release()
            raise
            
        self.lock.release()
                

    def get_policy(self):
        ip,sender,recipient = self.triplet()
        firsttime = self.search_entry()
        if not firsttime:
            self.create_entry()
        if firsttime and (time.time() > firsttime+GREYLIST_DELAY): 
            self.update_entry()
            return "dunno"
        else:
            printlog("greylisted: sender=%s recipient=%s ip=%s" % (sender,recipient,ip))
            return "defer_if_permit %s" % (GREYLIST_MESSAGE)

# Dummy subclass of ThreadingTCPServer just to set allow_reuse_address
class MyThreadingTCPServer (SocketServer.ThreadingTCPServer):
    allow_reuse_address = True
            
def main():
    syslog.openlog(progname+'['+str(os.getpid())+']',0,syslog.LOG_MAIL)
    printlog("Started")
    tcpserver = MyThreadingTCPServer(("127.0.0.1",4343),
                                     GreylistRequestHandler)
    tcpserver.serve_forever()

try:
    syslog.openlog(progname+'['+str(os.getpid())+']',0,syslog.LOG_MAIL)

    if not debug: 
        daemonize('/var/run/greylist.pid')
    main()

except SystemExit:
        pass
except KeyboardInterrupt:
        raise
except:
    syslog_traceback()
    sys.exit(1);
