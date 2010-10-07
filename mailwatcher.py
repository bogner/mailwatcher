#!/usr/bin/env python

import authinfo
import config
import gtkextra
import imaplib2
import log

import Queue
import gobject
import gtk
import indicate
import multiprocessing
import os
import socket
import subprocess
import sys
import threading

def main(argv):
    if '-d' in argv:
        log.set_level("debug")

    mail_queue = multiprocessing.Queue()
    server_queue = multiprocessing.Queue()

    gui = LibIndicateGui(mail_queue, server_queue)
    gui.start()
    for server in get_mail_servers():
        watcher = ImapWatcher(server, mail_queue, server_queue)
        watcher.start()

    try:
        gui.join()
    except KeyboardInterrupt:
        watcher.terminate()
        gui.terminate()
        return 1
    return 0

def get_mail_servers():
    return [MailServer(config.host, config.host.split(".")[-2], ["INBOX"])]

class MailServer(object):
    def __init__(self, host, short_name, mailboxes):
        self.host = host
        self.short_name = short_name
        self.mailboxes = mailboxes

class ImapWatcher(multiprocessing.Process):
    def __init__(self, mail_server, mail_queue, server_queue):
        multiprocessing.Process.__init__(self)
        self.mail_server = mail_server
        self.mail_queue = mail_queue
        self.server_queue = server_queue
        self.need_a_command = False

    def run(self):
        imap = None
        timeout = 30 * 60
        while True:
            command = self.check_for_commands()
            if command == "quit":
                break
            if command == "reconnect":
                imap = None

            if not imap:
                imap = self.connect()
                if not imap:
                    self.error("Could not connect")
                    self.need_a_command = True
                    continue

            try:
                imap.select('INBOX')
                status, [messages] = imap.search(None, 'UNSEEN')
            except socket.error, imaplib2.abort:
                imap = None

            if status != 'OK' or imap is None:
                self.error("Failed to read headers")
                continue
            self.new_mail("INBOX", len(messages.split()))

            try:
                imap.idle()
            except Exception:
                imap = None
                self.error("Error while idling")

    def error(self, msg):
        self.mail_queue.put(MailError(self.mail_server, msg))

    def new_mail(self, mailbox, count):
        self.mail_queue.put(NewMail(self.mail_server, mailbox, count))

    def check_for_commands(self):
        try:
            return self.server_queue.get(block = self.need_a_command)
        except Queue.Empty:
            return None

    def connect(self):
        return self.make_imap_client()

    def make_imap_client(self):
        host = self.mail_server.host
        if config.use_ssl:
            IMAP4 = imaplib2.IMAP4_SSL
        else:
            IMAP4 = imaplib2.IMAP4
        auth = authinfo.AuthInfo.from_netrc(host)

        try:
            imap = IMAP4(host)
            imap.login(auth.user, auth.password)
        except socket.error:
            return None
        return imap

class LibIndicateGui(multiprocessing.Process):
    def __init__(self, mail_queue, server_queue):
        multiprocessing.Process.__init__(self)
        self.mail_queue = mail_queue
        self.server_queue = server_queue
        self.indicators = {}

    def register_indicators(self):
        server = indicate.indicate_server_ref_default()
        server.set_type("message.mail")
        server.set_desktop_file(get_desktop_file())
        server.connect("server-display", self.click)

        self.force_gtk_to_render_indicators()

    def force_gtk_to_render_indicators(self):
        for server in get_mail_servers():
            for mailbox in server.mailboxes:
                self.get_indicator_for(server, mailbox)

    def click(self, *args):
        # TODO: should this be configurable?
        for indicator in self.indicators:
            self.indicators[indicator].set_property("draw-attention", "false")
        subprocess.Popen(['gnus']).wait()

    def run(self):
        self.register_indicators()
        self.start_queue_watcher()
        gtk.main()

    def start_queue_watcher(self):
        gobject.idle_add(self.watch_mail_queue)

    def watch_mail_queue(self):
        new_mail = self.mail_queue.get()
        self.update_indicator(new_mail)
        return True

    def reconnect(self, *args):
        self.server_queue.put("reconnect")

    def update_indicator(self, new_mail):
        server = new_mail.server
        if new_mail.error:
            self.show_mailbox_error(server, new_mail.message)
        else:
            self.show_mailbox_count(server, new_mail.mailbox, new_mail.count)

    def show_mailbox_error(self, server, error):
        for indicator in self.get_server_indicators(server):
            indicator.set_property("count", "error")
            # TODO? indicator.set_property("draw-attention", "true")
        log.error(error)

    def show_mailbox_count(self, server, mailbox, count):
        log.debug("%s: %s (%s)" % (server.short_name, mailbox, count))

        indicator = self.get_indicator_for(server, mailbox)
        old_count = indicator.get_property("count")
        indicator.set_property("count", str(count))
        if count > int_or_zero(old_count):
            indicator.set_property("draw-attention", "true")

    def get_server_indicators(self, server):
        return [indicator for label, indicator in self.indicators.items()
                if label.startswith(server.short_name + ".")]

    def get_indicator_for(self, server, mailbox):
        label = "%s.%s" % (server.short_name, mailbox)
        if label not in self.indicators:
            self.indicators[label] = self.new_indicator(label)
        return self.indicators[label]

    def new_indicator(self, label):
        indicator = indicate.Indicator()
        indicator.set_property("name", label)
        indicator.set_property("count", "0")
        #indicator.connect("user-display", ?)
        indicator.show()
        return indicator

def int_or_zero(x):
    try:
        return int(x)
    except ValueError:
        return 0

def get_desktop_file():
    name = "mailwatcher.desktop"
    directory = os.path.dirname(__file__)
    return os.path.abspath(os.path.join(directory, name))

class MailError:
    def __init__(self, server, message):
        self.server = server
        self.message = message
        self.error = True

    def __str__(self):
        return "error: " + self.message

class NewMail:
    def __init__(self, server, mailbox, count):
        self.server = server
        self.mailbox = mailbox
        self.count = count
        self.error = False

    def __str__(self):
        return "%s (%s)" % (self.mailbox, self.count)

if __name__ == '__main__':
   sys.exit(main(sys.argv))
