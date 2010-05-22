#!/usr/bin/env python

import authinfo, config, gtk, gtkextra, gobject
import imaplib2, os, socket, subprocess, sys, threading

def main(argv):
   gobject.threads_init()
   channel = Channel()
   construct_watcher(channel).start()
   construct_gui(channel).start()
   try:
       gtk.main()
   except KeyboardInterrupt:
       channel.quitting = True
       return 1
   return 0

def construct_watcher(channel):
    return ImapWatcher(channel)

class ImapWatcher(threading.Thread):
    def __init__(self, channel):
        threading.Thread.__init__(self)
        self.channel = channel

    def run(self):
        imap = None
        timeout = 30 * 60
        while not self.channel.quitting:
            if not imap:
                imap = self.connect()
                if not imap:
                    self.channel.mail_error()
                    continue
            try:
                imap.select('INBOX')
                status, [messages] = imap.search(None, 'UNSEEN')
            except socket.error, imaplib2.abort:
                imap = None
            if status != 'OK' or imap is None:
                self.channel.mail_error()
                continue
            self.channel.new_mail(len(messages.split()))
            try:
                imap.idle()
            except Exception:
                imap = None
                self.channel.mail_error()

    def connect(self):
        self.channel.reconnect.wait()
        self.channel.reconnect.clear()
        return self.make_imap_client()

    def make_imap_client(self):
        host = config.host
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

def construct_gui(channel):
    return GtkGui(channel)

class GtkGui:
    def __init__(self, channel):
        self.channel = channel
        self.icon = self.make_icon()
        self.menu = self.make_menu()

    def start(self):
        self.reconnect()
        self.update_icon()
        threading.Thread(target = self.listener).start()

    def listener(self):
        while not self.channel.quitting:
            self.channel.mail_update.wait()
            self.channel.mail_update.clear()
            gobject.idle_add(self.update_icon)

    def make_icon(self):
        icon = gtkextra.StatusIcon()
        icon.connect("activate", self.click)
        icon.connect("popup-menu", self.popup)
        return icon

    def click(self, *args):
        # TODO: should this be configurable?
        subprocess.Popen(['gnus']).wait()

    def popup(self, icon, button, activate_time):
        self.menu.popup(None, None, gtk.status_icon_position_menu,
                        button, activate_time, icon)

    def make_menu(self):
        menu = gtk.Menu()
        items = [("Reconnect", self.reconnect),
                 ("Quit", self.quit)]
        for label, method in items:
            item = gtk.MenuItem(label)
            item.connect("activate", method)
            item.show()
            menu.append(item)
        return menu

    def reconnect(self, *args):
        self.channel.reconnect.set()

    def quit(self, *args):
        gtk.main_quit()

    def update_icon(self):
        if self.channel.mail_status.error:
            image = 'error.png'
        else:
            image = 'mail.png'
        self.icon.set_from_file_with_counter(self.get_data_file(image),
                                             self.channel.mail_status.new)

    def get_data_file(self, file_name):
        if os.path.isabs(file_name):
            return file_name
        data_dir = os.path.join(os.path.dirname(__file__), 'data')
        return os.path.join(data_dir, file_name)

class Channel:
    def __init__(self):
        self.mail_update = threading.Event()
        self.mail_status = MailStatus()
        self.reconnect = threading.Event()
        self.quitting = False

    def mail_error(self):
        self.mail_status.error = True
        self.mail_update.set()

    def new_mail(self, count):
        self.mail_status.error = False
        self.mail_status.new = count
        self.mail_update.set()

class MailStatus:
    def __init__(self):
        self.new = 0
        self.error = False

if __name__ == '__main__':
   sys.exit(main(sys.argv))
