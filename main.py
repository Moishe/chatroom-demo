from google.appengine.api import app_identity
from google.appengine.api import taskqueue
from google.appengine.api import xmpp
from google.appengine.ext import db
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
import logging
import os
import sys

appid = app_identity.get_application_id()
version = os.environ['CURRENT_VERSION_ID'].split('.')[0]
cluster = 'appspot.com'
custom_cluster = 'appspotchat.com'

class Friends(db.Model):
  bare_jid = db.StringProperty()
  my_jid = db.StringProperty()
  nickname = db.StringProperty()

class Resources(db.Model):
  jid = db.StringProperty()
  bare_jid = db.StringProperty()
  my_jid = db.StringProperty()
  show = db.StringProperty()
  status = db.StringProperty()

class MessageHandler(webapp.RequestHandler):
  def post(self):
    pass


class ResourceFetcher():
  def __init__(self, bare_jid, my_jid):
    q = Resources.all()
    q.filter('bare_jid =', bare_jid)
    q.filter('my_jid =', my_jid)
    q.order('bare_jid')
    self.pairs = {}
    for resource in q:
      self.pairs['.'.join([resource.show, resource.status])] = 1

  def best(self):
    SHOW_BY_VALUE = ['', 'away', 'dnd', 'xa']
    best_idx = sys.maxint
    for pair in self.pairs:
      (show, status) = pair.split('.')
      idx = SHOW_BY_VALUE.index(show)
      if idx < best_idx:
        best_idx = idx
        best_pair = (show, status)

    return best_pair


class MainPage(webapp.RequestHandler):
    def get(self):
      for friend in Friends.all():
        (show, status) = ResourceFetcher(friend.bare_jid, friend.my_jid).best()
        self.response.out.write('%s, %s, %s, %s<br>' % (friend.bare_jid,
                                                    friend.my_jid,
                                                    show,
                                                    status))
        xmpp.send_presence(friend.bare_jid, from_jid=friend.my_jid,
                           presence_type='probe')


class SubscribeHandler(webapp.RequestHandler):
    def post(self):
        sender = self.request.get('from').split('/')[0]
        to = self.request.get('to').split('/')[0]
        logging.debug('Subscription status: %s, stanza: %s.',
                      self.request.get('status'), self.request.get('stanza'))
        logging.info('Subscription request from %s to %s.', sender, to)

class PresenceHandler(webapp.RequestHandler):
  def post(self):
    available = self.request.path == '/_ah/xmpp/presence/available/'
    sender = self.request.get('from')
    to = self.request.get('to').split('/')[0]
    status = self.request.get('status')
    show = self.request.get('show')
    logging.debug('Show: %s, Status: %s, stanza: %s, available: %s',
                  show, status, self.request.get('stanza'), available)
    logging.debug('Presence from %s to %s.', sender, to)

    taskqueue.add(url='/updatepresence',
                  params = {'jid': sender,
                            'my_jid': to,
                            'show': show,
                            'available': available,
                            'status': status})


class UpdatePresenceHandler(webapp.RequestHandler):
  def post(self):
    available = self.request.get('available') == 'True'
    sender = self.request.get('jid')
    to = self.request.get('my_jid')
    status = self.request.get('status')
    show = self.request.get('show')

    q = Friends.all()
    q.filter("bare_jid =", sender.split('/')[0])
    q.filter("my_jid =", to)
    f = q.get()
    if not f:
      Friends(bare_jid=sender.split('/')[0],
              my_jid=to).put()

    q = Resources.all()
    q.filter("jid =", sender)
    q.filter("my_jid =", to)
    r = q.get()
    if not available:
      if r:
        r.delete()
    elif r:
      r.show = show
      r.status = status
      r.put()
    else:
      resource = Resources(jid=sender,
                           bare_jid=sender.split('/')[0],
                           my_jid=to,
                           show=show,
                           status=status)
      resource.put()

  def get(self):
    self.post()


application = webapp.WSGIApplication([
    ('/', MainPage),
    ('/updatepresence', UpdatePresenceHandler),
    ('/_ah/xmpp/message/chat/', MessageHandler),
    ('/_ah/xmpp/subscription/subscribe/', SubscribeHandler),
    ('/_ah/xmpp/presence/unavailable/', PresenceHandler),
    ('/_ah/xmpp/presence/available/', PresenceHandler)], debug=True)

def main():
    run_wsgi_app(application)

if __name__ == "__main__":
    main()
