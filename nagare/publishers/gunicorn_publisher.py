# --
# Copyright (c) 2008-2018 Net-ng.
# All rights reserved.
#
# This software is licensed under the BSD License, as described in
# the file LICENSE.txt, which you should have received as part of
# this distribution.
# --

"""The Gunicorn publisher"""

import os
import multiprocessing

from ws4py import websocket
from gunicorn.app import base
from gunicorn import util, workers
from nagare.server import http_publisher


gthread_worker = util.load_class(workers.SUPPORTED_WORKERS['gthread'])
workers.SUPPORTED_WORKERS['gthread'] = 'nagare.publishers.gunicorn_publisher.Worker'


class Cfg(object):

    def __init__(self, cfg):
        self.keepalive = 30
        self.is_ssl = cfg.is_ssl


class WebSocket(workers.gthread.TConn, websocket.WebSocket):

    def __init__(self):
        pass

    def bind_to(self, conn):
        workers.gthread.TConn.__init__(
            self,
            Cfg(conn.cfg),
            conn.sock, conn.client, conn.server
        )
        websocket.WebSocket.__init__(self, conn.sock)

    def close(self):
        self.closed(None)
        super(WebSocket, self).close()


class Worker(gthread_worker):

    def handle(self, conn):
        if isinstance(conn, WebSocket):
            return conn.process(conn.sock.recv(1024)), conn
        else:
            keepalive, conn = super(Worker, self).handle(conn)
            websocket = conn.websocket
            if websocket is not None:
                del conn.websocket
                websocket.bind_to(conn)
                conn = websocket

            return keepalive, conn

    def handle_request(self, req, conn):
        keepalive = super(Worker, self).handle_request(req, conn)
        conn.websocket = req.websocket

        return keepalive


class GunicornPublisher(base.BaseApplication):
    def __init__(self, app_factory, reloader, start_handle_request, **config):
        self.app_factory = app_factory
        self.reloader = reloader
        self.start_handle_request = start_handle_request
        self.config = config

        super(GunicornPublisher, self).__init__()

    def load_config(self):
        for k, v in self.config.items():
            self.cfg.set(k, v)

        self.cfg.set('post_request', self.post_request)
        self.cfg.set('post_worker_init', lambda worker: self.post_worker_init(worker, self.reloader))

    def load(self):
        app = self.app_factory()

        return lambda environ, start_response: self.start_handle_request(app, environ, start_response)

    @staticmethod
    def post_request(worker, req, environ, resp):
        req.websocket = environ['websocket']

    @staticmethod
    def post_worker_init(worker, reloader):
        if reloader is not None:
            reloader.start(lambda reloader, path: os._exit(0))


class Publisher(http_publisher.Publisher):
    """The Gunicorn publisher"""

    CONFIG_SPEC = dict(
        http_publisher.Publisher.CONFIG_SPEC,
        host='string(default="127.0.0.1")',
        port='integer(default=8080)',
        worker_class='string(default="gthread")'
    )
    for spec in (
        'socket/string', 'umask/integer', 'backlog/integer',
        'workers/string', 'threads/string',
        'worker_connections/integer', 'max_requests/integer',
        'timeout/integer', 'graceful_timeout/integer', 'keepalive/integer',
        'limit_request_line/integer', 'limit_request_fields/integer',
        'limit_request_field_size/integer',
        'preload/boolean',
        'chdir/string', 'daemon/boolean', 'pidfile/string', 'worker_tmp_dir/string',
        'user/string', 'group/string',
        'tmp_upload_dir/string', 'accesslog/string', 'access_log_format/string',
        'errorlog/string', 'loglevel/string', 'logger_class/string', 'logconf/string',
        'syslog_addr/string', 'syslog/boolean', 'syslog_prefix/string', 'syslog_facility/string',
        'enable_stdio_inheritance/boolean', 'proc_name/string',
        'keyfile/string', 'certfile/string', 'ssl_version/integer', 'cert_reqs/integer',
        'ca_certs/string', 'suppress_ragged_eofs/boolean', 'do_handshake_on_connect/boolean',
        'ciphers/string'
    ):
        name, type_ = spec.split('/')
        CONFIG_SPEC[name] = type_ + '(default=None)'

    def __init__(self, name, dist, workers, threads, socket=None, **config):
        """Initialization
        """
        nb_cpus = multiprocessing.cpu_count()
        workers = eval(workers or '1', {}, {'NB_CPUS': nb_cpus})
        threads = eval(threads or '1', {}, {'NB_CPUS': nb_cpus})

        self.has_multi_processes = workers > 1
        self.has_multi_threads = threads > 1

        config = {k: v for k, v in config.items() if v is not None}

        http_publisher.Publisher.__init__(
            self,
            name, dist,
            workers=workers, threads=threads,
            **config
        )

    @staticmethod
    def monitor(reloader, reload_action):
        return 0

    @staticmethod
    def set_websocket(websocket, environ):
        environ['websocket'] = websocket

    def create_websocket(self, environ):
        environ['set_websocket'] = self.set_websocket
        return WebSocket() if environ.get('HTTP_UPGRADE', '') == 'websocket' else None

    def _create_app(self, services_service):
        return lambda: services_service(super(Publisher, self).create_app)

    def _serve(self, app_factory, host, port, socket=None, reloader_service=None, **config):
        if (reloader_service is not None) and self.has_multi_processes:
            print("The reloader service can't be activated in multi-processes")
            reloader_service = None

        bind = ('unix:' + (os.path.abspath(os.path.expanduser(socket)))) if socket else ('%s:%d' % (host, port))

        GunicornPublisher(app_factory, reloader_service, self.start_handle_request, bind=bind, **config).run()
